# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shop category admin: save must not require posting every shop item row."""

from html.parser import HTMLParser

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from luanti.models import LuantiShopCategory, LuantiShopItem

User = get_user_model()


class _AdminFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self._select_name = None
        self._select_value = ""
        self._option_value = ""
        self._option_selected = False
        self._textarea_name = None
        self._textarea_data = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input":
            name = attrs.get("name")
            if not name or attrs.get("type") in {"submit", "file", "button"}:
                return
            if attrs.get("type") == "checkbox":
                if "checked" in attrs:
                    self.fields[name] = attrs.get("value", "on")
                return
            self.fields[name] = attrs.get("value", "")
        elif tag == "select":
            self._select_name = attrs.get("name")
            self._select_value = ""
        elif tag == "option" and self._select_name:
            self._option_value = attrs.get("value", "")
            self._option_selected = "selected" in attrs
        elif tag == "textarea":
            self._textarea_name = attrs.get("name")
            self._textarea_data = []

    def handle_data(self, data):
        if self._textarea_name:
            self._textarea_data.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self._select_name and self._option_selected:
            self._select_value = self._option_value
        elif tag == "select" and self._select_name:
            self.fields[self._select_name] = self._select_value
            self._select_name = None
        elif tag == "textarea" and self._textarea_name:
            self.fields[self._textarea_name] = "".join(self._textarea_data)
            self._textarea_name = None


def _post_data_from_change_page(html: str) -> dict:
    parser = _AdminFormParser()
    parser.feed(html)
    data = dict(parser.fields)
    data["_save"] = "Save"
    return data


@pytest.mark.django_db
def test_shop_category_change_post_with_many_items_not_500():
    su = User.objects.create_superuser(
        username="shop-cat-admin",
        email="shop-cat@example.com",
        password="testpass123",
    )
    client = Client()
    client.force_login(su)

    cat = LuantiShopCategory.objects.create(
        slug="stairs-many",
        name="Stairs Many",
        enabled=True,
        sort_order=0,
    )
    for i in range(125):
        LuantiShopItem.objects.create(
            category=cat,
            item_name=f"mcl_stairs:item_{i}",
            buy_price_velos=1,
            stack_size=1,
            sort_order=i,
        )

    url = reverse("admin:luanti_luantishopcategory_change", args=[cat.pk])
    get_resp = client.get(url)
    assert get_resp.status_code == 200
    html = get_resp.content.decode()
    assert "items-" not in html and "luantishopitem_set-" not in html

    post_resp = client.post(url, _post_data_from_change_page(html))
    assert post_resp.status_code in (200, 302)
    assert post_resp.status_code != 500

    cat.refresh_from_db()
    assert cat.name == "Stairs Many"