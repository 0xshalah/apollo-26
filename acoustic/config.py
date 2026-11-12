"""Composition-boundary configuration: environment keys, .env files, loopback binds."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Final

from acoustic.frame import KeyMaterial

LOOPBACK_HOST: Final = "127.0.0.1"
LINK_KEY_ENV: Final = "APOLLO26_LINK_KEY"
OPERATOR_KEY_ENV: Final = "APOLLO26_OPERATOR_KEY"


class ConfigErrorCode(StrEnum):
    MISSING_KEY = "MISSING_KEY"
    NON_LOOPBACK_BIND = "NON_LOOPBACK_BIND"
    INVALID_PORT = "INVALID_PORT"
    ENV_FILE = "ENV_FILE"


class ConfigError(ValueError):
    def __init__(self, code: ConfigErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


def require_loopback_host(host: str) -> str:
    """Accept only the explicit IPv4 loopback literal; reject before any socket opens."""

    if host != LOOPBACK_HOST:
        raise ConfigError(
            ConfigErrorCode.NON_LOOPBACK_BIND,
            f"listener host must be {LOOPBACK_HOST}; refusing {host!r}",
        )
    return host


def require_port(port: int) -> int:
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        raise ConfigError(ConfigErrorCode.INVALID_PORT, f"invalid TCP port {port!r}")
    return port


def parse_env_file(text: str) -> dict[str, str]:
    """Parse a minimal KEY=VALUE .env document (comments and blank lines ignored)."""

    values: dict[str, str] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise ConfigError(ConfigErrorCode.ENV_FILE, f".env line {number} lacks '='")
        name, _, value = stripped.partition("=")
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value
    return values


def merged_environment(
    process_env: Mapping[str, str], env_file: Path | None
) -> dict[str, str]:
    """Process environment wins over values from an optional local .env file."""

    merged: dict[str, str] = {}
    if env_file is not None and env_file.is_file():
        try:
            merged.update(parse_env_file(env_file.read_text(encoding="utf-8")))
        except OSError as error:
            raise ConfigError(ConfigErrorCode.ENV_FILE, f"cannot read {env_file}") from error
    merged.update({key: value for key, value in process_env.items() if key.startswith("APOLLO26_")})
    return merged


def load_key_material(env: Mapping[str, str]) -> KeyMaterial:
    """Build frame keys; fail with a clear, secret-free message when missing."""

    missing = [name for name in (LINK_KEY_ENV, OPERATOR_KEY_ENV) if not env.get(name)]
    if missing:
        raise ConfigError(
            ConfigErrorCode.MISSING_KEY,
            "missing " + ", ".join(missing)
            + " (set the environment variables or copy .env.example to .env)",
        )
    return KeyMaterial(
        link_key=env[LINK_KEY_ENV].encode("utf-8"),
        operator_key=env[OPERATOR_KEY_ENV].encode("utf-8"),
    )
