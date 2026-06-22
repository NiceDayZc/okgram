"""
AuthMixin — the entire login flow

Covers:
    - password encryption in the #PWD_INSTAGRAM:4 format (RSA + AES-GCM) like the real app
    - pre_login_flow (fetch public key, mid, csrftoken)
    - login(username, password)
    - two_factor_login(code)
    - challenge (request/submit verification code)
    - login_by_sessionid (reuse an existing sessionid)
    - save/load session (dump_settings / load_settings)
    - logout
"""
from __future__ import annotations

import base64
import json
import logging
import re
import struct
import time
from pathlib import Path
from typing import Dict, Optional, Union

from .. import config, utils
from ..exceptions import (
    BadPassword,
    ChallengeRequired,
    ClientError,
    LoginRequired,
    TwoFactorRequired,
)

logger = logging.getLogger("okgram")

# try to use pycryptodome for password encryption (strongly recommended)
try:
    from Crypto.Cipher import AES, PKCS1_v1_5
    from Crypto.PublicKey import RSA
    from Crypto.Random import get_random_bytes

    HAS_CRYPTO = True
except Exception:  # pragma: no cover
    HAS_CRYPTO = False


class AuthMixin:
    """Bundles methods related to authentication"""

    # attributes the main client has
    user_id: Optional[str]
    username: Optional[str]
    password: Optional[str]
    authorization: str
    last_json: Dict

    # keep the public key for password encryption
    password_encryption_pub_key: Optional[str] = None
    password_encryption_key_id: Optional[int] = None
    # keep the latest challenge / 2fa context
    last_login: Optional[dict] = None
    challenge_context: Optional[dict] = None
    two_factor_info: Optional[dict] = None

    # ------------------------------------------------------------------
    # password encryption
    # ------------------------------------------------------------------
    def encrypt_password(self, password: str) -> str:
        """
        Encrypt the password into the #PWD_INSTAGRAM:4:<ts>:<payload> format
        If pycryptodome or the public key is missing -> fall back to :0: (plaintext)
        """
        timestamp = str(int(time.time()))

        if not (HAS_CRYPTO and self.password_encryption_pub_key
                and self.password_encryption_key_id is not None):
            # fallback: IG still accepts version 0 (plaintext) in some cases
            logger.warning(
                "no public key/pycryptodome -> using plaintext password (:0:)"
            )
            return f"#PWD_INSTAGRAM:0:{timestamp}:{password}"

        pub_key_id = int(self.password_encryption_key_id)
        # public key is base64 of PEM/DER RSA
        decoded_pub_key = base64.b64decode(self.password_encryption_pub_key)

        # 1) random AES session key 32 bytes + IV 12 bytes
        session_key = get_random_bytes(32)
        iv = get_random_bytes(12)

        # 2) encrypt the session key with RSA (PKCS1 v1.5)
        recipient_key = RSA.import_key(decoded_pub_key)
        cipher_rsa = PKCS1_v1_5.new(recipient_key)
        rsa_encrypted = cipher_rsa.encrypt(session_key)

        # 3) encrypt the password with AES-GCM (auth data = timestamp)
        cipher_aes = AES.new(session_key, AES.MODE_GCM, nonce=iv)
        cipher_aes.update(timestamp.encode("utf-8"))
        aes_encrypted, tag = cipher_aes.encrypt_and_digest(
            password.encode("utf-8")
        )

        # 4) assemble payload: \x01 | keyid | iv | len(rsa) | rsa | tag | aes
        size_buffer = struct.pack("<H", len(rsa_encrypted))  # unsigned short per IG spec
        payload = base64.b64encode(
            b"\x01"
            + struct.pack("B", pub_key_id)
            + iv
            + size_buffer
            + rsa_encrypted
            + tag
            + aes_encrypted
        )
        return f"#PWD_INSTAGRAM:4:{timestamp}:{payload.decode('utf-8')}"

    def _capture_password_key(self) -> None:
        """Fetch the password-encryption public key from the latest response headers"""
        resp = getattr(self, "last_response", None)
        if resp is None:
            return
        h = resp.headers
        key_id = h.get("ig-set-password-encryption-key-id")
        pub_key = h.get("ig-set-password-encryption-pub-key")
        if key_id is not None:
            self.password_encryption_key_id = int(key_id)
        if pub_key:
            self.password_encryption_pub_key = pub_key

    # ------------------------------------------------------------------
    # pre-login flow
    # ------------------------------------------------------------------
    def pre_login_flow(self) -> None:
        """
        Pre-login step: fetch mid, csrftoken, public key, sync feature flags
        (makes login look like the real app and obtains the public key for encryption)
        """
        # 1) sync launcher (no auth needed) -> obtains public key + mid
        try:
            self.private_request(
                "si/fetch_headers/",
                params={
                    "challenge_type": "signup",
                    "guid": self.device.uuid.replace("-", ""),
                },
                login=True,
            )
        except ClientError:
            pass
        self._capture_password_key()

        # 2) launcher/sync (configs)
        data = {
            "id": self.device.uuid,
            "server_config_retrieval": "1",
        }
        try:
            self.private_request("launcher/sync/", data, login=True)
        except ClientError:
            pass
        self._capture_password_key()

        # 3) qe/sync (experiments)
        try:
            self.private_request(
                "qe/sync/",
                {
                    "id": self.device.uuid,
                    "server_config_retrieval": "1",
                    "experiments": "",
                },
                login=True,
                headers={"X-DEVICE-ID": self.device.uuid},
            )
        except ClientError:
            pass
        self._capture_password_key()

    # ------------------------------------------------------------------
    # login
    # ------------------------------------------------------------------
    def login(
        self,
        username: str,
        password: str,
        *,
        relogin: bool = False,
        verification_code: str = "",
    ) -> bool:
        """
        login with username/password

        Returns
        -------
        bool : True on success

        Raises
        ------
        TwoFactorRequired   : 2FA is required -> call two_factor_login()
        ChallengeRequired   : a challenge is required -> call challenge_resolve()
        BadPassword         : wrong password
        """
        self.username = username
        self.password = password

        if self.authorization and not relogin:
            # a token already exists, try using it directly
            try:
                self.get_timeline_feed() if hasattr(self, "get_timeline_feed") else None
                return True
            except LoginRequired:
                pass

        # fetch the public key if not yet available
        if not self.password_encryption_pub_key:
            self.pre_login_flow()

        enc_password = self.encrypt_password(password)
        jazoest = utils.generate_jazoest(self.device.phone_id)

        data = {
            "jazoest": jazoest,
            "country_codes": json.dumps(
                [{"country_code": str(self.country_code), "source": ["default"]}]
            ),
            "phone_id": self.device.phone_id,
            "enc_password": enc_password,
            "username": username,
            "adid": self.device.advertising_id,
            "guid": self.device.uuid,
            "device_id": self.device.device_id,
            "google_tokens": "[]",
            "login_attempt_count": "0",
        }
        if verification_code:
            data["verification_code"] = verification_code

        try:
            result = self.private_request("accounts/login/", data, login=True)
        except TwoFactorRequired as exc:
            self.two_factor_info = exc.extra.get("two_factor_info")
            self.last_login = exc.extra
            raise
        except ChallengeRequired as exc:
            self.challenge_context = exc.extra.get("challenge") or exc.extra
            self.last_login = exc.extra
            raise

        return self._after_login(result)

    def _after_login(self, result: dict) -> bool:
        """Read a successful login result -> set user_id, username"""
        self.last_login = result
        if result.get("logged_in_user"):
            user = result["logged_in_user"]
            self.user_id = str(user.get("pk") or user.get("pk_id"))
            self.username = user.get("username", self.username)
            logger.info("login succeeded as %s (id=%s)", self.username, self.user_id)
            try:
                self.login_flow()
            except Exception:  # noqa
                pass
            return True
        if result.get("two_factor_required"):
            self.two_factor_info = result.get("two_factor_info")
            raise TwoFactorRequired(
                "2FA verification required", **result
            )
        raise BadPassword(result.get("message") or "login failed", **result)

    def two_factor_login(
        self, verification_code: str, *, two_factor_identifier: str = ""
    ) -> bool:
        """Verify 2FA with a 6-digit code (must be called after login() raises TwoFactorRequired)"""
        info = self.two_factor_info or {}
        identifier = two_factor_identifier or info.get("two_factor_identifier")
        if not identifier:
            raise ClientError("no two_factor_identifier — call login() first")

        data = {
            "verification_code": verification_code.replace(" ", ""),
            "phone_id": self.device.phone_id,
            "two_factor_identifier": identifier,
            "username": self.username,
            "trust_this_device": "1",
            "guid": self.device.uuid,
            "device_id": self.device.device_id,
            "verification_method": str(info.get("verification_method", "1")),
        }
        result = self.private_request(
            "accounts/two_factor_login/", data, login=True
        )
        return self._after_login(result)

    # ------------------------------------------------------------------
    # challenge
    # ------------------------------------------------------------------
    def challenge_resolve(self, choice: int = 1) -> bool:
        """
        Start the challenge: choose the code delivery method (typically 0=SMS, 1=Email)
        then call challenge_send_code() followed by challenge_submit_code()
        """
        ctx = self.challenge_context or {}
        api_path = ctx.get("api_path") or ctx.get("challenge", {}).get("api_path")
        if not api_path:
            raise ChallengeRequired("no challenge context — call login() first")
        # GET challenge
        endpoint = api_path.lstrip("/")
        if endpoint.startswith("api/v1/"):
            endpoint = endpoint[len("api/v1/"):]
        self.private_request(endpoint, login=True)
        # choose the delivery method
        return self.challenge_send_code(choice, endpoint)

    def challenge_send_code(self, choice: int, endpoint: str) -> bool:
        data = {
            "choice": str(choice),
            "_uuid": self.device.uuid,
            "guid": self.device.uuid,
            "device_id": self.device.device_id,
        }
        self.private_request(endpoint, data, login=True)
        self._pending_challenge_endpoint = endpoint
        return True

    def challenge_submit_code(self, code: str, endpoint: str = "") -> bool:
        """Submit the challenge verification code received via SMS/Email"""
        endpoint = endpoint or getattr(self, "_pending_challenge_endpoint", "")
        if not endpoint:
            raise ChallengeRequired("unknown challenge endpoint")
        data = {
            "security_code": code.replace(" ", ""),
            "_uuid": self.device.uuid,
            "guid": self.device.uuid,
            "device_id": self.device.device_id,
        }
        result = self.private_request(endpoint, data, login=True)
        if result.get("logged_in_user"):
            return self._after_login(result)
        if result.get("action") == "close" or result.get("status") == "ok":
            return True
        return False

    # ------------------------------------------------------------------
    # login with existing cookies (string / JSON / netscape / dict)
    # ------------------------------------------------------------------
    @staticmethod
    def parse_cookies(raw: Union[str, dict]) -> Dict[str, str]:
        """
        Parse cookies from many formats into a {name: value} dict:

          - header string  : "sessionid=...; ds_user_id=...; csrftoken=..."
                             (also accepts a leading "Cookie:")
          - JSON           : '[{"name":"sessionid","value":"..."}, ...]'  or
                             '{"sessionid":"...", "ds_user_id":"..."}'
                             (e.g. exported by the EditThisCookie / Cookie-Editor
                             browser extensions)
          - Netscape       : a cookies.txt dump (tab-separated)
          - dict           : {"sessionid": "...", ...}
          - bare sessionid : "1234%3Aabcd%3A10"

        Only the cookie name/value pairs are returned; domain/path/flags are ignored.
        """
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items() if v is not None}

        text = str(raw).strip()
        if not text:
            return {}

        # --- JSON (list of {name,value} objects, or a flat dict) ---
        if text[0] in "[{":
            try:
                data = json.loads(text)
            except Exception:
                data = None
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v is not None}
            if isinstance(data, list):
                out: Dict[str, str] = {}
                for c in data:
                    if isinstance(c, dict) and c.get("name"):
                        out[str(c["name"])] = str(c.get("value", ""))
                if out:
                    return out

        # --- Netscape cookies.txt (tab-separated: domain flag path secure exp name value) ---
        if "\t" in text:
            out = {}
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    out[parts[5]] = parts[6]
            if out:
                return out

        # --- header string: "Cookie: a=b; c=d"  or  "a=b; c=d" ---
        if text.lower().startswith("cookie:"):
            text = text.split(":", 1)[1].strip()
        out = {}
        for pair in re.split(r"[;\n]+", text):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, value = pair.split("=", 1)
            out[name.strip()] = value.strip()

        # --- bare sessionid fallback ---
        if not out and "=" not in text:
            out = {"sessionid": text}
        return out

    def login_by_cookie(
        self,
        cookies: Union[str, dict],
        *,
        verify: bool = True,
        warmup: bool = False,
        domain: str = ".instagram.com",
    ) -> bool:
        """
        Log in using existing cookies (any format accepted by :meth:`parse_cookies`).

        Requires at least ``sessionid``. It also reads ``ds_user_id`` / ``csrftoken``
        / ``mid`` when present, loads every cookie into the session jar, and
        reconstructs the mobile ``Authorization: Bearer IGT:2:...`` header from the
        sessionid (the private API authenticates by that header, not just the cookie).

        Parameters
        ----------
        cookies : str | dict
            cookie string / JSON / netscape text / dict / bare sessionid
        verify : bool
            if True, confirm by calling get_current_user() and fill username/user_id

        Returns
        -------
        bool : True on success

        Raises
        ------
        ClientError : if the input cannot be parsed or has no sessionid
        """
        jar = self.parse_cookies(cookies)
        if not jar:
            raise ClientError("could not parse any cookies from the input")
        sessionid = (jar.get("sessionid") or "").strip()
        if not sessionid:
            raise ClientError("the cookies contain no 'sessionid'")

        # load every cookie into the session jar
        for name, value in jar.items():
            try:
                self.session.cookies.set(name, value, domain=domain)
            except TypeError:
                self.session.cookies.set(name, value)

        # user id: prefer ds_user_id, else the prefix of the sessionid
        uid = jar.get("ds_user_id")
        if not uid:
            try:
                uid = sessionid.split("%3A")[0].split(":")[0]
            except Exception:
                uid = None
        if uid:
            self.user_id = str(uid)

        # carry over csrftoken / mid / rur so headers and cookies agree
        if jar.get("csrftoken"):
            self.csrftoken = jar["csrftoken"]
        if jar.get("mid"):
            self.mid = jar["mid"]
        # IG-U-RUR ships either as a cookie ('rur') or as an explicit key.
        rur = jar.get("rur") or jar.get("ig-u-rur") or jar.get("IG-U-RUR")
        if rur:
            self.ig_u_rur = rur
        if jar.get("shbid"):
            self.ig_u_shbid = jar["shbid"]
        if jar.get("shbts"):
            self.ig_u_shbts = jar["shbts"]

        # Reconstruct the mobile Bearer token ONLY in mobile mode -- in web mode the
        # browser session authenticates by the sessionid cookie + csrftoken, and a
        # Bearer header would contradict the web-app origin the session came from.
        if self.user_id and getattr(self, "mode", config.MODE_MOBILE) == config.MODE_MOBILE:
            blob = base64.b64encode(
                json.dumps(
                    {"ds_user_id": self.user_id, "sessionid": sessionid},
                    separators=(",", ":"),
                ).encode()
            ).decode()
            self.authorization = f"Bearer IGT:2:{blob}"

        ok = bool(self.user_id)
        if verify:
            user = self.get_current_user() if hasattr(self, "get_current_user") else None
            if user:
                self.user_id = str(user.get("pk", self.user_id))
                self.username = user.get("username", self.username)
                ok = True
            else:
                ok = False
        if ok and warmup:
            try:
                from .. import behaviors
                behaviors.cold_start(self)
            except Exception:  # noqa: BLE001 -- warmup must never fail the login
                pass
        return ok

    def login_by_cookie_file(self, path: Union[str, Path], *, verify: bool = True) -> bool:
        """Read cookies from a file (any supported format) and call login_by_cookie."""
        raw = Path(path).read_text(encoding="utf-8", errors="ignore")
        return self.login_by_cookie(raw, verify=verify)

    def login_by_sessionid(self, sessionid: str) -> bool:
        """login using an existing sessionid cookie (delegates to login_by_cookie)"""
        return self.login_by_cookie({"sessionid": str(sessionid).strip()})

    def logout(self) -> bool:
        """Log out"""
        try:
            self.private_request(
                "accounts/logout/",
                {"one_tap_app_login": "0", "guid": self.device.uuid},
            )
        except ClientError:
            pass
        self.authorization = ""
        self.user_id = None
        self.session.cookies.clear()
        return True

    def login_flow(self) -> None:
        """Post-login cold-start (timeline -> stories -> inbox -> current user),
        with a believable nav chain. Mirrors what the app does on first open."""
        try:
            from .. import behaviors
            behaviors.cold_start(self)
        except Exception:  # noqa
            pass

    # ------------------------------------------------------------------
    # session: save / load
    # ------------------------------------------------------------------
    def get_settings(self) -> dict:
        """
        Collect ALL state into one immutable identity bundle (saved for next time).

        The bundle travels together: device + uuids + the session-routing headers
        (mid / www-claim / IG-U-RUR / SHBID / SHBTS / region-hint) + the region
        (country / tz / eu-dc) + the live-synced bloks version. Reloading it
        reproduces the exact same identity the server last saw -- the single most
        important thing for not getting bounced.
        """
        geo = getattr(self, "geo", None)
        return {
            "uuids": self.device.to_dict(),
            "device_settings": self.device.profile,
            "user_agent": self.device.user_agent(
                self.app_version, self.version_code, self.locale
            ),
            "mode": getattr(self, "mode", config.MODE_MOBILE),
            "authorization_data": {
                "authorization": self.authorization,
                "user_id": self.user_id,
                "username": self.username,
            },
            "cookies": self.session.cookies.get_dict(),
            "mid": self.mid,
            "ig_www_claim": self.ig_www_claim,
            "csrftoken": self.csrftoken,
            # IG-U-* session-routing headers -- losing these on reload = bounce
            "ig_u_rur": getattr(self, "ig_u_rur", ""),
            "ig_u_shbid": getattr(self, "ig_u_shbid", ""),
            "ig_u_shbts": getattr(self, "ig_u_shbts", ""),
            "ig_direct_region_hint": getattr(self, "ig_direct_region_hint", ""),
            "country": self.country,
            "country_code": self.country_code,
            "locale": self.locale,
            "timezone_offset": self.timezone_offset,
            "eu_dc_enabled": getattr(self, "eu_dc_enabled", config.EU_DC_ENABLED),
            "geo": geo.to_dict() if geo is not None else None,
            "app_version": self.app_version,
            "version_code": self.version_code,
            "bloks_version_id": getattr(self, "bloks_version_id", config.BLOKS_VERSION_ID),
            "nav_chain": getattr(self, "nav_chain", ""),
            "proxy": getattr(self, "proxy", None),
            "governor": (
                self.governor.to_dict()
                if getattr(self, "governor", None) is not None else None
            ),
            "password_encryption_pub_key": self.password_encryption_pub_key,
            "password_encryption_key_id": self.password_encryption_key_id,
        }

    def set_settings(self, settings: dict) -> bool:
        """Load the identity bundle back into the client (exact inverse of get_settings)."""
        from ..device import Device

        if settings.get("uuids"):
            self.device = Device.from_dict(settings["uuids"])
        self.mode = settings.get("mode", getattr(self, "mode", config.MODE_MOBILE))
        # if the saved mode differs from how the transport was built, rebuild it so
        # the TLS fingerprint matches the mode (done BEFORE cookies are loaded so
        # they land in the new session's jar).
        if hasattr(self, "_sync_transport_to_mode"):
            self._sync_transport_to_mode()
        auth = settings.get("authorization_data", {})
        self.authorization = auth.get("authorization", "")
        self.user_id = auth.get("user_id")
        self.username = auth.get("username")
        for cookie_name, cookie_value in (settings.get("cookies") or {}).items():
            self.session.cookies.set(
                cookie_name, cookie_value, domain=".instagram.com"
            )
        self.mid = settings.get("mid", self.mid)
        self.ig_www_claim = settings.get("ig_www_claim", "0")
        self.csrftoken = settings.get("csrftoken", "")
        # restore the session-routing headers
        self.ig_u_rur = settings.get("ig_u_rur", getattr(self, "ig_u_rur", ""))
        self.ig_u_shbid = settings.get("ig_u_shbid", getattr(self, "ig_u_shbid", ""))
        self.ig_u_shbts = settings.get("ig_u_shbts", getattr(self, "ig_u_shbts", ""))
        self.ig_direct_region_hint = settings.get(
            "ig_direct_region_hint", getattr(self, "ig_direct_region_hint", "")
        )
        self.country = settings.get("country", self.country)
        self.country_code = settings.get("country_code", self.country_code)
        self.locale = settings.get("locale", self.locale)
        self.timezone_offset = settings.get("timezone_offset", self.timezone_offset)
        self.eu_dc_enabled = settings.get(
            "eu_dc_enabled", getattr(self, "eu_dc_enabled", config.EU_DC_ENABLED)
        )
        if settings.get("geo"):
            try:
                from ..geo import GeoProfile
                self.geo = GeoProfile.from_dict(settings["geo"])
            except Exception:  # noqa: BLE001
                pass
        self.app_version = settings.get("app_version", self.app_version)
        self.version_code = settings.get("version_code", self.version_code)
        self.bloks_version_id = settings.get(
            "bloks_version_id", getattr(self, "bloks_version_id", config.BLOKS_VERSION_ID)
        )
        self.nav_chain = settings.get("nav_chain", getattr(self, "nav_chain", ""))
        if settings.get("proxy") and hasattr(self, "set_proxy"):
            self.set_proxy(settings["proxy"])
        if settings.get("governor"):
            # round-trip the governor even into a client that wasn't started with
            # govern=True -- otherwise saved rate counts / cooldown silently vanish.
            if getattr(self, "governor", None) is None and hasattr(self, "enable_governor"):
                self.enable_governor()
            if getattr(self, "governor", None) is not None:
                self.governor.load_dict(settings["governor"])
        self.password_encryption_pub_key = settings.get(
            "password_encryption_pub_key"
        )
        self.password_encryption_key_id = settings.get(
            "password_encryption_key_id"
        )
        return True

    def dump_settings(self, path: Union[str, Path]) -> bool:
        """Save settings to a JSON file"""
        Path(path).write_text(
            json.dumps(self.get_settings(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    def load_settings(self, path: Union[str, Path]) -> dict:
        """Load settings from a JSON file"""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.set_settings(data)
        return data

    def relogin(self) -> bool:
        """Re-login using the existing username/password (keeps the same device)"""
        if not (self.username and self.password):
            raise ClientError("no username/password to relogin")
        return self.login(self.username, self.password, relogin=True)
