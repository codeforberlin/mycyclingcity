# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from mgmt.views_deployment import list_kind_backups


@pytest.mark.django_db
def test_list_and_download_world_backups(tmp_path, settings, client: Client):
    settings.BASE_DIR = tmp_path
    # Force development path branch
    import os

    os.environ.pop("MCC_ENV", None)

    root = tmp_path / "data" / "backups"
    (root / "database").mkdir(parents=True)
    (root / "minecraft").mkdir(parents=True)
    (root / "luanti").mkdir(parents=True)
    db = root / "database" / "db_backup_20260101_120000.sqlite3"
    mc = root / "minecraft" / "mc_world_20260101_120000.tar.gz"
    lt = root / "luanti" / "luanti_world_20260101_120000.tar.gz"
    db.write_bytes(b"db-archive")
    mc.write_bytes(b"minecraft-archive")
    lt.write_bytes(b"luanti-archive")

    # Point DATA_DIR at tmp data root parent... DATA_DIR is tmp_path/data when BASE_DIR=tmp_path
    settings.DATA_DIR = tmp_path / "data"

    assert any(r["filename"] == db.name for r in list_kind_backups("database"))
    assert any(r["filename"] == mc.name for r in list_kind_backups("minecraft"))
    assert any(r["filename"] == lt.name for r in list_kind_backups("luanti"))

    User = get_user_model()
    su = User.objects.create_superuser("backup_su", "b@example.com", "x")
    client.force_login(su)

    page = client.get(reverse("admin:mgmt_backup_control"))
    assert page.status_code == 200
    assert mc.name.encode() in page.content
    assert lt.name.encode() in page.content
    assert b"bk-tab" in page.content
    assert b"backup-catalog-data" in page.content

    r_mc = client.get(
        reverse(
            "admin:mgmt_backup_download",
            kwargs={"kind": "minecraft", "filename": mc.name},
        )
    )
    assert r_mc.status_code == 200
    assert b"minecraft-archive" in b"".join(r_mc.streaming_content)

    r_lt = client.get(
        reverse(
            "admin:mgmt_backup_download",
            kwargs={"kind": "luanti", "filename": lt.name},
        )
    )
    assert r_lt.status_code == 200
    assert b"luanti-archive" in b"".join(r_lt.streaming_content)

    # Wrong type / unknown kind rejected
    bad = client.get(
        reverse(
            "admin:mgmt_backup_download",
            kwargs={"kind": "minecraft", "filename": "not-a-backup.txt"},
        )
    )
    assert bad.status_code == 404

    bad_kind = client.get(
        reverse(
            "admin:mgmt_backup_download",
            kwargs={"kind": "other", "filename": mc.name},
        )
    )
    assert bad_kind.status_code == 404

    # Delete selected minecraft archive
    del_resp = client.post(
        reverse("admin:mgmt_backup_delete"),
        data='{"kind":"minecraft","filename":"%s"}' % mc.name,
        content_type="application/json",
    )
    assert del_resp.status_code == 200
    body = del_resp.json()
    assert body["success"] is True
    assert not mc.exists()

    # Reject unknown type
    bad_del = client.post(
        reverse("admin:mgmt_backup_delete"),
        data='{"kind":"minecraft","filename":"nope.txt"}',
        content_type="application/json",
    )
    assert bad_del.status_code == 404
