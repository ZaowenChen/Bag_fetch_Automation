"""macOS Keychain helpers via keyring."""
from __future__ import annotations

import keyring

SERVICE_NAME = "com.yourorg.bagfetcher"


def _credential_key(user: str, host: str, port: int) -> str:
    return f"{user}@{host}:{port}"


def save_password(user: str, host: str, port: int, password: str) -> None:
    keyring.set_password(SERVICE_NAME, _credential_key(user, host, port), password)


def load_password(user: str, host: str, port: int) -> str | None:
    return keyring.get_password(SERVICE_NAME, _credential_key(user, host, port))


def delete_password(user: str, host: str, port: int) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, _credential_key(user, host, port))
    except keyring.errors.PasswordDeleteError:
        pass
