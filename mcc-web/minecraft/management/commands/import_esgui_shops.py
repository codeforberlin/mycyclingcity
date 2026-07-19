# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from minecraft.models import MinecraftShopItem
from minecraft.services.shop_import import collect_yaml_files, import_esgui_catalog


class Command(BaseCommand):
    help = "Re-import EconomyShopGUI shop YAML files from a directory (includes subfolders)."

    def add_arguments(self, parser):
        parser.add_argument(
            "shops_dir",
            nargs="?",
            help="Path to EconomyShopGUI shops/ directory on this machine",
        )
        parser.add_argument(
            "--sections-dir",
            help="Optional path to EconomyShopGUI sections/ directory",
        )
        parser.add_argument(
            "--replace-items",
            action="store_true",
            help="Replace existing items per category",
        )

    def handle(self, *args, **options):
        shops_dir = options.get("shops_dir") or settings.MCC_MINECRAFT_ESGUI_SHOPS_DIR
        sections_dir = options.get("sections_dir") or settings.MCC_MINECRAFT_ESGUI_SECTIONS_DIR
        replace_items = options["replace_items"]

        if not shops_dir:
            self.stderr.write(
                self.style.ERROR(
                    "shops_dir required (argument or MCC_MINECRAFT_ESGUI_SHOPS_DIR in .env)"
                )
            )
            return

        shop_files = collect_yaml_files(Path(shops_dir))
        section_files = collect_yaml_files(Path(sections_dir)) if sections_dir else {}

        if not shop_files:
            self.stderr.write(self.style.ERROR(f"No shop YAML files found under {shops_dir}"))
            return

        result = import_esgui_catalog(
            shop_files=shop_files,
            section_files=section_files,
            replace_items=replace_items,
        )

        if result.errors:
            self.stderr.write(self.style.WARNING("; ".join(result.errors)))

        self.stdout.write(
            self.style.SUCCESS(
                f"Import done: {len(shop_files)} shop files, "
                f"categories +{result.categories_created}/~{result.categories_updated}, "
                f"items +{result.items_created}/~{result.items_updated}, "
                f"with loc={MinecraftShopItem.objects.exclude(esgui_item_loc='').count()}"
            )
        )
