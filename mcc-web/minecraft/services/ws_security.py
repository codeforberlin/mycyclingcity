import hmac
import json
from hashlib import sha256

from django.conf import settings


def sign_payload(payload: dict) -> str:
    message = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    secret = settings.MCC_MINECRAFT_WS_SHARED_SECRET.encode("utf-8")
    return hmac.new(secret, message, sha256).hexdigest()


def verify_signature(payload: dict, signature: str) -> bool:
    expected = sign_payload(payload)
    return hmac.compare_digest(expected, signature or "")
