# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.core.management.base import BaseCommand

from luanti.services.shop_labels import (
    import_english_labels_from_locales,
    import_german_labels_from_locales,
    sync_labels_from_registry,
)


class Command(BaseCommand):
    help = "Sync Luanti shop item labels (DE from registry, EN from Mineclonia locales)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lang",
            choices=("de", "en"),
            default="de",
            help="Language to sync (de=registry or locales, en=locale files)",
        )
        parser.add_argument(
            "--source",
            choices=("registry", "locales", "both"),
            default="registry",
            help="For --lang de: registry descriptions, Mineclonia .de.tr, or both",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Overwrite existing labels (default: only empty/missing)",
        )
        parser.add_argument(
            "--categories",
            action="store_true",
            help="Sync shop category tab titles (DE/EN slug defaults) instead of items",
        )

    def handle(self, *args, **options):
        overwrite = bool(options["overwrite"])
        if options["categories"]:
            from luanti.services.shop_labels import sync_category_labels_defaults

            result = sync_category_labels_defaults(
                overwrite=overwrite,
                only_empty=not overwrite,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Categories: created={result.created} updated={result.updated} "
                    f"skipped={result.skipped}"
                )
            )
            return
        lang = options["lang"]
        if lang == "de":
            source = options["source"]
            if source in ("locales", "both"):
                loc_result = import_german_labels_from_locales(
                    overwrite=overwrite,
                    only_empty=not overwrite,
                )
                if loc_result.errors:
                    self.stderr.write(self.style.ERROR(",".join(loc_result.errors)))
                self.stdout.write(
                    self.style.SUCCESS(
                        f"DE (locales): created={loc_result.created} updated={loc_result.updated} "
                        f"skipped={loc_result.skipped} no_en={loc_result.no_en_source} "
                        f"no_de={loc_result.no_de_match}"
                    )
                )
            if source in ("registry", "both"):
                result = sync_labels_from_registry(
                    language_code="de",
                    overwrite=overwrite,
                    only_empty=not overwrite,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"DE (registry): created={result.created} updated={result.updated} "
                        f"skipped={result.skipped} missing_registry={result.missing_registry}"
                    )
                )
            return
        result = import_english_labels_from_locales(
            overwrite=overwrite,
            only_empty=not overwrite,
        )
        if result.errors:
            self.stderr.write(self.style.ERROR(",".join(result.errors)))
        self.stdout.write(
            self.style.SUCCESS(
                f"EN: created={result.created} updated={result.updated} "
                f"skipped={result.skipped} no_de={result.no_de_text} no_en={result.no_en_match}"
            )
        )
