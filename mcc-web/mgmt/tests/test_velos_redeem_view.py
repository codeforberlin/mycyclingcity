# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import Client
from django.urls import reverse

from api.models import CyclistVelosRedemption
from api.tests.conftest import CyclistFactory, GroupFactory, UserFactory
from mgmt.velos_redeem_views import user_can_redeem_velos


@pytest.mark.django_db
class TestVelosRedeemView:
    def _grant_redeem_perm(self, user):
        perm = Permission.objects.get(
            codename='redeem_velos',
            content_type=ContentType.objects.get_for_model(CyclistVelosRedemption),
        )
        user.user_permissions.add(perm)

    def test_permission_helper(self):
        user = UserFactory(is_staff=True)
        assert user_can_redeem_velos(user) is False
        self._grant_redeem_perm(user)
        user = type(user).objects.get(pk=user.pk)
        assert user_can_redeem_velos(user) is True

    def test_view_requires_permission(self):
        user = UserFactory(is_staff=True)
        client = Client()
        client.force_login(user)
        response = client.get(reverse('admin:api_velos_redeem'))
        assert response.status_code == 403

    def test_view_redeem_partial(self):
        top_group = GroupFactory(name='Top School', parent=None)
        leaf = GroupFactory(name='Class 1a', parent=top_group)
        cyclist = CyclistFactory(user_id='redeem-ui-user', velos_balance=400)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('admin:api_velos_redeem'),
            {
                'action': 'redeem',
                'top_group': top_group.id,
                'identifier': 'redeem-ui-user',
                'amount': '200',
                'note': 'Counter',
                'external_currency': 'Wuhlis',
            },
        )
        assert response.status_code == 200
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 200
        assert cyclist.velos_redemptions.count() == 1
        redemption = cyclist.velos_redemptions.first()
        assert redemption.velos_redeemed == 200
        assert redemption.external_currency == 'Wuhlis'

    def test_view_prefills_top_group(self):
        top_a = GroupFactory(name='Top A', parent=None)
        top_b = GroupFactory(name='Top B', parent=None)
        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get(reverse('admin:api_velos_redeem'))
        assert response.status_code == 200
        assert top_a.name in response.content.decode()

        response = client.get(reverse('admin:api_velos_redeem'), {'top_group': top_b.id})
        assert response.status_code == 200
        assert str(top_b.id) in response.content.decode()

    def test_lookup_api(self):
        top_group = GroupFactory(name='Lookup Top', parent=None)
        leaf = GroupFactory(name='Lookup Leaf', parent=top_group)
        cyclist = CyclistFactory(user_id='lookup-user', velos_balance=320)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('admin:api_velos_redeem_lookup'),
            {'top_group': top_group.id, 'identifier': 'lookup-user'},
        )
        assert response.status_code == 200
        data = response.json()
        assert data['user_id'] == 'lookup-user'
        assert data['velos_balance'] == 320

    def test_view_redeem_by_cyclist_list(self):
        top_group = GroupFactory(name='List Top School', parent=None)
        leaf = GroupFactory(name='List Class 1a', parent=top_group)
        cyclist = CyclistFactory(user_id='list-select-user', velos_balance=300)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('admin:api_velos_redeem'),
            {
                'action': 'redeem',
                'top_group': top_group.id,
                'cyclist_id': cyclist.id,
                'amount': '100',
            },
        )
        assert response.status_code == 200
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 200

    def test_view_lists_cyclists_for_top_group(self):
        top_group = GroupFactory(name='Dropdown Top', parent=None)
        leaf = GroupFactory(name='Dropdown Leaf', parent=top_group)
        cyclist = CyclistFactory(user_id='dropdown-user', velos_balance=150)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.get(
            reverse('admin:api_velos_redeem'),
            {'top_group': top_group.id},
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert 'dropdown-user' in content
        assert f'value="{cyclist.id}"' in content

    def test_cyclist_outside_top_group_not_found(self):
        top_group = GroupFactory(name='Allowed Top', parent=None)
        other_top = GroupFactory(name='Other Top', parent=None)
        leaf = GroupFactory(name='Other Leaf', parent=other_top)
        cyclist = CyclistFactory(user_id='outside-user', velos_balance=100)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('admin:api_velos_redeem'),
            {
                'action': 'redeem',
                'top_group': top_group.id,
                'identifier': 'outside-user',
                'amount': '50',
            },
        )
        assert response.status_code == 200
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 100

    def test_view_redeem_player_session(self):
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

        config = MinecraftIntegrationConfig.get_config()
        config.player_velos_per_minute = 20
        config.player_min_velos = 300
        config.save()

        top_group = GroupFactory(name='MC Top School', parent=None)
        leaf = GroupFactory(name='MC Class 1a', parent=top_group)
        cyclist = CyclistFactory(user_id='mc-session-user', velos_balance=500)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('admin:api_velos_redeem'),
            {
                'action': 'redeem',
                'top_group': top_group.id,
                'identifier': 'mc-session-user',
                'amount': '300',
                'product': 'player_session',
                'note': 'Arena counter',
            },
        )
        assert response.status_code == 200
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 200
        entry = MinecraftSessionWaitlistEntry.objects.get(cyclist=cyclist)
        assert entry.source == MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM
        assert entry.velos_cost == 300
        assert entry.duration_minutes == 15
        assert entry.status == MinecraftSessionWaitlistEntry.STATUS_WAITING

    def test_view_redeem_builder_session(self):
        from minecraft.models import MinecraftIntegrationConfig, MinecraftSessionWaitlistEntry

        config = MinecraftIntegrationConfig.get_config()
        config.player_velos_per_minute = 20
        config.player_min_velos = 300
        config.save()

        top_group = GroupFactory(name='MC Builder Top', parent=None)
        leaf = GroupFactory(name='MC Builder Class', parent=top_group)
        cyclist = CyclistFactory(user_id='mc-builder-ui', velos_balance=700)
        cyclist.groups.set([leaf])

        user = UserFactory(is_staff=True, is_superuser=True)
        client = Client()
        client.force_login(user)

        response = client.post(
            reverse('admin:api_velos_redeem'),
            {
                'action': 'redeem',
                'top_group': top_group.id,
                'identifier': 'mc-builder-ui',
                'amount': '600',
                'product': 'builder_session',
                'note': 'Bau counter',
            },
        )
        assert response.status_code == 200
        cyclist.refresh_from_db()
        assert cyclist.velos_balance == 100
        entry = MinecraftSessionWaitlistEntry.objects.get(cyclist=cyclist)
        assert entry.queue_type == MinecraftSessionWaitlistEntry.QUEUE_BUILDER
        assert entry.source == MinecraftSessionWaitlistEntry.SOURCE_VELOS_REDEEM
        assert entry.duration_minutes == 30
        assert entry.status == MinecraftSessionWaitlistEntry.STATUS_WAITING
