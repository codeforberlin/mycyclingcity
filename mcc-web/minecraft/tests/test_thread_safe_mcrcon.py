# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import threading

import pytest


@pytest.mark.unit
def test_thread_safe_mcrcon_init_from_worker_thread():
    """Upstream MCRcon.__init__ raises in non-main threads; ours must not."""
    errors: list[BaseException] = []

    def worker():
        try:
            from minecraft.services.thread_safe_mcrcon import ThreadSafeMCRcon

            mcr = ThreadSafeMCRcon("127.0.0.1", "secret", port=25575, timeout=2)
            assert mcr.host == "127.0.0.1"
            assert mcr.timeout == 2
        except BaseException as exc:  # noqa: BLE001 — capture for main thread
            errors.append(exc)

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5)
    assert not t.is_alive()
    assert errors == []
