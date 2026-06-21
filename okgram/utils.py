"""
Utility helpers: body signing, uuid/id generation, json handling,
media id <-> code conversion, etc.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import random
import string
import time
import uuid
from typing import Any, Dict, Optional, Union
from urllib.parse import quote

from . import config


# ---------------------------------------------------------------------------
# id / uuid generation
# ---------------------------------------------------------------------------
def generate_uuid(prefix: str = "", suffix: str = "") -> str:
    """Generate a standard UUID4, e.g. for _uuid, phone_id, client_session_id"""
    return f"{prefix}{uuid.uuid4()}{suffix}"


def generate_android_device_id(seed: Optional[str] = None) -> str:
    """
    Generate an android device id of the form 'android-<16 hex>'.
    If a seed is provided (e.g. username), the same value is returned every
    time (deterministic).
    """
    if seed is None:
        seed = str(uuid.uuid4())
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return "android-" + h[:16]


def generate_jazoest(symbols: str) -> str:
    """
    Compute the jazoest that IG needs alongside phone_id at login
    = '2' + the sum of ord() of every character in symbols
    """
    amount = sum(ord(c) for c in symbols)
    return f"2{amount}"


def generate_signature_hmac(data: str, key: str) -> str:
    """HMAC-SHA256 (legacy) — newer IG no longer uses it, kept for old endpoints"""
    return hmac.new(
        key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# ---------------------------------------------------------------------------
# Signing the body of a POST request
# ---------------------------------------------------------------------------
def json_dumps(data: Any) -> str:
    """Dump JSON in compact form (no spaces), the same way IG's client does"""
    return json.dumps(data, separators=(",", ":"))


def generate_signed_body(
    data: Union[Dict[str, Any], str],
    *,
    signed: bool = False,
    key: str = "",
) -> Dict[str, str]:
    """
    Return a dict ready to send as the form-data of a POST:
        {'signed_body': 'SIGNATURE.<json>'}            (new default mode)
        {'signed_body': '<hmac>.<json>', 'ig_sig_key_version': '4'}  (legacy)

    Current IG accepts the fixed prefix 'SIGNATURE.' without verifying the HMAC.
    """
    if isinstance(data, dict):
        payload = json_dumps(data)
    else:
        payload = data

    if signed and key:
        sig = generate_signature_hmac(payload, key)
        return {
            "ig_sig_key_version": config.SIGNATURE_KEY_VERSION,
            "signed_body": f"{sig}.{payload}",
        }
    return {"signed_body": f"{config.UNSIGNED_PREFIX}.{payload}"}


# ---------------------------------------------------------------------------
# media id <-> shortcode (e.g. in the url instagram.com/p/<code>/)
# ---------------------------------------------------------------------------
_B64_ALPHABET = (
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


def media_pk_to_code(pk: Union[int, str]) -> str:
    """Convert a media pk (number) -> shortcode"""
    pk = int(pk)
    code = ""
    while pk > 0:
        pk, rem = divmod(pk, 64)
        code = _B64_ALPHABET[rem] + code
    return code or "A"


def media_code_to_pk(code: str) -> int:
    """Convert a shortcode -> media pk (number)"""
    pk = 0
    for char in code:
        pk = pk * 64 + _B64_ALPHABET.index(char)
    return pk


def media_id_to_pk(media_id: str) -> str:
    """'1234567890_9876543210' -> '1234567890' (strip the user id)"""
    return str(media_id).split("_")[0]


def pk_with_user_id(pk: Union[int, str], user_id: Union[int, str]) -> str:
    """Combine media pk + user id into a full media_id '<pk>_<user_id>'"""
    return f"{pk}_{user_id}"


# ---------------------------------------------------------------------------
# time / random
# ---------------------------------------------------------------------------
def now_ms() -> int:
    return int(time.time() * 1000)


def now_s() -> int:
    return int(time.time())


def random_delay(range_: tuple = config.REQUEST_DELAY_RANGE) -> float:
    """Random delay to mimic human behavior; returns the seconds delayed"""
    delay = random.uniform(*range_)
    time.sleep(delay)
    return delay


def random_string(length: int = 8, chars: str = string.ascii_lowercase) -> str:
    return "".join(random.choices(chars, k=length))


def generate_mutation_token() -> str:
    """client mutation token / offline_threading_id (18-19 digit number)"""
    return str(random.randint(10**18, 10**19 - 1))


# ---------------------------------------------------------------------------
# json helpers
# ---------------------------------------------------------------------------
def dict_to_url_encoded(data: Dict[str, Any]) -> str:
    """Convert a dict -> an encoded query string"""
    return "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in data.items())


def safe_get(data: dict, *keys, default=None):
    """Safely fetch a nested value from a dict: safe_get(d, 'a', 'b', 'c')"""
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur
