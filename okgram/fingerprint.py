"""
Live TLS / HTTP-2 fingerprint proof.

"Looks like a phone" is only a claim until you measure what actually leaves the
socket. This probes a JA3/JA4 echo service through the client's own transport and
reports the **real** TLS fingerprint (JA3/JA4), the **HTTP/2** Akamai fingerprint,
the negotiated protocol, and the User-Agent the server saw -- so you can confirm
the bytes on the wire are OkHttp/Chrome over h2, not Python/OpenSSL over h1.

`okgram fingerprint` prints this; `doctor --online` folds in a one-line check.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("okgram")

#: peet.ws echoes the TLS ClientHello (ja3/ja4), the HTTP/2 settings (akamai), the
#: negotiated protocol and the UA it received -- everything we need to verify.
PROBE_URL = "https://tls.peet.ws/api/all"


def probe(session: Any, *, user_agent: Optional[str] = None, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Hit the echo service through ``session``; return a parsed fingerprint dict (or None)."""
    headers = {"Accept": "application/json"}
    if user_agent:
        headers["User-Agent"] = user_agent
    try:
        resp = session.request("GET", PROBE_URL, headers=headers, timeout=timeout)
        if getattr(resp, "status_code", 0) >= 400:
            return None
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.debug("fingerprint probe failed: %s", exc)
        return None
    if not isinstance(data, dict):
        return None

    tls = data.get("tls") if isinstance(data.get("tls"), dict) else {}
    http2 = data.get("http2") if isinstance(data.get("http2"), dict) else {}
    akamai = (
        http2.get("akamai_fingerprint")
        or http2.get("akamai_fingerprint_hash")
        or data.get("akamai_fingerprint")
    )
    return {
        "ja3": tls.get("ja3"),
        "ja3_hash": tls.get("ja3_hash"),
        "ja4": tls.get("ja4"),
        "peetprint_hash": tls.get("peetprint_hash"),
        "tls_version": tls.get("tls_version_negotiated") or tls.get("tls_version_record"),
        "http_version": data.get("http_version"),
        "akamai": akamai,
        "user_agent": data.get("user_agent"),
        "ip": data.get("ip"),
    }


def _is_http2(http_version: Any) -> bool:
    return str(http_version or "").lower().replace("/", "").replace(".", "") in ("h2", "http20", "2")


def summary(client: Any, *, timeout: int = 10) -> Dict[str, Any]:
    """
    Probe through ``client`` and classify the result. Returns a dict with the raw
    fingerprint plus a ``verdict`` / ``grade`` you can show or assert on.
    """
    engine = getattr(getattr(client, "session", None), "engine", "?")
    try:
        ua = client.base_headers.get("User-Agent")
    except Exception:  # noqa: BLE001
        ua = None

    fp = probe(client.session, user_agent=ua, timeout=timeout)
    out: Dict[str, Any] = {"engine": engine, "intended_user_agent": ua, "fingerprint": fp}
    if fp is None:
        out["grade"] = "unknown"
        out["verdict"] = "could not reach the fingerprint service (offline?)"
        return out

    http2 = _is_http2(fp.get("http_version"))
    server_ua = fp.get("user_agent") or ""
    looks_python = "python" in server_ua.lower() or engine == "requests"

    if engine in ("?", None, ""):
        grade, verdict = "unknown", "engine is unknown -- cannot classify the fingerprint."
    elif looks_python:
        grade, verdict = "weak", (
            "WEAK -- Python/requests TLS over HTTP/1.1 is trivially flagged. "
            "Install tls-client (mobile) or curl_cffi (web)."
        )
    elif engine == "tls_client" and http2:
        grade, verdict = "phone", "PHONE-GRADE -- OkHttp/Android TLS over HTTP/2 (JA3/JA4 below)."
    elif engine == "curl_cffi" and http2:
        grade, verdict = "browser", "BROWSER-GRADE -- Chrome TLS over HTTP/2 (origin-consistent for web mode)."
    elif http2:
        grade, verdict = "ok", "OK -- HTTP/2 with a non-Python TLS stack."
    else:
        grade, verdict = "weak", "WEAK -- not negotiating HTTP/2; fingerprint is suspicious."

    out["http2"] = http2
    out["grade"] = grade
    out["verdict"] = verdict
    out["ua_match"] = bool(ua) and (server_ua == ua)
    return out


def render(s: Dict[str, Any]) -> str:
    """Render a summary() dict as a console block."""
    fp = s.get("fingerprint") or {}
    lines = [
        "okgram fingerprint -- what actually left the socket",
        "=" * 50,
        f"engine        : {s.get('engine')}",
        f"verdict       : {s.get('verdict')}",
        f"grade         : {s.get('grade')}",
        f"http version  : {fp.get('http_version')}",
        f"JA3 hash      : {fp.get('ja3_hash')}",
        f"JA4           : {fp.get('ja4')}",
        f"HTTP/2 akamai : {fp.get('akamai')}",
        f"TLS version   : {fp.get('tls_version')}",
        f"server saw UA : {fp.get('user_agent')}",
        f"UA matches    : {s.get('ua_match')}",
        f"egress IP     : {fp.get('ip')}",
        "=" * 50,
        f"JA3: {fp.get('ja3')}",
    ]
    return "\n".join(lines)
