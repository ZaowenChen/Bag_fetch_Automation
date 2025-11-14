"""Robot metadata helpers for BagFetcher."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import errno
import json
import os

import yaml

ROBOT_PUBLIC_DIR = "/root/public"
USER_CONFIG_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/user_config.yaml"
MES_INFO_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/mes_info.json"
VERSION_INFO_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/version_info.json"
ROBOT_YAML_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/robot.yaml"


@dataclass
class RobotInfo:
    sn: Optional[str] = None
    product_id: Optional[str] = None
    model_type: Optional[str] = None
    model_number: Optional[str] = None
    jixing: Optional[str] = None
    upper_pc_version: Optional[str] = None

    raw_mes_info: Optional[dict] = None
    raw_version_info: Optional[dict] = None
    raw_robot_yaml: Optional[dict] = None


def _read_remote_text(sftp, remote_path: str) -> Optional[str]:
    """
    Try to read a remote text file via sftp.
    Return None if file does not exist or any IO error occurs.
    """
    try:
        with sftp.file(remote_path, "r") as remote:
            return remote.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_robot_info(sftp) -> RobotInfo:
    """Collect robot metadata from known files on the robot."""
    info = RobotInfo()

    mes_text = _read_remote_text(sftp, MES_INFO_REMOTE_PATH)
    if mes_text:
        try:
            mes_data = json.loads(mes_text)
        except json.JSONDecodeError:
            mes_data = None
        if isinstance(mes_data, dict):
            info.raw_mes_info = mes_data
            info.sn = mes_data.get("sn") or info.sn
            info.model_number = mes_data.get("model_number") or info.model_number
            info.jixing = mes_data.get("jixing") or info.jixing

    robot_yaml_text = _read_remote_text(sftp, ROBOT_YAML_REMOTE_PATH)
    if robot_yaml_text:
        try:
            robot_yaml = yaml.safe_load(robot_yaml_text)
        except yaml.YAMLError:
            robot_yaml = None
        if isinstance(robot_yaml, dict):
            info.raw_robot_yaml = robot_yaml
            info.model_type = robot_yaml.get("model_type") or info.jixing or info.model_type
            info.product_id = robot_yaml.get("product_id") or info.sn or info.product_id

    version_text = _read_remote_text(sftp, VERSION_INFO_REMOTE_PATH)
    if version_text:
        try:
            version_data = json.loads(version_text)
        except json.JSONDecodeError:
            version_data = None
        if isinstance(version_data, dict):
            info.raw_version_info = version_data
            info.upper_pc_version = version_data.get("上位机版本") or info.upper_pc_version

    if info.product_id is None:
        info.product_id = info.sn
    if info.model_type is None:
        info.model_type = info.jixing

    return info


def download_user_config(sftp, local_path: str, ssh_wrapper=None) -> None:
    """
    Download /root/public/user_config.yaml to local_path.
    """
    try:
        sftp.get(USER_CONFIG_REMOTE_PATH, local_path)
        return
    except OSError as exc:
        if not ssh_wrapper or getattr(exc, "errno", None) not in (errno.EACCES, errno.EPERM):
            raise

    # Fallback: copy using sudo to a temp location under /root/public/tmp
    temp_remote = f"{ROBOT_PUBLIC_DIR}/tmp/bagfetcher_user_config.yaml"
    try:
        ssh_wrapper.run_sudo(
            f"mkdir -p {ROBOT_PUBLIC_DIR}/tmp && "
            f"cp {USER_CONFIG_REMOTE_PATH} {temp_remote} && chmod a+r {temp_remote}"
        )
        sftp.get(temp_remote, local_path)
    finally:
        try:
            ssh_wrapper.run_sudo(f"rm -f {temp_remote}")
        except Exception:
            pass


def resolve_local_config_dir(robot_info: RobotInfo, host: str) -> str:
    """Resolve a local directory for storing robot-specific files."""
    base = os.path.expanduser("~/RobotBags/configs")
    key = robot_info.product_id or robot_info.sn or host or "unknown"
    safe_key = key.replace(" ", "_").replace("/", "_")
    return os.path.join(base, safe_key)


__all__ = [
    "RobotInfo",
    "ROBOT_PUBLIC_DIR",
    "USER_CONFIG_REMOTE_PATH",
    "MES_INFO_REMOTE_PATH",
    "VERSION_INFO_REMOTE_PATH",
    "ROBOT_YAML_REMOTE_PATH",
    "fetch_robot_info",
    "download_user_config",
    "resolve_local_config_dir",
]
