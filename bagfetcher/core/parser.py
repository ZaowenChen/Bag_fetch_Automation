"""Utilities for parsing pasted SSH connection blocks."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

SSH_RE = re.compile(r"^ssh\s+([A-Za-z0-9._-]+)@([A-Za-z0-9._-]+)(?:\s+-p\s+(\d+))?", re.I)
BAG_RE = re.compile(
    r"^GS_(\d{4})-(\d{2})-(\d{2})-(\d{2})-(\d{2})-(\d{2})_\d+\.bag$",
)


@dataclass(slots=True)
class PasteResult:
    user: str
    host: str
    port: int
    password: str


class ParseError(ValueError):
    """Raised when a paste block cannot be parsed."""


def parse_paste(block: str) -> PasteResult:
    """Parse a multi-line SSH paste block."""
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        raise ParseError("Nothing to parse")

    first = lines[0]
    match = SSH_RE.match(first)
    if not match:
        raise ParseError("First line must look like 'ssh user@host -p 1234'")

    user, host, port_str = match.groups()
    user = user or "gaussian"
    host = host or ""
    if not host:
        raise ParseError("Missing host in ssh line")
    port = int(port_str) if port_str else 22

    password = lines[1] if len(lines) > 1 else ""

    return PasteResult(user=user, host=host, port=port, password=password)


def bag_name_to_datetime(name: str):
    """Extract a datetime tuple from a bag name."""
    match = BAG_RE.match(name)
    if not match:
        return None
    year, month, day, hour, minute, second = map(int, match.groups())
    from datetime import datetime

    return datetime(year, month, day, hour, minute, second)


__all__ = ["parse_paste", "PasteResult", "ParseError", "bag_name_to_datetime"]
