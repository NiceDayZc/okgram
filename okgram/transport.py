"""
Pluggable HTTP transport — make traffic look like the real Instagram Android app.

Plain ``requests`` is trivially detectable by anti-bot systems: it uses Python's
OpenSSL (a distinctive JA3/JA4 TLS fingerprint that no phone produces) and speaks
HTTP/1.1, while the Instagram app speaks HTTP/2 over an OkHttp/BoringSSL stack.

This module abstracts the HTTP layer behind a small ``Session``/``Response`` pair
and picks the most app-like engine available:

    1. tls_client  -> impersonates OkHttp on Android (okhttp4_android_*), HTTP/2,
                      real OkHttp JA3/JA4. **Best match for the Instagram Android UA.**
    2. curl_cffi   -> curl-impersonate (browser TLS + HTTP/2). Real, non-Python TLS.
    3. requests    -> last-resort fallback (always importable, weakest fingerprint).

The wrapper keeps a ``requests``-compatible surface (``session.request/get/post``,
``session.cookies`` as a cookie jar, ``session.proxies``; ``response.status_code/
headers/json()/text/cookies``) so the rest of the package does not care which
engine is underneath. Network/timeout failures are normalised to this package's
own exceptions (:class:`ClientRequestTimeout` / :class:`ClientConnectionError`).
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any, Dict, Optional, Union

from requests.structures import CaseInsensitiveDict
from requests.cookies import RequestsCookieJar

from . import config
from .exceptions import ClientConnectionError, ClientRequestTimeout

logger = logging.getLogger("okgram")

# ---------------------------------------------------------------------------
# Engine detection
# ---------------------------------------------------------------------------
try:
    import tls_client  # type: ignore
    HAS_TLS_CLIENT = True
except Exception:  # pragma: no cover
    HAS_TLS_CLIENT = False

try:
    from curl_cffi import requests as _curl  # type: ignore
    HAS_CURL_CFFI = True
except Exception:  # pragma: no cover
    HAS_CURL_CFFI = False

import requests as _requests  # always available (fallback + cookie jar/types)

#: Engine priority when ``engine="auto"``. tls_client first = closest to the
#: Instagram Android (OkHttp) client.
ENGINE_PRIORITY = ("tls_client", "curl_cffi", "requests")

#: Default browser profile for curl_cffi (no Android-app profile exists there).
CURL_IMPERSONATE_DEFAULT = "chrome"

#: Header order that the Instagram Android app roughly emits on the wire.
#: tls_client sends headers in this order (a real client never alphabetises them
#: the way requests does).
HEADER_ORDER = [
    "X-IG-App-Locale", "X-IG-Device-Locale", "X-IG-Mapped-Locale",
    "X-Pigeon-Session-Id", "X-Pigeon-Rawclienttime",
    "X-IG-Bandwidth-Speed-KBPS", "X-IG-Bandwidth-TotalBytes-B",
    "X-IG-Bandwidth-TotalTime-MS", "X-IG-App-Startup-Country",
    "X-Bloks-Version-Id", "X-IG-WWW-Claim", "X-Bloks-Is-Layout-RTL",
    "X-Bloks-Is-Panorama-Enabled", "X-IG-Device-ID", "X-IG-Family-Device-ID",
    "X-IG-Android-ID", "X-IG-Timezone-Offset", "X-IG-Connection-Type",
    "X-IG-Capabilities", "X-IG-App-ID", "Priority", "User-Agent",
    "Accept-Language", "Accept-Encoding", "Host", "X-MID", "X-CSRFToken",
    "Authorization", "IG-U-DS-USER-ID", "IG-INTENDED-USER-ID",
    "X-FB-HTTP-Engine", "X-FB-Client-IP", "X-FB-Server-Cluster", "Connection",
]


def okhttp_profile_for(android_release: Union[str, int, None]) -> str:
    """Map an Android release (e.g. '13') to the closest tls_client OkHttp profile."""
    try:
        major = int(str(android_release).split(".")[0])
    except (TypeError, ValueError):
        major = 13
    major = max(7, min(13, major))  # available: okhttp4_android_7 .. _13
    return f"okhttp4_android_{major}"


# ---------------------------------------------------------------------------
# Response wrapper (uniform surface over every engine)
# ---------------------------------------------------------------------------
class Response:
    """requests-like response over any engine (case-insensitive headers)."""

    __slots__ = ("status_code", "headers", "cookies", "text", "url", "_content", "_native")

    def __init__(self, native: Any):
        self._native = native
        self.status_code = int(getattr(native, "status_code", 0))
        try:
            self.headers = CaseInsensitiveDict(dict(native.headers))
        except Exception:
            self.headers = CaseInsensitiveDict()
        self.cookies = getattr(native, "cookies", {}) or {}
        try:
            self.text = native.text
        except Exception:
            self.text = ""
        self.url = str(getattr(native, "url", "") or "")
        self._content: Optional[bytes] = None

    @property
    def content(self) -> bytes:
        if self._content is None:
            raw = getattr(self._native, "content", None)
            if isinstance(raw, (bytes, bytearray)):
                self._content = bytes(raw)
            else:
                self._content = (self.text or "").encode("utf-8", "ignore")
        return self._content

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        return _json.loads(self.text)

    def __repr__(self) -> str:
        return f"<Response [{self.status_code}] {self.url}>"


# ---------------------------------------------------------------------------
# Session wrapper
# ---------------------------------------------------------------------------
class _CurlCookieJar:
    """Minimal RequestsCookieJar-compatible facade over curl_cffi's Cookies."""

    def __init__(self, sess: Any):
        self._s = sess

    def get(self, name: str, default: Any = None) -> Any:
        try:
            return self._s.cookies.get(name) or default
        except Exception:
            return default

    def set(self, name: str, value: str, domain: Optional[str] = None, **_kw: Any) -> None:
        try:
            self._s.cookies.set(name, value, domain=domain or "", path="/")
        except TypeError:
            self._s.cookies.set(name, value)
        except Exception:
            pass

    def get_dict(self, *_a: Any, **_kw: Any) -> Dict[str, str]:
        try:
            return {k: v for k, v in self._s.cookies.items()}
        except Exception:
            try:
                return dict(self._s.cookies)
            except Exception:
                return {}

    def clear(self, *_a: Any, **_kw: Any) -> None:
        try:
            self._s.cookies.clear()
        except Exception:
            pass


