"""
Consistency guard + smart retry.

`verify_egress` checks that the **egress IP's region still matches the session's
region** before you act. A session minted in TH that suddenly egresses from a US
IP is the textbook instant-challenge trigger; catching it *before* sending beats
getting bounced after.

`retry_wait` computes a polite backoff that honours IG's ``Retry-After`` header
(and the ``ig-set-*`` throttle hints) instead of a blind fixed sleep.
"""
from __future__ import annotations

import logging
import random
from typing import Any, Dict, Optional

from . import config
from .exceptions import EgressMismatch

logger = logging.getLogger("okgram")


def verify_egress(client: Any, *, policy: str = "resync") -> Dict[str, Any]:
    """
    Compare the egress-IP region to the client's configured region.

    policy:
        "resync" -> on mismatch, re-align the client to the egress IP (and warn)
        "raise"  -> on mismatch, raise EgressMismatch (don't send anything)
        "warn"   -> just log and report

    Returns a report dict; never raises unless policy="raise" on a real mismatch.
    """
    from . import geo as geo_mod

    report: Dict[str, Any] = {
        "ok": True, "session_country": getattr(client, "country", None),
        "egress_country": None, "egress_ip": None, "action": "none",
    }
    prof = geo_mod.detect(client.session)
    if prof is None:
        report["action"] = "skipped (no geo)"
        return report

    report["egress_country"] = prof.country
    report["egress_ip"] = prof.ip
    session_country = (getattr(client, "country", "") or "").upper()
    if prof.country.upper() == session_country:
        return report

    report["ok"] = False
    msg = (f"egress IP is in {prof.country} (ip {prof.ip}) but the session is "
           f"{session_country} -- sending now risks a challenge")
    if policy == "raise":
        raise EgressMismatch(msg)
    if policy == "resync":
        from . import live_config
        live_config.apply_geo(client, prof)
        report["action"] = f"resynced -> {prof.country}"
        logger.warning("%s; resynced region to egress", msg)
    else:  # warn
        report["action"] = "warned"
        logger.warning(msg)
    return report


def retry_after_seconds(resp: Any) -> Optional[float]:
    """Read a ``Retry-After`` header (seconds form) from a response, if present."""
    if resp is None:
        return None
    try:
        val = resp.headers.get("Retry-After") or resp.headers.get("retry-after")
    except Exception:  # noqa: BLE001
        return None
    if not val:
        return None
    try:
        return float(str(val).strip())
    except (TypeError, ValueError):
        return None


def retry_wait(exc: Any, attempt: int, base: float = config.RETRY_BACKOFF) -> float:
    """
    Backoff seconds for retry ``attempt`` (0-based). Honours ``Retry-After`` from
    the exception's response when available; otherwise exponential with jitter.
    """
    resp = getattr(exc, "response", None)
    ra = retry_after_seconds(resp)
    if ra is not None:
        return ra + random.uniform(0, 1.0)        # small jitter on top of the hint
    return base * (2 ** attempt) + random.uniform(0, base)
