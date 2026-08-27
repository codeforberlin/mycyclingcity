# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    test_backup_config.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""Tests for MccBackupConfig conf export."""

import pytest
from django.core.management import call_command

from mgmt.models_backup import MccBackupConfig
from mgmt.services.backup_config import render_backup_conf, write_backup_conf


@pytest.mark.django_db
def test_render_backup_conf_includes_required_fields():
    cfg = MccBackupConfig.get_config()
    cfg.ssh_host = "cbm-srv2"
    cfg.ssh_user = "mccweb"
    cfg.ssh_port = 22
    cfg.remote_backup_dir = "/home/mccweb/backup"
    cfg.ssh_key = ""
    cfg.save()
    text = render_backup_conf(cfg)
    assert 'SSH_HOST="cbm-srv2"' in text
    assert 'SSH_USER="mccweb"' in text
    assert 'SSH_PORT="22"' in text
    assert 'REMOTE_BACKUP_DIR="/home/mccweb/backup"' in text
    assert "SSH_KEY=" not in text


@pytest.mark.django_db
def test_render_includes_optional_ssh_key():
    cfg = MccBackupConfig.get_config()
    cfg.ssh_key = "/home/roland/.ssh/id_ed25519"
    cfg.save()
    text = render_backup_conf(cfg)
    assert 'SSH_KEY="/home/roland/.ssh/id_ed25519"' in text


@pytest.mark.django_db
def test_write_backup_conf(tmp_path, settings):
    settings.MCC_BACKUP_CONF_PATH = str(tmp_path / "backup_mcc.conf")
    cfg = MccBackupConfig.get_config()
    cfg.ssh_host = "cbm-srv2"
    cfg.ssh_user = "mccweb"
    cfg.remote_backup_dir = "/home/mccweb/backup"
    cfg.save()
    path = write_backup_conf(cfg)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert 'SSH_USER="mccweb"' in content


@pytest.mark.django_db
def test_run_backup_mcc_dry_write(tmp_path, settings):
    settings.MCC_BACKUP_CONF_PATH = str(tmp_path / "backup_mcc.conf")
    call_command("run_backup_mcc", dry_write_conf=True)
    assert (tmp_path / "backup_mcc.conf").exists()
