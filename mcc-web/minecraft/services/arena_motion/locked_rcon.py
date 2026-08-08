# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    locked_rcon.py
# @note    Persistent RCON with shared file lock (coexists with bridge worker).

from __future__ import annotations

import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from django.conf import settings

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore

from config.logger_utils import get_logger

logger = get_logger("minecraft")


def default_rcon_lock_path() -> Path:
    configured = getattr(settings, "MCC_MINECRAFT_RCON_LOCK_PATH", "") or ""
    if configured:
        return Path(configured)
    data_dir = Path(getattr(settings, "DATA_DIR", Path("/tmp")))
    return data_dir / "tmp" / "mcc-minecraft-rcon.lock"


@contextmanager
def rcon_file_lock(
    lock_path: Path | None = None,
    *,
    timeout_seconds: float | None = None,
) -> Iterator[None]:
    """Exclusive cross-process lock around RCON critical sections."""
    path = lock_path or default_rcon_lock_path()
    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else float(getattr(settings, "MCC_MINECRAFT_RCON_LOCK_TIMEOUT", 2.0))
    )
    if fcntl is None:
        yield
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a+", encoding="utf-8")
    deadline = time.monotonic() + max(0.0, timeout)
    try:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    fh.close()
                    raise TimeoutError(
                        f"RCON-Lock Timeout nach {timeout:.1f}s ({path})"
                    )
                time.sleep(0.01)
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


class LockedRconGateway:
    """Persistent MCRcon session; every command holds the shared file lock."""

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        lock_path: Path | None = None,
        lock_timeout_seconds: float | None = None,
        forbid_scoreboard: bool = True,
    ):
        self.host = host or settings.MCC_MINECRAFT_RCON_HOST
        self.port = int(port or settings.MCC_MINECRAFT_RCON_PORT)
        self.password = password if password is not None else settings.MCC_MINECRAFT_RCON_PASSWORD
        self.lock_path = lock_path or default_rcon_lock_path()
        self.lock_timeout_seconds = (
            lock_timeout_seconds
            if lock_timeout_seconds is not None
            else float(getattr(settings, "MCC_MINECRAFT_RCON_LOCK_TIMEOUT", 2.0))
        )
        self.forbid_scoreboard = forbid_scoreboard
        self._mcr = None
        self._command: Callable[[str], str] | None = None
        self.command_count = 0

    def connect(self) -> None:
        from mcrcon import MCRcon

        mcr = MCRcon(self.host, self.password, port=self.port)
        mcr.connect()
        self._mcr = mcr
        self._command = mcr.command
        logger.info(
            "[arena_motion] RCON connected %s:%s lock=%s",
            self.host,
            self.port,
            self.lock_path,
        )

    def close(self) -> None:
        if self._mcr is not None:
            try:
                self._mcr.disconnect()
            except Exception:
                pass
        self._mcr = None
        self._command = None

    def __enter__(self) -> "LockedRconGateway":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def run(self, command: str) -> str:
        if self._command is None:
            raise RuntimeError("RCON nicht verbunden")
        lowered = command.strip().lower()
        if self.forbid_scoreboard and lowered.startswith("scoreboard "):
            raise RuntimeError(f"Scoreboard-Befehle im Motion-Pfad verboten: {command!r}")
        with rcon_file_lock(self.lock_path, timeout_seconds=self.lock_timeout_seconds):
            try:
                response = self._command(command)
            except (BrokenPipeError, ConnectionError, OSError) as exc:
                # Persistent RCON dies under load; reconnect once and retry.
                logger.warning("[arena_motion] RCON reconnect after %s", exc)
                self.close()
                self.connect()
                if self._command is None:
                    raise
                response = self._command(command)
            self.command_count += 1
            return response or ""
