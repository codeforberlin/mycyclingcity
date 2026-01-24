import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from config.logger_utils import get_logger
from minecraft.services.scoreboard import refresh_scoreboard_snapshot


logger = get_logger("minecraft")


class Command(BaseCommand):
    help = "Continuously refresh Minecraft scoreboard snapshots."

    def handle(self, *args, **options):
        interval = settings.MCC_MINECRAFT_SNAPSHOT_INTERVAL
        update_db = settings.MCC_MINECRAFT_SNAPSHOT_UPDATE_DB_SPENDABLE
        logger.info(f"[minecraft_snapshot_worker] started interval={interval}s update_db={update_db}")
        while True:
            try:
                updated = refresh_scoreboard_snapshot()
                logger.info(f"[minecraft_snapshot_worker] cycle completed updated={updated} players at {timezone.now().isoformat()}")
            except Exception as exc:
                logger.error(f"[minecraft_snapshot_worker] cycle failed: {exc}", exc_info=True)
            time.sleep(interval)
