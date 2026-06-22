"""
Live config sync -- fetch the values that legitimately change, from IG itself.

A real Instagram app does not ship every server value baked in: on cold start it
hits ``launcher/sync`` and ``qe/sync`` to pull the current server-driven config
(experiment rollouts, the password-encryption public key, the expected bloks
version, routing hints) and reads a batch of ``ig-set-*`` response headers
(authorization, www-claim, mid, IG-U-RUR ...). Hard-coding those guarantees drift
from what the server expects -> flags.

This module performs that sync against the live backend and lets the client adopt
the fresh values. It is best-effort and never raises: if the network is down or a
call is rejected, the client keeps its last-known-good values.

The actual header capture lives in the request chokepoint
(:meth:`PrivateRequestMixin._update_from_response_headers`); this module only
*orchestrates the cold-start calls* and harvests body-level config.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from . import config

logger = logging.getLogger("okgram")


def sync(client: Any, *, login: bool = False, force: bool = False) -> Dict[str, Any]:
    """
    Run the cold-start config sync (launcher/sync + qe/sync) and adopt any fresh
    server values. Returns a small report dict; never raises.

    Parameters
    ----------
    login : bool
        True during the pre-login phase (no auth token yet) -- the calls are sent
        in login mode so a missing Authorization header is not an error.
    force : bool
        re-sync even if it was synced recently.
    """
    report: Dict[str, Any] = {"ran": [], "adopted": {}, "errors": []}

    last = getattr(client, "_live_config_synced_at", 0.0)
    if not force and last and (time.time() - last) < 1800:
        report["skipped"] = "synced recently"
        return report

    uuid = getattr(client.device, "uuid", "")
    calls = (
        ("launcher/sync/", {"id": uuid, "server_config_retrieval": "1"}, None),
        (
            "qe/sync/",
            {"id": uuid, "server_config_retrieval": "1", "experiments": ""},
            {"X-DEVICE-ID": uuid},
        ),
    )

    for endpoint, data, headers in calls:
        try:
            result = client.private_request(
                endpoint, data, login=login, headers=headers, retries=0
            )
            report["ran"].append(endpoint)
            _adopt_from_body(client, result, report)
        except Exception as exc:  # noqa: BLE001 -- best effort
            report["errors"].append(f"{endpoint}: {type(exc).__name__}")
            logger.debug("live_config sync %s failed: %s", endpoint, exc)

    # the password key + routing headers are captured by the request layer; pull
    # the key into auth state too (mirrors AuthMixin._capture_password_key).
    if hasattr(client, "_capture_password_key"):
        try:
            client._capture_password_key()
        except Exception:  # noqa: BLE001
            pass

    client._live_config_synced_at = time.time()
    return report


def _adopt_from_body(client: Any, result: Any, report: Dict[str, Any]) -> None:
    """Adopt dynamic values that some config responses carry in the JSON body."""
    if not isinstance(result, dict):
        return

    # Some launcher/sync payloads expose the bloks version the server expects.
    for key in ("bloks_version_id", "bloks_version", "client_doc_id"):
        val = result.get(key)
        if isinstance(val, str) and len(val) >= 16:
            if getattr(client, "bloks_version_id", None) != val:
                client.bloks_version_id = val
                report["adopted"]["bloks_version_id"] = val
            break

    # qe/sync sometimes returns the rollout/config that bumps capabilities hints.
    cfg = result.get("configs") or result.get("config")
    if isinstance(cfg, dict):
        report["adopted"]["configs"] = len(cfg)


def effective_bloks_version(client: Any) -> str:
    """The bloks version to send: live-synced value if present, else the default."""
    return getattr(client, "bloks_version_id", None) or config.BLOKS_VERSION_ID


def needs_geo(client: Any) -> bool:
    """Whether the client should (re)detect geo: no profile yet, or it went stale."""
    geo = getattr(client, "geo", None)
    if geo is None:
        return True
    try:
        return not geo.is_fresh()
    except Exception:  # noqa: BLE001
        return True


def maybe_sync_geo(client: Any, *, force: bool = False) -> Optional[Any]:
    """
    Detect + apply geo if needed (or forced). Returns the applied GeoProfile or
    None. Pulls through the client's own transport so the proxy is honoured.
    Best-effort: any failure leaves the client's region untouched.
    """
    from . import geo as geo_mod

    if not force and not needs_geo(client):
        return getattr(client, "geo", None)
    try:
        profile = geo_mod.detect(client.session)
    except Exception as exc:  # noqa: BLE001
        logger.debug("geo detect failed: %s", exc)
        profile = None
    if profile is None:
        return getattr(client, "geo", None)
    apply_geo(client, profile)
    return profile


def apply_geo(client: Any, profile: Any, *, set_locale: bool = False) -> None:
    """Apply a GeoProfile to the client so every header/payload stays consistent."""
    client.geo = profile
    client.country = profile.country
    client.country_code = profile.country_code
    client.timezone_offset = profile.timezone_offset
    client.eu_dc_enabled = profile.eu_dc
    if set_locale and profile.language:
        # turn 'th' / 'en' into a locale like 'th_TH' / 'en_US'
        lang = profile.language.split("-")[0].split("_")[0].lower()
        client.locale = f"{lang}_{profile.country}"
    logger.info(
        "geo applied: country=%s cc=%s tz=%s eu_dc=%s",
        profile.country, profile.country_code, profile.timezone_offset, profile.eu_dc,
    )
