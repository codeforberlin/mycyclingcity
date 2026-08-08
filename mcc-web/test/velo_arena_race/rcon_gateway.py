# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    rcon_gateway.py
# @note    Locked RCON session for arena motion tests (no scoreboard/DB writes).

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX
    fcntl = None  # type: ignore


@dataclass(frozen=True)
class RconEndpoint:
    host: str
    port: int
    password: str


def load_rcon_endpoint() -> RconEndpoint:
    """Read RCON from environment / nearby .env files (no Django)."""
    _load_dotenv_soft()
    host = _env("MCC_MINECRAFT_RCON_HOST", "RCON_HOST", default="127.0.0.1")
    port_raw = _env("MCC_MINECRAFT_RCON_PORT", "RCON_PORT", default="25575")
    password = _env(
        "MCC_MINECRAFT_RCON_PASSWORD",
        "RCON_PASSWORD",
        default="",
    )
    if not password:
        raise RuntimeError(
            "RCON-Passwort fehlt (MCC_MINECRAFT_RCON_PASSWORD / RCON_PASSWORD)."
        )
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise RuntimeError(f"Ungültiger RCON-Port: {port_raw!r}") from exc
    return RconEndpoint(host=host, port=port, password=password)


def _env(*keys: str, default: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return default


def _load_dotenv_soft() -> None:
    candidates = [
        Path(__file__).resolve().parents[2] / ".env",  # mcc-web/.env
        Path("/data/appl/mcc/.env"),
        Path("/data/appl/mcc/mcc-web/.env"),
        Path.cwd() / ".env",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
        except OSError:
            continue
        break


class RconGateway:
    """
    Persistent RCON connection with an exclusive file lock.

    Purpose: reduce collisions with the MCC scoreboard worker when both talk
    to the same Minecraft RCON port. This gateway never issues scoreboard or
    database-related commands by itself – callers must keep that contract.
    """

    def __init__(
        self,
        endpoint: RconEndpoint,
        *,
        lock_path: Path,
        lock_timeout_seconds: float = 2.0,
    ):
        self.endpoint = endpoint
        self.lock_path = lock_path
        self.lock_timeout_seconds = lock_timeout_seconds
        self._mcr = None
        self._command: Callable[[str], str] | None = None
        self._lock_fh = None
        self.lock_wait_ms_total = 0.0
        self.lock_wait_count = 0
        self.command_count = 0

    def connect(self) -> None:
        try:
            from mcrcon import MCRcon  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Paket 'mcrcon' fehlt. Installieren mit: pip install mcrcon"
            ) from exc

        mcr = MCRcon(
            self.endpoint.host,
            self.endpoint.password,
            port=self.endpoint.port,
        )
        try:
            mcr.connect()
        except Exception as exc:
            raise ConnectionError(
                f"RCON-Verbindung fehlgeschlagen "
                f"({self.endpoint.host}:{self.endpoint.port}): {exc}"
            ) from exc
        self._mcr = mcr
        self._command = mcr.command

    def close(self) -> None:
        if self._mcr is not None:
            try:
                self._mcr.disconnect()
            except Exception:
                pass
        self._mcr = None
        self._command = None

    def __enter__(self) -> "RconGateway":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Acquire the cross-process RCON lock for a short critical section."""
        if fcntl is None:
            yield
            return

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.lock_path, "a+", encoding="utf-8")
        deadline = time.monotonic() + max(0.0, self.lock_timeout_seconds)
        waited_ms = 0.0
        try:
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        fh.close()
                        raise TimeoutError(
                            f"RCON-Lock Timeout nach "
                            f"{self.lock_timeout_seconds:.1f}s "
                            f"({self.lock_path})"
                        )
                    time.sleep(0.01)
                    waited_ms += 10.0
            if waited_ms:
                self.lock_wait_ms_total += waited_ms
                self.lock_wait_count += 1
            self._lock_fh = fh
            yield
        finally:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                fh.close()
            except Exception:
                pass
            self._lock_fh = None

    def run(self, command: str) -> str:
        if self._command is None:
            raise RuntimeError("RCON nicht verbunden")
        # Refuse scoreboard mutations from this test harness.
        lowered = command.strip().lower()
        if lowered.startswith("scoreboard "):
            raise RuntimeError(
                f"Scoreboard-Befehle sind in diesem Test verboten: {command!r}"
            )
        with self.locked():
            response = self._command(command)
            self.command_count += 1
            return response or ""
