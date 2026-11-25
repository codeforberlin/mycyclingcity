# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from api.models import Group, GroupType
from luanti.models import LuantiShopPurchaseCredit
from luanti.services.purchase_credit_transfer import (
    transfer_all_credits_from_groups,
    transfer_purchase_credits_to_group,
)


@pytest.fixture
def groups(db):
    gtype, _ = GroupType.objects.get_or_create(name="School")
    src = Group.objects.create(name="SrcLeaf", group_type=gtype, is_visible=True)
    dst = Group.objects.create(name="DstLeaf", group_type=gtype, is_visible=True)
    other = Group.objects.create(name="OtherLeaf", group_type=gtype, is_visible=True)
    return {"src": src, "dst": dst, "other": other}


@pytest.mark.django_db
def test_transfer_selected_merges_same_item(groups):
    a = LuantiShopPurchaseCredit.objects.create(
        group=groups["src"], item_name="mcl_core:dirt", quantity=3
    )
    LuantiShopPurchaseCredit.objects.create(
        group=groups["dst"], item_name="mcl_core:dirt", quantity=2
    )
    LuantiShopPurchaseCredit.objects.create(
        group=groups["src"], item_name="mcl_core:stone", quantity=5
    )
    result = transfer_purchase_credits_to_group(
        target_group=groups["dst"],
        credit_ids=[a.pk],
    )
    assert result.transferred_rows == 1
    assert result.total_quantity == 3
    dest = LuantiShopPurchaseCredit.objects.get(
        group=groups["dst"], item_name="mcl_core:dirt"
    )
    assert dest.quantity == 5
    assert not LuantiShopPurchaseCredit.objects.filter(pk=a.pk).exists()
    assert LuantiShopPurchaseCredit.objects.get(
        group=groups["src"], item_name="mcl_core:stone"
    ).quantity == 5


@pytest.mark.django_db
def test_transfer_all_from_group(groups):
    LuantiShopPurchaseCredit.objects.create(
        group=groups["src"], item_name="mcl_core:dirt", quantity=1
    )
    LuantiShopPurchaseCredit.objects.create(
        group=groups["src"], item_name="mcl_core:stone", quantity=4
    )
    LuantiShopPurchaseCredit.objects.create(
        group=groups["other"], item_name="mcl_core:dirt", quantity=9
    )
    result = transfer_all_credits_from_groups(
        target_group=groups["dst"],
        source_group_ids=[groups["src"].pk],
    )
    assert result.transferred_rows == 2
    assert result.total_quantity == 5
    assert not LuantiShopPurchaseCredit.objects.filter(group=groups["src"]).exists()
    assert LuantiShopPurchaseCredit.objects.filter(group=groups["other"]).count() == 1
    assert LuantiShopPurchaseCredit.objects.filter(group=groups["dst"]).count() == 2


@pytest.mark.django_db
def test_transfer_skips_same_group(groups):
    row = LuantiShopPurchaseCredit.objects.create(
        group=groups["dst"], item_name="mcl_core:dirt", quantity=2
    )
    result = transfer_purchase_credits_to_group(
        target_group=groups["dst"],
        credit_ids=[row.pk],
    )
    assert result.skipped_same_group == 1
    assert result.transferred_rows == 0
    assert LuantiShopPurchaseCredit.objects.get(pk=row.pk).quantity == 2