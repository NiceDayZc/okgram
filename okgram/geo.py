"""
Geo auto-sync -- align the client's reported region to the real egress IP.

The single biggest non-IP cause of "login_required"/challenge bounces is a region
fingerprint that contradicts the source IP: e.g. the client claims ``country=US``
and an ``America/*`` timezone while the traffic exits a Thai residential IP.

This module detects the country / calling-code / timezone of the **actual egress
IP** (querying through the client's own transport, so any proxy is honoured) and
returns a *self-consistent* :class:`GeoProfile`. It works for every country: the
provider supplies the precise values, and :mod:`okgram.config` tables fill any gap.

Everything here is best-effort and offline-safe -- if no provider answers, the
caller keeps its configured/default region and nothing raises.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from . import config

logger = logging.getLogger("okgram")


class GeoProfile:
    """A self-consistent region profile derived from the egress IP."""

    __slots__ = (
        "country", "country_code", "timezone_offset", "locale", "language",
        "eu_dc", "ip", "source", "detected_at",
    )

    def __init__(
        self,
        *,
        country: str,
        country_code: int,
        timezone_offset: int,
        locale: Optional[str] = None,
        language: Optional[str] = None,
        eu_dc: Optional[str] = None,
        ip: str = "",
        source: str = "",
        detected_at: Optional[float] = None,
    ):
        self.country = (country or config.DEFAULT_COUNTRY).upper()
        self.country_code = int(country_code or config.DEFAULT_COUNTRY_CODE)
        self.timezone_offset = int(timezone_offset)
        self.locale = locale
        self.language = language
        self.eu_dc = eu_dc if eu_dc is not None else (
            "true" if self.country in config.EU_DC_COUNTRIES else "false"
        )
        self.ip = ip
        self.source = source
        self.detected_at = detected_at if detected_at is not None else time.time()

    # -- (de)serialisation for the settings bundle --------------------------
    def to_dict(self) -> dict:
        return {
            "country": self.country,
            "country_code": self.country_code,
            "timezone_offset": self.timezone_offset,
            "locale": self.locale,
            "language": self.language,
            "eu_dc": self.eu_dc,
            "ip": self.ip,
            "source": self.source,
            "detected_at": self.detected_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GeoProfile":
        return cls(
            country=data.get("country", config.DEFAULT_COUNTRY),
            country_code=data.get("country_code", config.DEFAULT_COUNTRY_CODE),
            timezone_offset=data.get("timezone_offset", config.TIMEZONE_OFFSET),
            locale=data.get("locale"),
            language=data.get("language"),
            eu_dc=data.get("eu_dc"),
            ip=data.get("ip", ""),
            source=data.get("source", ""),
            detected_at=data.get("detected_at"),
        )

    def is_fresh(self, ttl: int = config.GEO_CACHE_TTL) -> bool:
        return (time.time() - self.detected_at) < ttl

    def __repr__(self) -> str:
        return (
            f"<GeoProfile {self.country} +cc{self.country_code} "
            f"tz{self.timezone_offset:+d} ip={self.ip or '?'} via {self.source}>"
        )


# ---------------------------------------------------------------------------
# offset parsing helpers
# ---------------------------------------------------------------------------
def _parse_offset(value: Any) -> Optional[int]:
    """
    Parse a tz offset into seconds. Accepts integer seconds (``25200``/``-18000``)
    or the ``+HHMM`` / ``+HH:MM`` clock forms (``"+0700"``, ``"+07:00"``).

    The clock forms are detected FIRST -- otherwise ``int("+0900")`` would wrongly
    yield ``900`` (Python accepts a leading sign), corrupting every string offset.
    A bare ``"7200"`` is disambiguated as seconds because ``72`` is not a valid hour.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None

    # Clock form requires an EXPLICIT marker -- a sign ('+0700'/'-0500') or a colon
    # ('+07:00'/'07:00'). A bare integer string ('25200', '7200') is always seconds.
    # Requiring the marker removes the '0530' = 5h30m vs 530s ambiguity entirely
    # (every real provider sends the marker), and we validate hours<=14, mins<=59.
    has_sign = text[0] in "+-"
    has_colon = ":" in text
    if has_sign or has_colon:
        body = (text[1:] if has_sign else text).replace(":", "")
        if body.isdigit() and 2 <= len(body) <= 4:
            hours = int(body[:2])
            minutes = int(body[2:4]) if len(body) >= 4 else 0
            if hours <= 14 and minutes <= 59:
                sign = -1 if text[0] == "-" else 1
                return sign * (hours * 3600 + minutes * 60)
        return None  # malformed clock value -> let the caller fall back

    try:
        return int(text)
    except ValueError:
        return None


def _calling_code(raw: Any, country: str) -> int:
    """Normalise a provider calling code ('+66' / '66') or fall back to the table."""
    if raw is not None:
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                pass
    return config.COUNTRY_CALLING_CODES.get(
        (country or "").upper(), config.DEFAULT_COUNTRY_CODE
    )


