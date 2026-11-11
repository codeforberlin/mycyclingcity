# Copyright (c) 2026 SAI-Lab / MyCyclingCity / ADFC Berlin
# SPDX-License-Identifier: AGPL-3.0-or-later

from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from luanti.services.shop_plan_ghost import (
    plan_ghost_hint_for_item_name,
    plan_ghost_hint_html,
)
from luanti.services.shop_icon import registry_item_map

from luanti.models import (
    LuantiAccount,
    LuantiArenaLane,
    LuantiArenaMotionSettings,
    LuantiBridgeConnection,
    LuantiCityPreset,
    LuantiIntegrationConfig,
    LuantiPendingCommand,
    LuantiPlayerInventory,
    LuantiProtectedRegion,
    LuantiRegisteredItem,
    LuantiSession,
    LuantiShopCategory,
    LuantiShopCategoryLabel,
    LuantiShopItem,
    LuantiShopItemLabel,
    LuantiPlanMaterializeTransaction,
    LuantiShopPurchaseCredit,
    LuantiShopTransaction,
    LuantiStation,
    LuantiWaitingPlayer,
)
from luanti.services.session_control import clear_account_inventory


@admin.register(LuantiIntegrationConfig)
class LuantiIntegrationConfigAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "default_session_minutes",
        "session_end_warning_seconds",
        "updated_at",
    )

    def has_add_permission(self, request):
        return not LuantiIntegrationConfig.objects.exists()


@admin.register(LuantiBridgeConnection)
class LuantiBridgeConnectionAdmin(admin.ModelAdmin):
    list_display = ("server_id", "is_connected", "connected_at", "last_seen_at")
    readonly_fields = ("server_id", "is_connected", "connected_at", "last_seen_at")


@admin.register(LuantiPendingCommand)
class LuantiPendingCommandAdmin(admin.ModelAdmin):
    list_display = ("id", "server_id", "created_at", "delivered_at")
    readonly_fields = ("server_id", "payload", "created_at", "delivered_at")
    list_filter = ("delivered_at",)


@admin.register(LuantiAccount)
class LuantiAccountAdmin(admin.ModelAdmin):
    list_display = (
        "login_name",
        "id_tag",
        "password_display",
        "password_provisioned",
        "is_active",
        "default_mode",
        "assigned_to_group_link",
        "active_wallet_link",
        "wallet_mode",
        "sort_order",
    )
    list_filter = ("is_active", "default_mode", "wallet_mode", "password_provisioned")
    search_fields = ("login_name", "id_tag", "display_name")
    readonly_fields = ("password_last_set_at", "created_at", "updated_at")
    autocomplete_fields = ("assigned_to_group", "active_wallet")

    class Media:
        css = {"all": ("admin/css/group_admin.css",)}
        js = ("admin/js/cyclist_group_link.js",)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        group_url_pattern = reverse("admin:api_group_change", args=[0]).replace(
            "/0/", "/{id}/"
        )
        link_label = str(_("TOP-Gruppe öffnen →"))
        for field_name, link_id in (
            ("assigned_to_group", "luanti-account-home-group-link"),
            ("active_wallet", "luanti-account-wallet-link"),
        ):
            if field_name not in form.base_fields:
                continue
            widget = form.base_fields[field_name].widget
            widget.attrs["data-mcc-group-url-pattern"] = group_url_pattern
            widget.attrs["data-mcc-group-link-label"] = link_label
            widget.attrs["data-mcc-nav-link-id"] = link_id
        return form

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "active_wallet":
            kwargs["required"] = False
            kwargs["empty_label"] = _("—")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description=_("Heimat-Gruppe"), ordering="assigned_to_group__name")
    def assigned_to_group_link(self, obj):
        group = obj.assigned_to_group
        if not group:
            return "—"
        url = reverse("admin:api_group_change", args=[group.pk])
        return format_html(
            '<a href="{}" class="cyclist-group-admin-link" target="_blank" '
            'rel="noopener noreferrer">{}</a>',
            url,
            group.name,
        )

    @admin.display(description=_("Aktives Wallet"), ordering="active_wallet__name")
    def active_wallet_link(self, obj):
        group = obj.active_wallet
        if not group:
            return "—"
        url = reverse("admin:api_group_change", args=[group.pk])
        return format_html(
            '<a href="{}" class="cyclist-group-admin-link" target="_blank" '
            'rel="noopener noreferrer">{}</a>',
            url,
            group.name,
        )

    @admin.display(description=_("Login-Passwort"))
    def password_display(self, obj):
        return "********" if obj.login_password else "—"

    def get_exclude(self, request, obj=None):
        if not request.user.is_superuser:
            return ["login_password"]
        return super().get_exclude(request, obj)


