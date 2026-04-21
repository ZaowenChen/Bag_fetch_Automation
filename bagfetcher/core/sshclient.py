"""Paramiko wrapper for BagFetcher."""
from __future__ import annotations

import errno
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import paramiko

from .exceptions import DownloadCancelled
from .models import BagFile
from .parser import bag_name_to_datetime


@dataclass
class SSHConnection:
    client: paramiko.SSHClient
    sftp: paramiko.SFTPClient


class SSHClientWrapper:
    """Wrapper providing higher-level SSH helpers."""

    def __init__(self, host: str, port: int, user: str, password: str | None = None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self._conn: SSHConnection | None = None

    # region lifecycle -------------------------------------------------
    def connect(self, keepalive: int = 30) -> None:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.user,
            password=self.password,
            look_for_keys=False,
            banner_timeout=30,
        )
        transport = client.get_transport()
        if not transport:
            raise RuntimeError("SSH transport not available")
        transport.set_keepalive(keepalive)
        sftp = client.open_sftp()
        self._conn = SSHConnection(client, sftp)

    def close(self) -> None:
        if self._conn:
            self._conn.sftp.close()
            self._conn.client.close()
            self._conn = None

    # endregion --------------------------------------------------------

    @property
    def sftp(self) -> paramiko.SFTPClient:
        if not self._conn:
            raise RuntimeError("SSH client not connected")
        return self._conn.sftp

    @property
    def client(self) -> paramiko.SSHClient:
        if not self._conn:
            raise RuntimeError("SSH client not connected")
        return self._conn.client

    def list_bags(self, bag_dir: str) -> list[BagFile]:
        try:
            attrs = self.sftp.listdir_attr(bag_dir)
        except IOError as exc:
            if getattr(exc, "errno", None) == errno.EACCES:
                return self._list_bags_via_sudo(bag_dir)
            raise

        items = []
        for attr in attrs:
            name = attr.filename
            if name.endswith(".active"):
                continue
            dt = bag_name_to_datetime(name)
            if not dt:
                continue
            remote_path = f"{bag_dir.rstrip('/')}/{name}"
            items.append(BagFile(name=name, remote_path=remote_path, dt=dt, size=attr.st_size))
        items.sort(key=lambda b: b.dt, reverse=True)
        return items

    def _list_bags_via_sudo(self, bag_dir: str) -> list[BagFile]:
        quoted = shlex.quote(bag_dir)
        cmd = (
            "shopt -s nullglob && "
            f"cd {quoted} && for file in *.bag; do stat -c '%n,%s' \"$file\"; done"
        )
        code, output = self.run_sudo(cmd)
        if code != 0:
            raise RuntimeError(f"Unable to list bags via sudo: {output}")

        items: list[BagFile] = []
        for line in output.splitlines():
            line = line.strip()
            if not line or ".active" in line:
                continue
            parts = line.split(",", 1)
            if len(parts) != 2:
                continue
            name, size_str = parts
            dt = bag_name_to_datetime(name)
            if not dt:
                continue
            try:
                size = int(size_str)
            except ValueError:
                size = 0
            remote_path = f"{bag_dir.rstrip('/')}/{name}"
            items.append(BagFile(name=name, remote_path=remote_path, dt=dt, size=size))
        items.sort(key=lambda b: b.dt, reverse=True)
        return items

    def ensure_stage(self, stage_dir: str) -> None:
        sftp = self.sftp
        try:
            sftp.listdir(stage_dir)
            return
        except IOError as exc:
            if getattr(exc, "errno", None) not in (errno.ENOENT, errno.EACCES):
                raise
        self._ensure_stage_via_sudo(stage_dir)

    def _ensure_stage_via_sudo(self, stage_dir: str) -> None:
        parts = [part for part in stage_dir.strip("/").split("/") if part]
        current = ""
        for part in parts:
            current = f"{current}/{part}" if current else f"/{part}"
            quoted = shlex.quote(current)
            self.run_sudo(f"mkdir -p {quoted} && chmod a+rx {quoted}")

    def run_sudo(self, command: str, timeout: int = 120) -> tuple[int, str]:
        """Execute a sudo command while feeding the password exactly once."""
        stdin, stdout, stderr = self.client.exec_command(
            f"sudo -S bash -lc '{command}'", get_pty=True, timeout=timeout
        )
        if self.password:
            stdin.write(self.password + "\n")
            stdin.flush()
        output = stdout.read().decode() + stderr.read().decode()
        exit_status = stdout.channel.recv_exit_status()
        return exit_status, output

    def create_remote_archive(
        self,
        base_dir: str,
        source_names: Iterable[str],
        dest_tar: str,
        timeout: int = 300,
    ) -> None:
        """Compress remote folders into a single tarball relative to base_dir."""
        sources = [name for name in source_names if name]
        if not sources:
            raise ValueError("No source paths provided for archive creation")
        safe_sources = " ".join(shlex.quote(name) for name in sources)
        quoted_base = shlex.quote(base_dir)
        quoted_dest = shlex.quote(dest_tar)
        cmd = f"tar -C {quoted_base} -chzf {quoted_dest} {safe_sources} && chmod a+r {quoted_dest}"
        code, output = self.run_sudo(cmd, timeout=timeout)
        if code != 0:
            raise RuntimeError(f"Failed to create remote archive: {output}")

    def get_remote_file_size(self, path: str) -> int:
        """Get the size of a remote file."""
        try:
            return self.sftp.stat(path).st_size
        except IOError:
            return 0

    def stage_files(self, remote_paths: Iterable[str], stage_dir: str, cancel_cb=None) -> None:
        for path in remote_paths:
            if cancel_cb and cancel_cb():
                raise DownloadCancelled()
            fname = Path(path).name
            self.run_sudo(f"cp {path} {stage_dir.rstrip('/')}/{fname} && chmod a+r {stage_dir.rstrip('/')}/{fname}")

    def download_file(self, stage_dir: str, name: str, local_path: Path, progress_cb=None, cancel_cb=None) -> None:
        remote_path = f"{stage_dir.rstrip('/')}/{name}"
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with self.sftp.file(remote_path, mode="rb") as remote, local_path.open("wb") as local:
            transferred = 0
            while True:
                if cancel_cb and cancel_cb():
                    raise DownloadCancelled()
                data = remote.read(32768)
                if not data:
                    break
                local.write(data)
                transferred += len(data)
                if progress_cb:
                    progress_cb(transferred)

    def cleanup(self, stage_dir: str, names: Iterable[str]) -> None:
        for name in names:
            remote_path = f"{stage_dir.rstrip('/')}/{name}"
            try:
                self.run_sudo(f"rm -f {remote_path}")
            except Exception:
                pass


__all__ = ["SSHClientWrapper"]
