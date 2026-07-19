#!/usr/bin/env python3
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    prepare_lasttest_devices.py
# @note    Ensures mcc-test-001..004 exist with wheel sizes for Phase-A load test.
#
# Usage (integration PROD):
#   cd /data/appl/mcc/mcc-web
#   /data/appl/mcc/venv/bin/python3 /nas/public/dev/mycyclingcity/mcc-web/test/prepare_lasttest_devices.py
#
# Or via manage.py shell:
#   /data/appl/mcc/venv/bin/python3 manage.py shell < prepare_lasttest_devices.py

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path


def _bootstrap_django() -> None:
    if "django" in sys.modules and os.environ.get("DJANGO_SETTINGS_MODULE"):
        try:
            from django.conf import settings

            if settings.configured:
                return
        except Exception:
            pass

    repo_web = Path(__file__).resolve().parents[1]
    candidates = [
        Path("/data/appl/mcc/mcc-web"),
        repo_web,
    ]
    for root in candidates:
        manage = root / "manage.py"
        if manage.exists():
            sys.path.insert(0, str(root))
            break
    else:
        sys.path.insert(0, str(repo_web))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def main() -> int:
    _bootstrap_django()

    from api.models import Cyclist
    from iot.models import Device, DeviceConfiguration

    pairs_path = Path(__file__).with_name("lasttest_4raeder.json")
    with pairs_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    pairs = data["pairs"]

    print("=== Prepare lasttest devices ===")
    for pair in pairs:
        name = pair["device_id"]
        wheel = Decimal(str(pair["wheel_size"]))
        device, created = Device.objects.get_or_create(
            name=name,
            defaults={
                "display_name": name,
                "is_visible": True,
                "is_km_collection_enabled": True,
            },
        )
        changed = []
        if not device.is_visible:
            device.is_visible = True
            changed.append("is_visible")
        if not device.is_km_collection_enabled:
            device.is_km_collection_enabled = True
            changed.append("is_km_collection_enabled")
        if changed:
            device.save(update_fields=changed)

        cfg, _ = DeviceConfiguration.objects.get_or_create(device=device)
        if cfg.wheel_size != wheel:
            cfg.wheel_size = wheel
            cfg.save(update_fields=["wheel_size"])
            wheel_note = f"wheel→{wheel}"
        else:
            wheel_note = f"wheel={wheel}"

        action = "CREATED" if created else "OK"
        print(f"  {action} {name} {wheel_note} km_enabled={device.is_km_collection_enabled}")

    print("\n=== Verify cyclists ===")
    missing = []
    for pair in pairs:
        tag = pair["id_tag"]
        cyclist = Cyclist.objects.filter(id_tag__iexact=tag).first()
        if not cyclist:
            missing.append(tag)
            print(f"  MISSING id_tag={tag} (expected {pair.get('cyclist_name')})")
        else:
            group_names = ", ".join(cyclist.groups.values_list("name", flat=True)) or "-"
            print(f"  OK {cyclist.user_id} id_tag={cyclist.id_tag} groups={group_names}")

    if missing:
        print(f"\nERROR: missing cyclists: {', '.join(missing)}")
        return 1

    print("\nPrepare complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