@admin.register(LuantiSession)
class LuantiSessionAdmin(admin.ModelAdmin):
    list_display = ("login_name", "mode", "status", "source", "timestamp_start", "ends_at")
    list_filter = ("status", "mode", "source")
    search_fields = ("login_name",)


@admin.register(LuantiPlayerInventory)
class LuantiPlayerInventoryAdmin(admin.ModelAdmin):
    list_display = ("account_admin_link", "mode", "revision", "updated_at")
    list_display_links = ("mode",)
    list_filter = ("mode",)
    actions = ("action_clear_inventory",)
    search_fields = ("account__login_name",)

    class Media:
        css = {"all": ("admin/css/group_admin.css",)}
        js = ("admin/js/cyclist_group_link.js",)

    def get_form(self, request, obj=None, **kwargs):
        from mgmt.admin import _mcc_attach_admin_nav_link

        form = super().get_form(request, obj, **kwargs)
        if "account" in form.base_fields:
            _mcc_attach_admin_nav_link(
                form.base_fields["account"],
                obj.account_id if obj else None,
                label=_("Account öffnen →"),
                link_id="luanti-player-inventory-account-link",
                change_url_name="admin:luanti_luantiaccount_change",
            )
        return form

    @admin.display(description=_("Account"), ordering="account__login_name")
    def account_admin_link(self, obj):
        account = obj.account
        if not account:
            return "—"
        url = reverse("admin:luanti_luantiaccount_change", args=[account.pk])
        label = account.display_name or account.login_name
        return format_html(
            '<a href="{}" class="cyclist-group-admin-link" target="_blank" '
            'rel="noopener noreferrer">{}</a>',
            url,
            label,
        )

    @admin.action(description=_("Inventar leeren (DB + online)"))
    def action_clear_inventory(self, request, queryset):
        n = 0
        for inv in queryset.select_related("account"):
            clear_account_inventory(inv)
            n += 1
        self.message_user(
            request,
            _("Inventar geleert: %(n)s Eintrag/Einträge. Revision erhöht; "
              "bei aktiver Session gleicher Modus auch live geleert.")
            % {"n": n},
            messages.SUCCESS,
        )


class LuantiShopItemInline(admin.TabularInline):
    model = LuantiShopItem
    extra = 0


class LuantiShopItemLabelInline(admin.TabularInline):
    model = LuantiShopItemLabel
    extra = 0
    fields = ("language_code", "display_name")


class LuantiShopCategoryLabelInline(admin.TabularInline):
    model = LuantiShopCategoryLabel
    extra = 0
    fields = ("language_code", "display_name")


@admin.register(LuantiShopCategory)
class LuantiShopCategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "enabled", "sort_order")
    search_fields = ("name", "slug", "labels__display_name")
    inlines = [LuantiShopCategoryLabelInline, LuantiShopItemInline]


