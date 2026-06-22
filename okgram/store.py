"""
Multi-account session vault -- one device + one proxy + one identity per account,
managed together, optionally encrypted at rest.

Running several accounts safely means never letting their identities bleed into
each other: each account keeps its own stable device, its own egress (proxy), and
its own routing bundle, forever. :class:`SessionStore` keeps each account in its
own file under a directory, binds a proxy to it, and -- because that file holds a
live ``sessionid`` -- can encrypt it with AES-GCM derived from a passphrase.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from . import config

try:
    from Crypto.Cipher import AES
    from Crypto.Random import get_random_bytes
    _HAS_CRYPTO = True
except Exception:  # pragma: no cover
    _HAS_CRYPTO = False

_KDF_ITERS = 200_000
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def _default_dir() -> Path:
    return Path.home() / ".okgram" / "accounts"


class SessionStore:
    """A directory of account identity bundles (optionally encrypted)."""

    def __init__(self, directory: Union[str, Path, None] = None, *, password: Optional[str] = None):
        self.dir = Path(directory) if directory else _default_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.password = password
        if password and not _HAS_CRYPTO:
            raise RuntimeError("encryption requested but pycryptodome is not installed")

    # -- paths -----------------------------------------------------------
    @staticmethod
    def _safe(name: str) -> str:
        name = _SAFE_NAME.sub("_", str(name)).strip("_")
        return name or "account"

    def _path(self, name: str) -> Path:
        return self.dir / f"{self._safe(name)}.json"

    def list(self) -> List[str]:
        return sorted(p.stem for p in self.dir.glob("*.json"))

    def exists(self, name: str) -> bool:
        return self._path(name).exists()

    # -- encryption ------------------------------------------------------
    def _derive_key(self, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", self.password.encode("utf-8"), salt, _KDF_ITERS, 32)

    def _encrypt(self, bundle: dict) -> dict:
        salt = get_random_bytes(16)
        nonce = get_random_bytes(12)
        key = self._derive_key(salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        ct, tag = cipher.encrypt_and_digest(json.dumps(bundle).encode("utf-8"))
        b64 = lambda b: base64.b64encode(b).decode()
        return {
            "okgram_enc": 1, "kdf": "pbkdf2-sha256", "iter": _KDF_ITERS,
            "salt": b64(salt), "nonce": b64(nonce), "tag": b64(tag), "ct": b64(ct),
        }

    def _decrypt(self, obj: dict) -> dict:
        if not _HAS_CRYPTO:
            raise RuntimeError("pycryptodome is required to open this encrypted account")
        if not self.password:
            raise RuntimeError("this account is encrypted -- a password is required to open it")
        b = lambda s: base64.b64decode(s)
        key = self._derive_key(b(obj["salt"]))
        cipher = AES.new(key, AES.MODE_GCM, nonce=b(obj["nonce"]))
        try:
            data = cipher.decrypt_and_verify(b(obj["ct"]), b(obj["tag"]))
        except ValueError as exc:  # MAC check failed -> wrong password / tampered
            raise ValueError("could not decrypt account: wrong password or corrupted file") from exc
        return json.loads(data.decode("utf-8"))

    # -- raw bundle I/O --------------------------------------------------
    def save_bundle(self, name: str, bundle: dict, *, proxy: Optional[str] = None) -> Path:
        bundle = dict(bundle)
        if proxy is not None:
            bundle["proxy"] = proxy
        payload = self._encrypt(bundle) if self.password else bundle
        path = self._path(name)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def load_bundle(self, name: str) -> dict:
        raw = json.loads(self._path(name).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("okgram_enc"):
            return self._decrypt(raw)
        return raw

    def remove(self, name: str) -> bool:
        p = self._path(name)
        if p.exists():
            p.unlink()
            return True
        return False

    # -- high level ------------------------------------------------------
    def add(
        self,
        name: str,
        source: Any,
        *,
        proxy: Optional[str] = None,
        device_seed: Optional[str] = None,
        mode: str = config.MODE_MOBILE,
        bootstrap: bool = False,
        **client_kwargs: Any,
    ) -> dict:
        """
        Add/replace an account from: an :class:`InstagramAPI`, a settings dict, or a
        sessionid / cookie string (a client is built, optionally bootstrapped).
        Returns the saved bundle.
        """
        from .client import InstagramAPI

        if isinstance(source, InstagramAPI):
            bundle = source.get_settings()
            proxy = proxy or getattr(source, "proxy", None)
        elif isinstance(source, dict):
            # a raw bundle must look like get_settings() output, or open() will
            # KeyError later -- fail loudly here instead.
            if not (source.get("uuids") or {}).get("profile"):
                raise ValueError(
                    "dict source must be a full settings bundle "
                    "(use client.get_settings()); missing uuids.profile"
                )
            bundle = source
        else:  # sessionid / cookie string
            cl = InstagramAPI(device_seed=device_seed or self._safe(name), mode=mode,
                              proxy=proxy, **client_kwargs)
            if bootstrap:
                cl.bootstrap(str(source))
            else:
                cl.login_by_cookie(str(source), verify=False)
            bundle = cl.get_settings()
        self.save_bundle(name, bundle, proxy=proxy)
        return bundle

    def open(self, name: str, **client_kwargs: Any):
        """Build a ready InstagramAPI for ``name`` (restores device/routing/geo/proxy)."""
        from .client import InstagramAPI

        bundle = self.load_bundle(name)
        proxy = bundle.get("proxy")
        mode = bundle.get("mode", config.MODE_MOBILE)
        cl = InstagramAPI(mode=mode, proxy=proxy, **client_kwargs)
        cl.set_settings(bundle)
        return cl

    def info(self, name: str) -> dict:
        """Masked, non-secret summary of an account bundle."""
        try:
            b = self.load_bundle(name)
        except (RuntimeError, ValueError) as exc:
            return {"name": name, "encrypted": True, "error": str(exc)}
        auth = b.get("authorization_data", {})
        return {
            "name": name,
            "username": auth.get("username"),
            "user_id": auth.get("user_id"),
            "mode": b.get("mode"),
            "country": b.get("country"),
            "proxy": _mask_proxy(b.get("proxy")),
            "has_rur": bool(b.get("ig_u_rur")),
            "device": (b.get("device_settings") or {}).get("model"),
        }


def _mask_proxy(proxy: Optional[str]) -> Optional[str]:
    if not proxy:
        return None
    # hide credentials: scheme://user:pass@host -> scheme://***@host
    return re.sub(r"//[^@/]+@", "//***@", proxy)
