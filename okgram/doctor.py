"""
Session doctor -- explain *why* a session is likely to bounce, before it does.

``diagnose(client)`` runs a battery of consistency checks over the client's
identity (region, routing headers, device, transport, session origin) and returns
a structured report. With ``online=True`` it also detects the real egress IP and
flags a region that contradicts it. ``render()`` turns the report into a readable
console block.

This is the single most useful tool for a "sessionid keeps getting logged out"
problem: it pinpoints the exact contradiction (e.g. country=US but a Bangkok
timezone, or a missing IG-U-RUR) instead of guessing.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import config

OK = "ok"
WARN = "warn"
FAIL = "fail"
INFO = "info"

_ICON = {OK: "[ OK ]", WARN: "[WARN]", FAIL: "[FAIL]", INFO: "[INFO]"}


def _check(name: str, status: str, detail: str, fix: str = "") -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def diagnose(client: Any, *, online: bool = False) -> Dict[str, Any]:
    """Return a structured consistency report for ``client``."""
    checks: List[Dict[str, str]] = []

    mode = getattr(client, "mode", config.MODE_MOBILE)
    country = (getattr(client, "country", "") or "").upper()
    cc = getattr(client, "country_code", None)
    tz = getattr(client, "timezone_offset", None)
    locale = getattr(client, "locale", "")
    eu_dc = str(getattr(client, "eu_dc_enabled", "false")).lower()

    # --- mode ------------------------------------------------------------
    checks.append(_check("mode", INFO, f"request mode = {mode}"))

    # --- region: calling code matches country ---------------------------
    expected_cc = config.COUNTRY_CALLING_CODES.get(country)
    if expected_cc is None:
        checks.append(_check("country", WARN, f"unknown country '{country}'",
                             "set country to a valid ISO-2 code (or run sync_geo)"))
    elif cc != expected_cc:
        checks.append(_check(
            "calling_code", FAIL,
            f"country={country} but country_code={cc} (expected {expected_cc})",
            "run cl.sync_geo() or set country_code to match the country",
        ))
    else:
        checks.append(_check("calling_code", OK, f"country={country} code=+{cc}"))

    # --- region: timezone is plausible for the country ------------------
    exp_tz = config.COUNTRY_DEFAULT_TZ_OFFSET.get(country)
    if exp_tz is not None and tz is not None:
        # allow up to 3h spread (DST + multi-tz countries) before flagging
        if abs(int(tz) - exp_tz) > 3 * 3600:
            checks.append(_check(
                "timezone", FAIL,
                f"timezone_offset={tz}s contradicts country={country} "
                f"(typical {exp_tz}s) -- a classic bounce trigger",
                "run cl.sync_geo() so tz matches the egress IP's region",
            ))
        else:
            checks.append(_check("timezone", OK, f"tz={tz}s consistent with {country}"))
    else:
        checks.append(_check("timezone", INFO, f"tz={tz}s (no reference for {country})"))

    # --- region: EU-DC flag matches the country -------------------------
    should_eu = country in config.EU_DC_COUNTRIES
    if should_eu and eu_dc != "true":
        checks.append(_check("eu_dc", WARN, f"{country} is EU but X-IG-EU-DC-ENABLED={eu_dc}",
                             "run cl.sync_geo() (sets eu_dc automatically)"))
    elif (not should_eu) and eu_dc == "true":
        checks.append(_check("eu_dc", WARN, f"{country} is not EU but eu_dc=true",
                             "run cl.sync_geo()"))
    else:
        checks.append(_check("eu_dc", OK, f"eu_dc={eu_dc} matches {country}"))

    # --- locale vs region (informational, not a failure) ----------------
    loc_region = locale.split("_")[-1].upper() if "_" in locale else ""
    if loc_region and country and loc_region != country:
        checks.append(_check(
            "locale", INFO,
            f"UI locale={locale} (region {loc_region}) differs from country={country}"
            " -- acceptable (e.g. English UI on a local SIM), but matching is safer",
        ))
    else:
        checks.append(_check("locale", OK, f"locale={locale}"))

    # --- routing headers / session continuity ---------------------------
    has_sid = bool(client.session.cookies.get("sessionid")) if hasattr(client, "session") else False
    authed = bool(getattr(client, "authorization", "")) or has_sid
    mid = getattr(client, "mid", "")
    claim = getattr(client, "ig_www_claim", "0")
    rur = getattr(client, "ig_u_rur", "")

    checks.append(_check(
        "authenticated", OK if authed else WARN,
        "session present" if authed else "no session (no Bearer / sessionid)",
        "" if authed else "import a sessionid (bootstrap) or login()",
    ))
    if authed:
        checks.append(_check("X-MID", OK if mid else WARN,
                             f"mid={'set' if mid else 'MISSING'}",
                             "" if mid else "run cl.sync_config()/bootstrap to obtain a mid"))
        checks.append(_check(
            "IG-U-RUR", OK if rur else WARN,
            f"routing header rur={'set' if rur else 'MISSING'}",
            "" if rur else "make one authenticated request (warmup) so IG sets rur, "
                           "then dump_settings -- missing rur is a top bounce cause",
        ))
        checks.append(_check(
            "www_claim", OK if claim not in ("", "0") else WARN,
            f"X-IG-WWW-Claim={'set' if claim not in ('', '0') else 'default 0'}",
            "" if claim not in ("", "0") else "run warmup so the server issues a claim",
        ))

    # --- session origin vs mode -----------------------------------------
    if has_sid and mode == config.MODE_MOBILE and claim in ("", "0"):
        checks.append(_check(
            "origin", WARN,
            "a sessionid (likely web-origin) is being used in MOBILE mode and the "
            "server has not issued a www-claim yet -- if it bounces, try mode='web' "
            "(origin-consistent with a browser sessionid)",
            "okgram ... --mode web   (or InstagramAPI(mode='web'))",
        ))

    # --- device stability ------------------------------------------------
    dev = getattr(client, "device", None)
    if dev is not None:
        ok_dev = bool(getattr(dev, "uuid", "")) and bool(getattr(dev, "family_device_id", ""))
        checks.append(_check(
            "device", OK if ok_dev else FAIL,
            f"{dev.profile.get('manufacturer')} {dev.profile.get('model')} "
            f"android {dev.profile.get('android_release')} uuid={'set' if ok_dev else 'MISSING'}",
            "" if ok_dev else "recreate the device; bind it per account with device_seed=username",
        ))

    # --- transport / TLS -------------------------------------------------
    engine = getattr(getattr(client, "session", None), "engine", "?")
    if engine == "requests":
        checks.append(_check("transport", WARN, "engine=requests (weak Python TLS fingerprint)",
                             "pip install tls-client (mobile) or curl_cffi (web)"))
    else:
        checks.append(_check("transport", OK, f"engine={engine} "
                             f"impersonate={getattr(client.session, 'impersonate', '?')}"))

    # --- online egress check --------------------------------------------
    if online and hasattr(client, "session"):
        from . import geo as geo_mod
        prof = geo_mod.detect(client.session)
        if prof is None:
            checks.append(_check("egress", INFO, "could not detect egress IP region (offline?)"))
        elif prof.country.upper() != country:
            checks.append(_check(
                "egress", FAIL,
                f"egress IP is in {prof.country} (ip={prof.ip}) but client claims {country}"
                " -- the server sees a region mismatch on every request",
                "run cl.sync_geo() to align to the egress IP, or use a proxy in "
                f"{country}",
            ))
        else:
            checks.append(_check("egress", OK, f"egress IP region {prof.country} matches client"))

        # live TLS / HTTP-2 fingerprint proof
        from . import fingerprint as fp_mod
        fp = fp_mod.summary(client)
        grade = fp.get("grade")
        status = OK if grade in ("phone", "browser", "ok") else (
            INFO if grade == "unknown" else WARN
        )
        checks.append(_check(
            "fingerprint", status,
            f"{fp.get('verdict')} (http={(fp.get('fingerprint') or {}).get('http_version')}, "
            f"ja3={(fp.get('fingerprint') or {}).get('ja3_hash')})",
            "" if status != WARN else "install tls-client (mobile) / curl_cffi (web)",
        ))

    n_fail = sum(1 for c in checks if c["status"] == FAIL)
    n_warn = sum(1 for c in checks if c["status"] == WARN)
    verdict = (
        "CRITICAL -- fix the FAILs before using this session" if n_fail
        else "OK with warnings -- review the WARNs" if n_warn
        else "healthy -- identity is internally consistent"
    )
    return {"checks": checks, "fails": n_fail, "warns": n_warn, "verdict": verdict}


def render(report: Dict[str, Any]) -> str:
    """Render a diagnose() report as a console block."""
    lines = ["okgram doctor -- session identity report", "=" * 44]
    for c in report["checks"]:
        line = f"{_ICON.get(c['status'], '[?]')} {c['name']}: {c['detail']}"
        lines.append(line)
        if c.get("fix") and c["status"] in (WARN, FAIL):
            lines.append(f"        -> fix: {c['fix']}")
    lines.append("=" * 44)
    lines.append(
        f"{report['fails']} fail / {report['warns']} warn  =>  {report['verdict']}"
    )
    return "\n".join(lines)