@admin.register(LuantiShopItem)
class LuantiShopItemAdmin(admin.ModelAdmin):
    list_display = (
        "item_name",
        "display_name",
        "category",
        "buy_price_velos",
        "admin_plan_ghost_column",
        "enabled",
        "sort_order",
    )
    list_filter = ("enabled", "category")
    actions = ("action_move_to_category",)
    inlines = [LuantiShopItemLabelInline]
    readonly_fields = ("admin_plan_ghost_readonly",)
    search_fields = (
        "item_name",
        "display_name",
        "labels__display_name",
        "category__name",
        "category__slug",
    )
    search_help_text = _(
        "Suche in allen Shop-Artikeln: Itemstring, Anzeigename oder Kategoriename."
    )
    list_per_page = 50
    show_full_result_count = True
    ordering = ("category__sort_order", "category__name", "sort_order", "item_name")

    class Media:
        css = {"all": ("admin/css/luanti_shop_plan_ghost.css",)}

    def _registry_map_for_objects(self, objects) -> dict:
        names = list({o.item_name for o in objects})
        return registry_item_map(names) if names else {}

    def changelist_view(self, request, extra_context=None):
        self._plan_ghost_reg_map = {}
        response = super().changelist_view(request, extra_context=extra_context)
        if (
            request.method == "GET"
            and hasattr(response, "context_data")
            and (cl := response.context_data.get("cl")) is not None
        ):
            self._plan_ghost_reg_map = self._registry_map_for_objects(cl.result_list)
        return response

    @admin.display(description=_("Plan-Hologramm"))
    def admin_plan_ghost_column(self, obj: LuantiShopItem):
        reg_map = getattr(self, "_plan_ghost_reg_map", None) or {}
        if not reg_map:
            reg_map = registry_item_map([obj.item_name])
        hint = plan_ghost_hint_for_item_name(obj.item_name, reg_map)
        return plan_ghost_hint_html(hint)

    @admin.display(description=_("Plan-Hologramm (Registry)"))
    def admin_plan_ghost_readonly(self, obj: LuantiShopItem):
        if not obj or not obj.item_name:
            return "—"
        reg_map = registry_item_map([obj.item_name])
        hint = plan_ghost_hint_for_item_name(obj.item_name, reg_map)
        detail = hint.get("plan_ghost_detail") or ""
        return format_html(
            "{}<br><span class=\"muted\" style=\"font-size:0.85em;\">{}</span>",
            plan_ghost_hint_html(hint),
            detail,
        )

    def get_fields(self, request, obj=None):
        fields = list(super().get_fields(request, obj))
        if "admin_plan_ghost_readonly" not in fields:
            fields.append("admin_plan_ghost_readonly")
        return fields

    @admin.action(description=_("In andere Kategorie verschieben…"))
    def action_move_to_category(self, request, queryset):
        """Bulk move shop items to another category (confirmation + unique-safe)."""
        if request.POST.get("post") != "yes":
            n_selected = queryset.count()
            context = {
                **self.admin_site.each_context(request),
                "title": _("Shop-Artikel in andere Kategorie verschieben"),
                "queryset": queryset,
                "selected_count": n_selected,
                "action_checkbox_name": ACTION_CHECKBOX_NAME,
                "admin_action_name": self.action_move_to_category.__name__,
                "select_across": request.POST.get("select_across", "0"),
                "index": request.POST.get("index", "0"),
                "categories": LuantiShopCategory.objects.order_by("sort_order", "slug"),
                "cancel_url": reverse("admin:luanti_luantishopitem_changelist"),
            }
            return TemplateResponse(
                request,
                "admin/luanti/luantishopitem/move_category_confirmation.html",
                context,
            )

        changelist_url = reverse("admin:luanti_luantishopitem_changelist")

        raw_pk = (request.POST.get("target_category_pk") or "").strip()
        if not raw_pk.isdigit():
            self.message_user(
                request,
                _("Ungültige Ziel-Kategorie."),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(changelist_url)

        try:
            target = LuantiShopCategory.objects.get(pk=int(raw_pk))
        except LuantiShopCategory.DoesNotExist:
            self.message_user(
                request,
                _("Ziel-Kategorie existiert nicht."),
                level=messages.ERROR,
            )
            return HttpResponseRedirect(changelist_url)

        moved = 0
        skipped_same = 0
        skipped_conflict = 0
        for item in queryset.select_related("category"):
            if item.category_id == target.pk:
                skipped_same += 1
                continue
            conflict = (
                LuantiShopItem.objects.filter(category=target, item_name=item.item_name)
                .exclude(pk=item.pk)
                .exists()
            )
            if conflict:
                skipped_conflict += 1
                continue
            item.category = target
            item.save(update_fields=["category"])
            moved += 1

        if moved:
            self.message_user(
                request,
                _("%(n)s Artikel nach „%(cat)s“ verschoben.")
                % {"n": moved, "cat": target.name},
                messages.SUCCESS,
            )
        if skipped_same:
            self.message_user(
                request,
                _(
                    "%(n)s Artikel übersprungen (waren bereits in der Ziel-Kategorie)."
                )
                % {"n": skipped_same},
                messages.INFO,
            )
        if skipped_conflict:
            self.message_user(
                request,
                _(
                    "%(n)s Artikel übersprungen: gleicher Itemstring existiert "
                    "bereits in der Ziel-Kategorie (Eindeutigkeit)."
                )
                % {"n": skipped_conflict},
                messages.WARNING,
            )
        if not moved and not skipped_same and not skipped_conflict:
            self.message_user(
                request,
                _("Keine Artikel ausgewählt."),
                level=messages.WARNING,
            )

        return HttpResponseRedirect(changelist_url)


@admin.register(LuantiShopPurchaseCredit)
class LuantiShopPurchaseCreditAdmin(admin.ModelAdmin):
    list_display = ("group", "item_name", "quantity")


@admin.register(LuantiShopTransaction)
class LuantiShopTransactionAdmin(admin.ModelAdmin):
    """Audit of shop buys/sells. Plan-Kauf must have velos_delta=0; Kauf with a negative
    delta means the client sent planning=false (or omitted it)."""

    list_display = (
        "created_at",
        "login_name",
        "side",
        "item_name",
        "quantity",
        "velos_delta",
        "group",
        "client_tx_id",
    )
    list_filter = ("side",)
    search_fields = ("login_name", "item_name", "client_tx_id")
    date_hierarchy = "created_at"
    readonly_fields = (
        "client_tx_id",
        "side",
        "login_name",
        "group",
        "item_name",
        "quantity",
        "velos_delta",
        "created_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(LuantiPlanMaterializeTransaction)
class LuantiPlanMaterializeTransactionAdmin(admin.ModelAdmin):
    """Plan-pool Velos debit when holograms convert to real blocks."""

    list_display = (
        "created_at",
        "login_name",
        "region",
        "group",
        "velos_delta",
        "world",
        "x",
        "y",
        "z",
        "client_tx_id",
    )
    list_filter = ("region",)
    search_fields = ("login_name", "client_tx_id", "world")
    date_hierarchy = "created_at"
    readonly_fields = (
        "client_tx_id",
        "region",
        "group",
        "world",
        "x",
        "y",
        "z",
        "velos_delta",
        "login_name",
        "created_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(LuantiRegisteredItem)
class LuantiRegisteredItemAdmin(admin.ModelAdmin):
    list_display = (
        "item_name",
        "kind",
        "drawtype",
        "plan_ghost_status",
        "plan_ghost_checked_at",
        "updated_at",
    )
    search_fields = ("item_name", "description")
    list_filter = ("kind", "plan_ghost_status")
    readonly_fields = ("plan_ghost_checked_at", "updated_at")


@admin.register(LuantiCityPreset)
class LuantiCityPresetAdmin(admin.ModelAdmin):
    """Hidden from app index — use custom Preset-Editor GUI instead."""

    list_display = ("slug", "name", "category", "enabled", "is_system", "last_run_at", "last_run_success")
    list_filter = ("category", "enabled", "is_system")
    search_fields = ("slug", "name")

    def has_module_permission(self, request):
        return False


@admin.register(LuantiProtectedRegion)
class LuantiProtectedRegionAdmin(admin.ModelAdmin):
    """Hidden from app index — use custom Geschützte Regionen GUI instead."""

    list_display = ("region_id", "display_name", "world", "protect_build", "enabled")

    def has_module_permission(self, request):
        return False


@admin.register(LuantiArenaMotionSettings)
class LuantiArenaMotionSettingsAdmin(admin.ModelAdmin):
    list_display = ("pk", "enabled", "default_speed", "updated_at")

    def has_add_permission(self, request):
        return not LuantiArenaMotionSettings.objects.exists()


@admin.register(LuantiArenaLane)
class LuantiArenaLaneAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled", "sort_order", "assigned_account")


@admin.register(LuantiStation)
class LuantiStationAdmin(admin.ModelAdmin):
    list_display = ("name", "hostname", "is_active", "default_account", "last_seen_at")
    readonly_fields = ("api_key", "last_seen_at", "reported_config", "last_error")


@admin.register(LuantiWaitingPlayer)
class LuantiWaitingPlayerAdmin(admin.ModelAdmin):
    list_display = ("login_name", "account", "server_id", "first_seen_at", "last_seen_at")
    readonly_fields = ("login_name", "account", "server_id", "first_seen_at", "last_seen_at")
    search_fields = ("login_name",)