class Session:
    """
    Uniform HTTP session over tls_client / curl_cffi / requests.

    ``.request()`` is the single chokepoint; ``.get()``/``.post()`` route through
    it (so a test that patches ``.request`` intercepts everything). Cookies live
    in ``.cookies`` (a cookie jar), proxies in ``.proxies``.
    """

    def __init__(self, engine: str, impersonate: Optional[str] = None):
        self.engine = engine
        self.impersonate = impersonate
        self.headers: Dict[str, str] = {}
        self._proxies: Optional[Dict[str, str]] = None
        self._build_engine()

    # -- engine construction -------------------------------------------------
    def _build_engine(self) -> None:
        if self.engine == "tls_client":
            self._sess = tls_client.Session(
                client_identifier=self.impersonate or "okhttp4_android_13",
                random_tls_extension_order=True,
                header_order=HEADER_ORDER,
            )
            self.cookies = self._sess.cookies  # already a RequestsCookieJar
        elif self.engine == "curl_cffi":
            self._sess = _curl.Session(impersonate=self.impersonate or CURL_IMPERSONATE_DEFAULT)
            self.cookies = _CurlCookieJar(self._sess)
        elif self.engine == "requests":
            self._sess = _requests.Session()
            self.cookies = self._sess.cookies
        else:  # pragma: no cover
            raise ValueError(f"unknown transport engine: {self.engine}")

    # -- proxies -------------------------------------------------------------
    @property
    def proxies(self) -> Optional[Dict[str, str]]:
        return self._proxies

    @proxies.setter
    def proxies(self, value: Union[str, Dict[str, str], None]) -> None:
        if isinstance(value, str):
            value = {"http": value, "https": value} if value else None
        self._proxies = value
        proxy_str = (value or {}).get("https") or (value or {}).get("http") if value else None
        try:
            if self.engine == "tls_client":
                self._sess.proxies = proxy_str or ""
            else:
                self._sess.proxies = value or {}
        except Exception:
            pass

    # -- request -------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Any = None,
        headers: Optional[Dict[str, str]] = None,
        files: Any = None,
        timeout: Optional[float] = None,
        cookies: Any = None,
        **_kw: Any,
    ) -> Response:
        merged = dict(self.headers)
        if headers:
            merged.update(headers)
        timeout = timeout or config.REQUEST_TIMEOUT
        try:
            if self.engine == "tls_client":
                native = self._sess.execute_request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    data=data,
                    headers=merged or None,
                    cookies=cookies,
                    timeout_seconds=int(timeout),
                )
            elif self.engine == "curl_cffi":
                native = self._sess.request(
                    method.upper(), url,
                    params=params, data=data, headers=merged or None,
                    cookies=cookies, timeout=timeout,
                    impersonate=self.impersonate or CURL_IMPERSONATE_DEFAULT,
                )
            else:  # requests
                native = self._sess.request(
                    method.upper(), url,
                    params=params, data=data, headers=merged or None,
                    files=files, cookies=cookies, timeout=timeout,
                    proxies=self._proxies,
                )
        except Exception as exc:  # normalise network/timeout/TLS errors
            if "timeout" in type(exc).__name__.lower() or "timeout" in str(exc).lower():
                raise ClientRequestTimeout(str(exc)) from exc
            raise ClientConnectionError(f"{type(exc).__name__}: {exc}") from exc

        return Response(native)

    def get(self, url: str, **kw: Any) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw: Any) -> Response:
        return self.request("POST", url, **kw)

    def __repr__(self) -> str:
        return f"<transport.Session engine={self.engine} impersonate={self.impersonate}>"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def resolve_engine(engine: str = "auto") -> str:
    """Resolve 'auto' to the best available engine; validate an explicit choice."""
    available = {
        "tls_client": HAS_TLS_CLIENT,
        "curl_cffi": HAS_CURL_CFFI,
        "requests": True,
    }
    if engine == "auto":
        for name in ENGINE_PRIORITY:
            if available.get(name):
                return name
        return "requests"
    if engine not in available:
        raise ValueError(f"unknown engine '{engine}' (choose from {list(available)} or 'auto')")
    if not available[engine]:
        raise ImportError(
            f"engine '{engine}' is not installed. "
            f"pip install {'tls-client' if engine == 'tls_client' else engine}"
        )
    return engine


def build_session(
    *,
    engine: str = "auto",
    impersonate: Optional[str] = None,
    android_release: Union[str, int, None] = None,
    proxy: Union[str, Dict[str, str], None] = None,
) -> Session:
    """
    Build a transport session.

    engine          : 'auto' | 'tls_client' | 'curl_cffi' | 'requests'
    impersonate     : profile override (e.g. 'okhttp4_android_12', 'chrome'); if
                      None, tls_client is auto-mapped from ``android_release``.
    android_release : the device's Android version, used to pick the OkHttp profile.
    proxy           : 'http://user:pass@host:port' / 'socks5://...' or a dict.
    """
    resolved = resolve_engine(engine)
    if impersonate is None and resolved == "tls_client":
        impersonate = okhttp_profile_for(android_release)
    elif impersonate is None and resolved == "curl_cffi":
        impersonate = CURL_IMPERSONATE_DEFAULT
    sess = Session(resolved, impersonate=impersonate)
    if proxy:
        sess.proxies = proxy
    logger.debug("transport engine=%s impersonate=%s", resolved, sess.impersonate)
    return sess
