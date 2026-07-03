from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.services.group_velos import spend_group_velos_from_minecraft
from minecraft.services.ws_security import verify_signature


logger = get_logger("minecraft")


class MinecraftEventConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not settings.MCC_MINECRAFT_WS_ENABLED:
            await self.close(code=4001)
            return
        await self.accept()

    async def receive_json(self, content, **kwargs):
        if not settings.MCC_MINECRAFT_WS_ENABLED:
            await self.close(code=4001)
            return

        signature = content.pop("signature", None)
        if not verify_signature(content, signature):
            await self.send_json({"status": "error", "error": "invalid_signature"})
            return

        event_type = content.get("type")
        if event_type in ("SPEND_GROUP_VELOS", "SPEND_COINS"):
            await self._handle_spend_group_velos(content)
            return

        await self.send_json({"status": "error", "error": "unsupported_event"})

    async def _handle_spend_group_velos(self, payload: dict):
        player = payload.get("player")
        amount = payload.get("amount")
        server_id = payload.get("server_id")

        if not player or amount is None:
            await self.send_json({"status": "error", "error": "invalid_payload"})
            return

        if server_id not in settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS:
            await self.send_json({"status": "error", "error": "server_not_allowed"})
            return

        result = await self._apply_spend(player, amount)
        if result == "group_not_found":
            await self.send_json({"status": "error", "error": "group_not_found"})
            return
        if result == "invalid_amount":
            await self.send_json({"status": "error", "error": "invalid_amount"})
            return

        logger.info(
            "[minecraft_ws] spend group velos player=%s amount=%s at=%s",
            player,
            amount,
            timezone.now().isoformat(),
        )
        await self.send_json({"status": "ok"})

    @database_sync_to_async
    def _apply_spend(self, player: str, amount: int):
        return spend_group_velos_from_minecraft(player, amount)
