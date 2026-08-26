# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import hmac

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

from config.logger_utils import get_logger
from luanti.services.bridge_connection import (
    mark_bridge_connected,
    mark_bridge_disconnected,
    touch_bridge_connection,
)
from luanti.services.http_security import verify_signature

logger = get_logger("luanti")


class LuantiEventConsumer(AsyncJsonWebsocketConsumer):
    connections: dict[str, "LuantiEventConsumer"] = {}
    pending_commands: list[dict] = []

    async def connect(self):
        if not settings.MCC_LUANTI_WS_ENABLED:
            await self.close(code=4001)
            return
        self.bound_server_id = None
        await self.accept()

    async def disconnect(self, close_code):
        if self.bound_server_id:
            type(self).connections.pop(self.bound_server_id, None)
            await self._mark_disconnected(self.bound_server_id)

    @database_sync_to_async
    def _mark_connected(self, server_id: str):
        mark_bridge_connected(server_id)

    @database_sync_to_async
    def _mark_disconnected(self, server_id: str):
        mark_bridge_disconnected(server_id)

    @database_sync_to_async
    def _touch(self, server_id: str):
        touch_bridge_connection(server_id)

    def _response(self, content: dict, **extra) -> dict:
        out = {"status": "ok", "type": content.get("type")}
        out.update(extra)
        return out

    async def receive_json(self, content, **kwargs):
        if not isinstance(content, dict):
            await self.send_json({"status": "error", "error": "invalid_json"})
            return
        event_type = str(content.get("type") or "")
        server_id = str(content.get("server_id") or "")
        signature = str(content.get("signature") or "")
        payload = {k: v for k, v in content.items() if k != "signature"}
        auth_token = str(payload.get("auth_token") or "")
        secret = settings.MCC_LUANTI_HTTP_SHARED_SECRET or ""
        signed_ok = verify_signature(payload, signature)
        token_ok = bool(auth_token) and hmac.compare_digest(auth_token, secret)
        if not signed_ok and not token_ok:
            await self.send_json({"status": "error", "error": "invalid_signature"})
            return
        payload.pop("auth_token", None)
        allowed = set(settings.MCC_LUANTI_ALLOWED_SERVER_IDS or [])
        if allowed and server_id not in allowed:
            await self.send_json({"status": "error", "error": "server_id_not_allowed"})
            return
        if server_id:
            if self.bound_server_id != server_id:
                self.bound_server_id = server_id
                type(self).connections[server_id] = self
                await self._mark_connected(server_id)
            else:
                await self._touch(server_id)

        if event_type == "HEARTBEAT":
            await self.send_json(self._response(content))
            return
        if event_type == "ACK_COMMAND":
            await self.send_json(self._response(content))
            return
        await self.send_json(self._response(content, note="ignored"))

    @classmethod
    async def push_to_server(cls, server_id: str, message: dict) -> bool:
        consumer = cls.connections.get(server_id)
        if not consumer:
            return False
        await consumer.send_json(message)
        return True

    @classmethod
    def push_to_all_sync(cls, message: dict) -> int:
        """Push to WS bridges; if none connected, enqueue for HTTP poll."""
        count = 0
        for server_id, consumer in list(cls.connections.items()):
            try:
                from asgiref.sync import async_to_sync

                async_to_sync(consumer.send_json)(message)
                count += 1
            except Exception as exc:
                logger.warning("luanti ws push failed server=%s error=%s", server_id, exc)
        if count == 0:
            from luanti.services.command_queue import enqueue_command

            enqueue_command(message if isinstance(message, dict) else {"raw": message})
            # Treat queued delivery as success so Admin shows a positive result.
            return 1
        return count
