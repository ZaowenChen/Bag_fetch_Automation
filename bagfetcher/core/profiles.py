"""Profile persistence for BagFetcher."""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Iterable

from .models import Profile

PROFILE_PATH = Path.home() / "Library" / "Application Support" / "BagFetcher" / "profiles.yaml"


def load_profiles() -> list[Profile]:
    if not PROFILE_PATH.exists():
        return []
    data = yaml.safe_load(PROFILE_PATH.read_text()) or []
    return [Profile(**entry) for entry in data]


def save_profiles(profiles: Iterable[Profile]) -> None:
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    yaml.safe_dump([profile.__dict__ for profile in profiles], PROFILE_PATH.open("w"))
