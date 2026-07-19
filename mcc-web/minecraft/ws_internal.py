# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import hmac
import json

from django.conf import settings

from minecraft.consumers import MinecraftEventConsumer


async def _read_body(receive):
    body = b""
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body += message.get("body", b"")
        if not message.get("more_body"):
            break
    return body


async def _send_json_response(send, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def handle_push_shop_http(scope, receive, send) -> None:
    if scope.get("method") != "POST":
        await _send_json_response(send, 405, {"error": "method_not_allowed"})
        return

    headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers", [])}
    provided_secret = headers.get("x-mcc-internal-secret", "")
    expected_secret = settings.MCC_MINECRAFT_WS_SHARED_SECRET
    if not hmac.compare_digest(provided_secret, expected_secret):
        await _send_json_response(send, 403, {"error": "forbidden"})
        return

    try:
        payload = json.loads((await _read_body(receive)).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        await _send_json_response(send, 400, {"error": "invalid_json"})
        return

    server_id = payload.get("server_id")
    if not server_id or server_id not in settings.MCC_MINECRAFT_WS_ALLOWED_SERVER_IDS:
        await _send_json_response(send, 400, {"error": "invalid_server_id"})
        return

    consumer = MinecraftEventConsumer.connections.get(server_id)
    if consumer is None:
        await _send_json_response(send, 404, {"error": "bridge_not_connected"})
        return

    request_id = payload.get("request_id") or "internal-push"
    await consumer.send_json(
        {
            "type": "REQUEST_CATALOG_SYNC",
            "request_id": request_id,
            "server_id": server_id,
        }
    )
    await _send_json_response(send, 200, {"status": "ok", "request_id": request_id})


def build_http_application(django_asgi_app):
    async def combined_http_application(scope, receive, send):
        if scope["type"] != "http":
            return

        path = scope.get("path", "")
        if path == "/internal/minecraft/push-shop/":
            await handle_push_shop_http(scope, receive, send)
            return

        await django_asgi_app(scope, receive, send)

    return combined_http_application