def from_country(country: str) -> GeoProfile:
    """Build a best-effort consistent profile from an ISO-2 country alone."""
    iso = (country or config.DEFAULT_COUNTRY).upper()
    return GeoProfile(
        country=iso,
        country_code=config.COUNTRY_CALLING_CODES.get(iso, config.DEFAULT_COUNTRY_CODE),
        timezone_offset=config.COUNTRY_DEFAULT_TZ_OFFSET.get(iso, config.TIMEZONE_OFFSET),
        source="country-table",
    )


# ---------------------------------------------------------------------------
# provider parsers -- each returns a GeoProfile or None
# ---------------------------------------------------------------------------
def _parse_ipapi_co(j: dict) -> Optional[GeoProfile]:
    cc = j.get("country_code") or j.get("country")
    if not cc:
        return None
    offset = _parse_offset(j.get("utc_offset"))
    if offset is None:
        offset = config.COUNTRY_DEFAULT_TZ_OFFSET.get(str(cc).upper(), config.TIMEZONE_OFFSET)
    langs = (j.get("languages") or "").split(",")
    return GeoProfile(
        country=cc,
        country_code=_calling_code(j.get("country_calling_code"), cc),
        timezone_offset=offset,
        language=langs[0] or None,
        ip=str(j.get("ip", "")),
        source="ipapi.co",
    )


def _parse_ip_api_com(j: dict) -> Optional[GeoProfile]:
    if j.get("status") and j.get("status") != "success":
        return None
    cc = j.get("countryCode")
    if not cc:
        return None
    offset = _parse_offset(j.get("offset"))
    if offset is None:
        offset = config.COUNTRY_DEFAULT_TZ_OFFSET.get(str(cc).upper(), config.TIMEZONE_OFFSET)
    return GeoProfile(
        country=cc,
        country_code=_calling_code(None, cc),
        timezone_offset=offset,
        ip=str(j.get("query", "")),
        source="ip-api.com",
    )


def _parse_ipwho_is(j: dict) -> Optional[GeoProfile]:
    if j.get("success") is False:
        return None
    cc = j.get("country_code")
    if not cc:
        return None
    tz = j.get("timezone") or {}
    offset = _parse_offset(tz.get("offset"))
    if offset is None:
        offset = _parse_offset(tz.get("utc"))
    if offset is None:
        offset = config.COUNTRY_DEFAULT_TZ_OFFSET.get(str(cc).upper(), config.TIMEZONE_OFFSET)
    return GeoProfile(
        country=cc,
        country_code=_calling_code(j.get("calling_code"), cc),
        timezone_offset=offset,
        ip=str(j.get("ip", "")),
        source="ipwho.is",
    )


def _parse_ipinfo_io(j: dict) -> Optional[GeoProfile]:
    cc = j.get("country")
    if not cc:
        return None
    offset = config.COUNTRY_DEFAULT_TZ_OFFSET.get(str(cc).upper(), config.TIMEZONE_OFFSET)
    return GeoProfile(
        country=cc,
        country_code=_calling_code(None, cc),
        timezone_offset=offset,
        ip=str(j.get("ip", "")),
        source="ipinfo.io",
    )


def _parse_cloudflare_trace(text: str) -> Optional[GeoProfile]:
    loc = ""
    ip = ""
    for line in str(text).splitlines():
        if line.startswith("loc="):
            loc = line[4:].strip()
        elif line.startswith("ip="):
            ip = line[3:].strip()
    if not loc:
        return None
    prof = from_country(loc)
    prof.ip = ip
    prof.source = "cloudflare-trace"
    return prof


_PARSERS = {
    "ipapi.co": _parse_ipapi_co,
    "ip-api.com": _parse_ip_api_com,
    "ipwho.is": _parse_ipwho_is,
    "ipinfo.io": _parse_ipinfo_io,
    "cloudflare.com": _parse_cloudflare_trace,
}


def _provider_key(url: str) -> str:
    for host, _ in _PARSERS.items():
        if host in url:
            return host
    return ""


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------
def detect(session: Any, *, timeout: int = config.GEO_LOOKUP_TIMEOUT) -> Optional[GeoProfile]:
    """
    Detect the egress-IP region using the given transport ``session`` (so the
    client's proxy is honoured). Returns a :class:`GeoProfile`, or ``None`` if no
    provider could be parsed. Never raises.
    """
    for url in config.GEO_PROVIDERS:
        key = _provider_key(url)
        parser = _PARSERS.get(key)
        if parser is None:
            continue
        try:
            resp = session.request("GET", url, headers={"Accept": "*/*"}, timeout=timeout)
            if getattr(resp, "status_code", 0) >= 400:
                continue
            if key == "cloudflare.com":
                prof = parser(getattr(resp, "text", "") or "")
            else:
                data = resp.json()
                if not isinstance(data, dict):
                    continue
                prof = parser(data)
        except Exception as exc:  # noqa: BLE001 -- any failure -> try next provider
            logger.debug("geo provider %s failed: %s", key, exc)
            continue
        if prof is not None:
            logger.info("geo detected %r", prof)
            return prof
    logger.debug("geo: no provider returned a usable result")
    return None
