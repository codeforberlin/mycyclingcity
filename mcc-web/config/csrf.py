# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    csrf.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

"""CSRF failure handling that keeps AJAX session dashboards on JSON."""

from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure


def _wants_json(request) -> bool:
    if request.GET.get("format") == "json":
        return True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return "application/json" in accept


def csrf_failure(request, reason=""):
    """
    Return JSON for AJAX/session-dashboard POSTs instead of Django's HTML 403 page.

    Without this, fetch().json() fails and the UI only shows
    "Ungültige Server-Antwort (kein JSON)."
    """
    if _wants_json(request):
        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "CSRF-Prüfung fehlgeschlagen. Bitte Seite neu laden und erneut versuchen."
                ),
                "reason": str(reason or ""),
            },
            status=403,
        )
    return django_csrf_failure(request, reason=reason)
