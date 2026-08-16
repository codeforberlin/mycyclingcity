# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    thread_safe_mcrcon.py
# @note    MCRcon without SIGALRM — safe under Gunicorn gthread workers.

from __future__ import annotations

import socket
import ssl

from mcrcon import MCRcon, MCRconException


class ThreadSafeMCRcon(MCRcon):
    """
    Drop-in MCRcon that uses socket timeouts instead of ``signal.SIGALRM``.

    Upstream ``mcrcon`` calls ``signal.signal`` / ``signal.alarm`` in ``__init__``
    and ``_read``. That only works in the main thread; Gunicorn ``gthread`` runs
    Django requests in worker threads →
    ``ValueError: signal only works in main thread of the main interpreter``.
    """

    def __init__(self, host, password, port=25575, tlsmode=0, timeout=5):
        self.host = host
        self.password = password
        self.port = port
        self.tlsmode = tlsmode
        self.timeout = timeout
        # Do not call MCRcon.__init__ (registers SIGALRM).

    def connect(self):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(float(self.timeout))

        if self.tlsmode > 0:
            ctx = ssl.create_default_context()
            if self.tlsmode > 1:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self.socket = ctx.wrap_socket(self.socket, server_hostname=self.host)

        self.socket.connect((self.host, self.port))
        self._send(3, self.password)

    def _read(self, length):
        data = b""
        while len(data) < length:
            try:
                chunk = self.socket.recv(length - len(data))
            except socket.timeout as exc:
                raise MCRconException("Connection timeout error") from exc
            if not chunk:
                raise MCRconException("Connection closed")
            data += chunk
        return data
