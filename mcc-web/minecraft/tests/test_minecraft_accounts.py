# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from api.tests.conftest import GroupFactory
from minecraft.models import (
    MinecraftIntegrationConfig,
    MinecraftPlayAccount,
    MinecraftVanillaOpLog,
)
from minecraft.services.account_admin import (
    ACCOUNT_BUILDER,
    ACCOUNT_PLAYER,
    create_play_account,
    deactivate_builder,
    delete_play_account,
    list_account_dtos,
    list_limbo_players_without_account,
    reactivate_builder,
    register_builder_group,
    top_group_for,
    update_play_account,
)
from minecraft.services.preset_permissions import (
    user_can_manage_minecraft_accounts,
    user_can_manage_minecraft_operators,
    user_can_manage_player_sessions,
)
from minecraft.services.team_registration import register_group_for_minecraft
from minecraft.services.vanilla_op import (
    VanillaOpError,
    grant_op,
    invalidate_ops_cache,
    list_operators,
    read_ops_from_file,
    revoke_op,
)


User = get_user_model()


def _add_perm(user, model, codename):
    content_type = ContentType.objects.get_for_model(model)
    perm = Permission.objects.get(content_type=content_type, codename=codename)
    user.user_permissions.add(perm)
    return User.objects.get(pk=user.pk)


@pytest.fixture
def account_manager(db):
    user = User.objects.create_user(
        username="acct_mgr",
        password="secret",
        is_staff=True,
    )
    return _add_perm(user, MinecraftIntegrationConfig, "manage_minecraft_accounts")


@pytest.fixture
def op_manager(db):
    user = User.objects.create_user(
        username="op_mgr",
        password="secret",
        is_staff=True,
    )
    return _add_perm(user, MinecraftIntegrationConfig, "manage_minecraft_operators")


@pytest.fixture
def player_manager(db):
    user = User.objects.create_user(
        username="player_mgr2",
        password="secret",
        is_staff=True,
    )
    return _add_perm(user, MinecraftIntegrationConfig, "manage_player_sessions")


@pytest.fixture
def play_account(db):
    return MinecraftPlayAccount.objects.create(
        id_tag="Arena1",
        short_name="Arena1",
        ms_username="PlayerOne",
        display_name="Arena 1",
        sort_order=1,
        is_active=True,
    )


@pytest.fixture
def builder_registration(db):
    top = GroupFactory(name="TOP Venue", mc_username="")
    leaf = GroupFactory(name="Team Alpha", mc_username="team_alpha", parent=top)
    return register_group_for_minecraft(leaf)


@pytest.mark.unit
@pytest.mark.django_db
class TestAccountPermissionHelpers:
    def test_account_perm(self, account_manager, player_manager):
        assert user_can_manage_minecraft_accounts(account_manager)
        assert not user_can_manage_minecraft_operators(account_manager)
        assert not user_can_manage_minecraft_accounts(player_manager)
        assert user_can_manage_player_sessions(player_manager)

    def test_op_perm(self, op_manager, player_manager):
        assert user_can_manage_minecraft_operators(op_manager)
        assert not user_can_manage_minecraft_operators(player_manager)


