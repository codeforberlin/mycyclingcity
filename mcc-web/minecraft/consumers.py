from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from django.utils import timezone

from api.models import Cyclist
from config.logger_utils import get_logger
from minecraft.services.outbox import queue_player_coins_update
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
        if event_type == "SPEND_COINS":
            await self._handle_spend_coins(content)
            return

        await self.send_json({"status": "error", "error": "unsupported_event"})

    async def _handle_spend_coins(self, payload: dict):
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
        if result == "player_not_found":
            await self.send_json({"status": "error", "error": "player_not_found"})
            return

        logger.info(
            f"[minecraft_ws] spend coins player={player} amount={amount} at={timezone.now().isoformat()}"
        )
        await self.send_json({"status": "ok"})

    @database_sync_to_async
    def _apply_spend(self, player: str, amount: int):
        cyclist = Cyclist.objects.filter(mc_username__iexact=player).first()
        if not cyclist:
            return "player_not_found"

        coins_spendable = max(int(cyclist.coins_spendable) - int(amount), 0)
        cyclist.coins_spendable = coins_spendable
        cyclist.save(update_fields=["coins_spendable"])

        queue_player_coins_update(
            player=player,
            coins_total=int(cyclist.coins_total),
            coins_spendable=coins_spendable,
            reason="minecraft_spend",
        )
        return "ok"
