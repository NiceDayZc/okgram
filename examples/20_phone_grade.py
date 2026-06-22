# -*- coding: utf-8 -*-
"""
20 - Phone-grade sessions: geo auto-sync, routing headers, modes, doctor.

This shows the anti-bounce machinery end to end. Most of it is offline/diagnostic
and safe to run. The geo lookup and the cookie bootstrap touch the network only
when you opt in (a connection / IG_COOKIE).

Env:
    IG_COOKIE   a sessionid or cookie string -> demonstrates bootstrap()
    IG_MODE     "mobile" (default) or "web"  -> web is origin-consistent for a
                browser sessionid
    IG_ONLINE   "1" to also detect your real egress IP in the doctor report
"""
import os

from _common import section, show, COOKIE, SESSION_FILE
from okgram import InstagramAPI, doctor, geo


MODE = os.environ.get("IG_MODE", "mobile")
ONLINE = os.environ.get("IG_ONLINE") == "1"


# ---------------------------------------------------------------------------
section("1) A client keeps one consistent identity (region matches everything)")
cl = InstagramAPI(device_seed="demo-account", mode=MODE, auto_geo=True)
show("mode", cl.mode)
show("region", f"{cl.country} +{cl.country_code} tz={cl.timezone_offset}s eu_dc={cl.eu_dc_enabled}")
show("device", f"{cl.device.profile['manufacturer']} {cl.device.profile['model']} "
                f"(android {cl.device.profile['android_release']})")
show("engine", f"{cl.session.engine} / {cl.session.impersonate}")


# ---------------------------------------------------------------------------
section("2) Geo auto-sync - align to YOUR real egress IP (any country)")
# Detection runs through the client's transport, so it honours any proxy you set.
profile = geo.detect(cl.session)
if profile is None:
    print("  (no network / no provider answered - keeping configured region)")
else:
    show("detected", profile)
    cl.sync_geo(force=True)              # apply it to the client
    show("after sync", f"{cl.country} +{cl.country_code} tz={cl.timezone_offset}s "
                       f"eu_dc={cl.eu_dc_enabled}")
    # every header now agrees with the network:
    h = cl.base_headers
    show("X-IG-App-Startup-Country", h.get("X-IG-App-Startup-Country"))
    show("X-IG-Timezone-Offset", h.get("X-IG-Timezone-Offset"))
    show("X-IG-EU-DC-ENABLED", h.get("X-IG-EU-DC-ENABLED"))


# ---------------------------------------------------------------------------
section("3) Routing headers (IG-U-RUR ...) are captured + echoed + persisted")
# Normally IG sets these; here we show the echo + round-trip mechanically.
cl.user_id = "1234567890"
cl.ig_u_rur = "NCB,1234567890,1700000000:demo"
cl.ig_u_shbid = "12345,1234567890,1700000000:shb"
cl.authorization = "Bearer IGT:2:demo"
h = cl.base_headers
show("IG-U-RUR echoed", h.get("IG-U-RUR"))
show("IG-U-SHBID echoed", h.get("IG-U-SHBID"))
# they survive dump/load (so a reloaded session is the same identity):
bundle = cl.get_settings()
show("bundle keeps ig_u_rur", bundle.get("ig_u_rur"))
cl2 = InstagramAPI(); cl2.set_settings(bundle)
show("restored ig_u_rur", cl2.ig_u_rur)


# ---------------------------------------------------------------------------
section("4) mobile vs web headers (origin consistency)")
mob = InstagramAPI(mode="mobile")
web = InstagramAPI(mode="web")
show("mobile X-IG-App-ID", mob.base_headers.get("X-IG-App-ID"))
show("web    X-IG-App-ID", web.base_headers.get("X-IG-App-ID"))
show("mobile User-Agent", mob.base_headers.get("User-Agent"))
show("web    User-Agent", web.base_headers.get("User-Agent"))


# ---------------------------------------------------------------------------
section("5) bootstrap() a real session from a cookie (set IG_COOKIE to run)")
if COOKIE:
    boot = InstagramAPI(device_seed="demo-account", mode=MODE)
    ok = boot.bootstrap(COOKIE)            # geo -> live config -> install -> warmup
    print(f"  bootstrap -> {'ready' if ok else 'unverified'} as @{boot.username} (id={boot.user_id})")
    boot.dump_settings(SESSION_FILE)
    print(f"  saved identity bundle -> {SESSION_FILE}")
    diag_client = boot
else:
    print("  (skipped - export IG_COOKIE='<sessionid or cookie string>' to try it)")
    diag_client = cl


# ---------------------------------------------------------------------------
section("6) doctor - find WHY a session would bounce")
report = doctor.diagnose(diag_client, online=ONLINE)
print(doctor.render(report))
print("\nCLI equivalent:  okgram doctor --session session.json --online")