@pytest.mark.unit
class TestVanillaOpParsing:
    def test_read_ops_json(self, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        payload = [
            {
                "uuid": "11111111-1111-1111-1111-111111111111",
                "name": "AdminGuy",
                "level": 4,
                "bypassesPlayerLimit": True,
            },
            {"name": "BuilderOp", "level": 2},
        ]
        (tmp_path / "ops.json").write_text(json.dumps(payload), encoding="utf-8")
        invalidate_ops_cache()
        ops = list_operators(use_cache=False)
        assert [o.name for o in ops] == ["AdminGuy", "BuilderOp"]
        assert ops[0].level == 4
        assert ops[0].bypasses_player_limit is True

    def test_missing_ops_json(self, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        invalidate_ops_cache()
        with pytest.raises(VanillaOpError):
            read_ops_from_file()

    @patch("minecraft.services.vanilla_op.rcon_client.run_command", return_value="Made AdminGuy a server operator")
    def test_grant_op_audits(self, mock_rcon, db, op_manager, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "ops.json").write_text("[]", encoding="utf-8")
        invalidate_ops_cache()
        ok, detail = grant_op("AdminGuy", user=op_manager, account_type="PLAYER", account_ref="PLAYER:1")
        assert ok
        assert "operator" in detail.lower() or detail
        log = MinecraftVanillaOpLog.objects.get()
        assert log.action == "op"
        assert log.player_name == "AdminGuy"
        assert log.ok is True
        assert log.created_by_id == op_manager.pk
        mock_rcon.assert_called_once_with("op AdminGuy")

    @patch("minecraft.services.vanilla_op.rcon_client.run_command", return_value="Made AdminGuy no longer a server operator")
    def test_revoke_op_audits(self, mock_rcon, db, op_manager):
        ok, _ = revoke_op("AdminGuy", user=op_manager)
        assert ok
        log = MinecraftVanillaOpLog.objects.get()
        assert log.action == "deop"
        mock_rcon.assert_called_once_with("deop AdminGuy")

    def test_rejects_invalid_name(self, db):
        with pytest.raises(VanillaOpError):
            grant_op("bad name")


@pytest.mark.unit
@pytest.mark.django_db
class TestAccountFacade:
    def test_list_includes_player_and_builder(self, play_account, builder_registration, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "ops.json").write_text(
            json.dumps([{"name": "PlayerOne", "level": 4}]),
            encoding="utf-8",
        )
        invalidate_ops_cache()
        dtos = list_account_dtos(ops=list_operators(use_cache=False))
        types = {d.account_type for d in dtos}
        assert ACCOUNT_PLAYER in types
        assert ACCOUNT_BUILDER in types
        player = next(d for d in dtos if d.account_type == ACCOUNT_PLAYER)
        assert player.is_vanilla_op is True
        builder = next(d for d in dtos if d.account_type == ACCOUNT_BUILDER)
        assert builder.top_group_name == "TOP Venue"

    def test_top_group_for_leaf(self, builder_registration):
        top = top_group_for(builder_registration.group)
        assert top is not None
        assert top.parent_id is None
        assert top.name == "TOP Venue"

    def test_assign_top_to_play(self, play_account, builder_registration):
        top = top_group_for(builder_registration.group)
        update_play_account(play_account, {"assigned_to_group_id": top.pk})
        play_account.refresh_from_db()
        assert play_account.assigned_to_group_id == top.pk
        filtered = list_account_dtos(account_type=ACCOUNT_PLAYER, top_group_id=top.pk, ops=[])
        assert len(filtered) == 1
        assert filtered[0].pk == play_account.pk

    def test_create_and_delete_play(self, db):
        acc = create_play_account(
            {"short_name": "Arena9", "ms_username": "SlotNine", "display_name": "Arena 9"}
        )
        assert acc.pk
        assert acc.id_tag == "Arena9"
        delete_play_account(acc)
        assert not MinecraftPlayAccount.objects.filter(short_name="Arena9").exists()

    def test_update_session_unlimited(self, play_account):
        update_play_account(play_account, {"session_unlimited": True})
        play_account.refresh_from_db()
        assert play_account.session_unlimited is True
        dto = list_account_dtos(account_type=ACCOUNT_PLAYER, ops=[])[0]
        assert dto.session_unlimited is True
        update_play_account(play_account, {"session_unlimited": False})
        play_account.refresh_from_db()
        assert play_account.session_unlimited is False

    def test_register_deactivate_reactivate_builder(self, db):
        top = GroupFactory(name="TOP Bau", mc_username="")
        leaf = GroupFactory(name="Team Bau", mc_username="team_bau", parent=top)
        reg = register_builder_group(leaf.pk)
        assert reg.is_active is True
        deactivate_builder(reg.pk)
        reg.refresh_from_db()
        assert reg.is_active is False
        reactivate_builder(reg.pk)
        reg.refresh_from_db()
        assert reg.is_active is True


@pytest.mark.unit
@pytest.mark.django_db
class TestAccountAdminView:
    def test_create_player_via_post(self, client, account_manager, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "ops.json").write_text("[]", encoding="utf-8")
        invalidate_ops_cache()
        client.force_login(account_manager)
        url = reverse("admin:minecraft_accounts")
        response = client.post(
            url,
            {
                "action": "create_player",
                "short_name": "ArenaNew",
                "ms_username": "NewPlayer",
            },
        )
        assert response.status_code == 302
        assert MinecraftPlayAccount.objects.filter(short_name="ArenaNew").exists()

    @patch(
        "minecraft.account_views.list_limbo_players_without_account",
        return_value=(["StrangerOne"], ""),
    )
    def test_limbo_unknown_listed(self, _mock_limbo, client, account_manager, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "ops.json").write_text("[]", encoding="utf-8")
        invalidate_ops_cache()
        client.force_login(account_manager)
        response = client.get(reverse("admin:minecraft_accounts"))
        assert response.status_code == 200
        assert b"StrangerOne" in response.content
        assert b"Limbo ohne Account" in response.content

    def test_list_limbo_filters_known(self, play_account):
        with patch(
            "minecraft.services.velocity_rcon.glist_server",
            return_value="[limbo] (2): PlayerOne, StrangerTwo",
        ):
            names, err = list_limbo_players_without_account()
        assert err == ""
        assert names == ["StrangerTwo"]
        assert "PlayerOne" not in names

    def test_adopt_limbo_as_builder_new_group(self, db):
        from minecraft.services.account_admin import adopt_limbo_as_builder

        top = GroupFactory(name="TOP Adopt", mc_username="")
        leaf = GroupFactory(name="Team Adopt", mc_username="team_adopt", parent=top)
        with patch(
            "minecraft.services.playerdata_uuid.resolve_ms_uuid_for_login",
            return_value="069a79f4-44e9-4726-a5fe-8c18a9833bd8",
        ):
            reg = adopt_limbo_as_builder("LimboBuilder", target=f"group:{leaf.pk}")
        assert reg.ms_username == "LimboBuilder"
        assert reg.ms_uuid == "069a79f4-44e9-4726-a5fe-8c18a9833bd8"
        assert reg.is_active is True

    def test_create_play_fills_uuid_from_usercache(self, tmp_path, settings, db):
        import json

        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "usercache.json").write_text(
            json.dumps(
                [
                    {
                        "name": "CachePlayer",
                        "uuid": "069a79f444e94726a5fe8c18a9833bd8",
                    }
                ]
            ),
            encoding="utf-8",
        )
        with patch(
            "minecraft.services.playerdata_uuid.lookup_ms_uuid_via_mojang",
            return_value=None,
        ):
            acc = create_play_account({"short_name": "SlotC", "ms_username": "CachePlayer"})
        assert acc.ms_uuid == "069a79f4-44e9-4726-a5fe-8c18a9833bd8"

    def test_player_manager_denied(self, client, player_manager):
        client.force_login(player_manager)
        url = reverse("admin:minecraft_accounts")
        response = client.get(url)
        assert response.status_code in (302, 403)

    def test_account_manager_ok(self, client, account_manager, play_account, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "ops.json").write_text("[]", encoding="utf-8")
        invalidate_ops_cache()
        client.force_login(account_manager)
        url = reverse("admin:minecraft_accounts")
        response = client.get(url)
        assert response.status_code == 200
        assert b"Arena1" in response.content or b"Arena 1" in response.content

    @patch("minecraft.account_views.grant_op")
    def test_op_requires_op_perm(self, mock_grant, client, account_manager, play_account):
        client.force_login(account_manager)
        url = reverse("admin:minecraft_accounts")
        response = client.post(
            url,
            {"action": "op", "account_type": "PLAYER", "pk": play_account.pk},
        )
        assert response.status_code == 302
        mock_grant.assert_not_called()

    @patch("minecraft.account_views.grant_op")
    def test_op_manager_can_op(self, mock_grant, client, op_manager, play_account, tmp_path, settings):
        settings.MCC_MINECRAFT_PAPER_DIR = str(tmp_path)
        (tmp_path / "ops.json").write_text("[]", encoding="utf-8")
        mock_grant.return_value = (True, "ok")
        client.force_login(op_manager)
        url = reverse("admin:minecraft_accounts")
        response = client.post(
            url,
            {"action": "op", "account_type": "PLAYER", "pk": play_account.pk},
        )
        assert response.status_code == 302
        mock_grant.assert_called_once()
