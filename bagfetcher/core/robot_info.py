"""Robot metadata helpers for BagFetcher."""
from __future__ import annotations

import errno
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

import yaml

if TYPE_CHECKING:  # pragma: no cover - typing only
    from bagfetcher.core.sshclient import SSHClientWrapper

log = logging.getLogger(__name__)

ROBOT_PUBLIC_DIR = "/root/public"
USER_CONFIG_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/user_config.yaml"
MES_INFO_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/mes_info.json"
VERSION_INFO_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/version_info.json"
ROBOT_YAML_REMOTE_PATH = f"{ROBOT_PUBLIC_DIR}/robot.yaml"
ROBOT_INFO_ENDPOINT = "http://10.7.5.88:8080/gs-robot/info"


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
    raw_robot_info: Optional[dict] = None


def fetch_robot_info(ssh_wrapper: "SSHClientWrapper") -> RobotInfo:
    """Collect robot metadata using the on-robot API with file fallbacks."""
    info = _fetch_robot_info_via_api(ssh_wrapper) or RobotInfo()
    file_info = _fetch_robot_info_from_files(ssh_wrapper.sftp)
    info = _merge_robot_info(info, file_info)

    if info.product_id is None:
        info.product_id = info.sn
    if info.model_type is None:
        info.model_type = info.jixing
    return info


def _fetch_robot_info_via_api(ssh_wrapper: "SSHClientWrapper") -> Optional[RobotInfo]:
    cmd = f"curl -sf {ROBOT_INFO_ENDPOINT}"
    try:
        exit_code, output = ssh_wrapper.run_sudo(cmd)
    except Exception:
        return None
    if exit_code != 0 or not output:
        if exit_code != 0:
            log.debug("Robot info API returned exit code %s", exit_code)
        return None

    payload = _try_parse_json_blob(output)
    if not isinstance(payload, dict):
        log.debug("Robot info API did not return a dict payload: %s", output[:200])
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None

    info = RobotInfo()
    info.raw_robot_info = data
    info.sn = data.get("productId") or data.get("serialNumber") or info.sn
    info.product_id = data.get("productId") or info.product_id
    info.model_type = data.get("modelType") or info.model_type
    info.model_number = data.get("modelNumber") or data.get("mcuType") or info.model_number
    info.upper_pc_version = (
        data.get("softwareVersion") or data.get("appVersion") or info.upper_pc_version
    )
    return info


def _fetch_robot_info_from_files(sftp) -> RobotInfo:
    info = RobotInfo()

    mes_text = _read_remote_text(sftp, MES_INFO_REMOTE_PATH)
    if mes_text:
        mes_data = _try_parse_json_blob(mes_text)
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
        version_data = _try_parse_json_blob(version_text)
        if isinstance(version_data, dict):
            info.raw_version_info = version_data
            info.upper_pc_version = version_data.get("上位机版本") or info.upper_pc_version

    return info


def _merge_robot_info(primary: RobotInfo, fallback: RobotInfo) -> RobotInfo:
    for field in ("sn", "product_id", "model_type", "model_number", "jixing", "upper_pc_version"):
        if getattr(primary, field) is None:
            setattr(primary, field, getattr(fallback, field))
    if primary.raw_mes_info is None:
        primary.raw_mes_info = fallback.raw_mes_info
    if primary.raw_robot_yaml is None:
        primary.raw_robot_yaml = fallback.raw_robot_yaml
    if primary.raw_version_info is None:
        primary.raw_version_info = fallback.raw_version_info
    return primary


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

    exit_code, output = ssh_wrapper.run_sudo(f"cat {USER_CONFIG_REMOTE_PATH}")
    if exit_code != 0:
        raise RuntimeError(f"Unable to read user_config via sudo: {output.strip() or exit_code}")
    with open(local_path, "w", encoding="utf-8") as fh:
        fh.write(output)


def resolve_local_config_dir(robot_info: RobotInfo, host: str) -> str:
    """Resolve a local directory for storing robot-specific files."""
    base = os.path.expanduser("~/RobotBags/configs")
    key = robot_info.product_id or robot_info.sn or host or "unknown"
    safe_key = key.replace(" ", "_").replace("/", "_")
    return os.path.join(base, safe_key)


def _try_parse_json_blob(blob: str) -> Optional[dict]:
    """Attempt to parse JSON even if prompts are appended."""
    if not blob:
        return None
    blob = blob.strip()
    if not blob:
        return None
    start = blob.find("{")
    end = blob.rfind("}")
    if start != -1 and end != -1 and end > start:
        blob = blob[start : end + 1]
    try:
        return json.loads(blob)
    except json.JSONDecodeError as exc:
        log.debug("Failed to parse JSON blob (%s): %s", exc, blob[:200])
        return None


__all__ = [
    "RobotInfo",
    "ROBOT_PUBLIC_DIR",
    "USER_CONFIG_REMOTE_PATH",
    "MES_INFO_REMOTE_PATH",
    "VERSION_INFO_REMOTE_PATH",
    "ROBOT_YAML_REMOTE_PATH",
    "ROBOT_INFO_ENDPOINT",
    "fetch_robot_info",
    "download_user_config",
    "resolve_local_config_dir",
]
