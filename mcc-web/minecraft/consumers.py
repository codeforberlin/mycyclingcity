from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.services.bridge_connection import (
    mark_bridge_connected,
    mark_bridge_disconnected,
    touch_bridge_connection,
)
from minecraft.services.group_velos import spend_group_velos_from_minecraft
from minecraft.services.shop_catalog import build_shop_catalog_payload
from minecraft.services.luckperms_sync import luckperms_group_name
from minecraft.services.team_registration import active_registrations
from minecraft.services.team_velos_query import get_team_velos_by_mc_username
from minecraft.services.ws_security import verify_signature


logger = get_logger("minecraft")


class MinecraftEventConsumer(AsyncJsonWebsocketConsumer):
    connections: dict[str, "MinecraftEventConsumer"] = {}

    async def connect(self):
        if not settings.MCC_MINECRAFT_WS_ENABLED:
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
    def _touch_connection(self, server_id: str):
        touch_bridge_connection(server_id)

    @database_sync_to_async
    def _active_mc_usernames(self) -> list[str]:
        return list(active_registrations().values_list("mc_username", flat=True))

    async def _push_all_team_mappings(self, server_id: str) -> None:
        for mc_username in await self._active_mc_usernames():
            await self.send_json(
                {
                    "type": "PUSH_TEAM_MAPPING",
                    "server_id": server_id,
                    "lp_group": luckperms_group_name(mc_username),
                    "mc_username": mc_username,
                }
            )

    async def receive_json(self, content, **kwargs):
        if not settings.MCC_MINECRAFT_WS_ENABLED:
            await self.close(code=4001)
            return

        request_id = content.get("request_id")
        signature = content.pop("signature", None)
        if not verify_signature(content, signature):
            logger.warning(
                "[minecraft_ws] invalid signature type=%s server_id=%s request_id=%s",
                content.get("type"),
                content.get("server_id"),
                request_id,
            )
            await self.send_json(self._error_response(request_id, "invalid_signature"))
            return

        server_id = content.get("server_id")
        bridge_was_new = False
        if self._server_id_allowed(server_id):
            if self.bound_server_id and self.bound_server_id != server_id:
                type(self).connections.pop(self.bound_server_id, None)
                await self._mark_disconnected(self.bound_server_id)
            bridge_was_new = server_id not in type(self).connections
            self.bound_server_id = server_id
            type(self).connections[server_id] = self
            await self._mark_connected(server_id)
            if bridge_was_new:
                await self._push_all_team_mappings(server_id)
        elif self.bound_server_id:
            await self._touch_connection(self.bound_server_id)

        event_type = content.get("type")
        if event_type in ("SPEND_GROUP_VELOS", "SPEND_COINS"):
            await self._handle_spend_group_velos(content)
            return
        if event_type == "GET_TEAM_VELOS":
            await self._handle_get_team_velos(content)
            return
        if event_type == "SYNC_SHOP_CATALOG":
            await self._handle_sync_shop_catalog(content)
            return
        if event_type == "HEARTBEAT":
            # Presence keep-alive for Admin shop-push button (updates last_seen)
            await self.send_json(self._response(content, status="ok"))
            return

        await self.send_json(self._error_response(request_id, "unsupported_event"))

    def _response(self, payload: dict, **fields) -> dict:
        response = dict(fields)
        request_id = payload.get("request_id")
        if request_id is not None:
            response["request_id"] = request_id
        return response

    def _error_response(self, request_id, error: str) -> dict:
        response = {"status": "error", "error": error}
        if request_id is not None:
            response["request_id"] = request_id
        return response

    def _server_id_allowed(self, server_id: str | None) -> bool:
        if not server_id:
            return False
        return server_id in settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS

    async def _handle_spend_group_velos(self, payload: dict):
        player = payload.get("player")
        amount = payload.get("amount")
        server_id = payload.get("server_id")

        if not player or amount is None:
            await self.send_json(self._response(payload, status="error", error="invalid_payload"))
            return

        if not self._server_id_allowed(server_id):
            await self.send_json(self._response(payload, status="error", error="server_not_allowed"))
            return

        result = await self._apply_spend(player, amount)
        if result == "group_not_found":
            await self.send_json(self._response(payload, status="error", error="group_not_found"))
            return
        if result == "invalid_amount":
            await self.send_json(self._response(payload, status="error", error="invalid_amount"))
            return

        logger.info(
            "[minecraft_ws] spend group velos player=%s amount=%s at=%s",
            player,
            amount,
            timezone.now().isoformat(),
        )
        await self.send_json(self._response(payload, status="ok"))

    async def _handle_get_team_velos(self, payload: dict):
        player = payload.get("player")
        server_id = payload.get("server_id")

        if not player:
            await self.send_json(self._response(payload, status="error", error="invalid_payload"))
            return

        if not self._server_id_allowed(server_id):
            await self.send_json(self._response(payload, status="error", error="server_not_allowed"))
            return

        data = await self._lookup_team_velos(player)
        if data is None:
            await self.send_json(self._response(payload, status="error", error="group_not_found"))
            return

        await self.send_json(self._response(payload, status="ok", **data))

    async def _handle_sync_shop_catalog(self, payload: dict):
        server_id = payload.get("server_id")

        if not self._server_id_allowed(server_id):
            await self.send_json(self._response(payload, status="error", error="server_not_allowed"))
            return

        catalog = await self._build_catalog()
        logger.info(
            "[minecraft_ws] shop catalog sync server_id=%s categories=%s at=%s",
            server_id,
            len(catalog.get("categories", [])),
            timezone.now().isoformat(),
        )
        await self.send_json(self._response(payload, status="ok", catalog=catalog))

    @database_sync_to_async
    def _apply_spend(self, player: str, amount: int):
        return spend_group_velos_from_minecraft(player, amount)

    @database_sync_to_async
    def _lookup_team_velos(self, player: str):
        return get_team_velos_by_mc_username(player)

    @database_sync_to_async
    def _build_catalog(self):
        return build_shop_catalog_payload()
