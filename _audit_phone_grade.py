# -*- coding: utf-8 -*-
"""
Offline audit for the phone-grade upgrades:
  - IG-U-RUR / SHBID / SHBTS / region-hint capture + echo + persistence
  - rur/mid cookie capture
  - geo auto-detect parsing (every provider) + consistent apply
  - web vs mobile mode headers (app-id / base url / UA / auth)
  - nav-chain builder, Content-Type on POST, EU-DC from country
  - doctor flags real contradictions
  - bootstrap() end-to-end against a mock network
"""
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from requests.structures import CaseInsensitiveDict
from okgram import InstagramAPI, geo, doctor, behaviors, config

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


# ---- mock network -------------------------------------------------------
class FakeCookies:
    def __init__(self, d=None): self._d = d or {}
    def get(self, k, default=None): return self._d.get(k, default)

class FakeResp:
    def __init__(self, *, headers=None, cookies=None, body=None, status=200):
        self.status_code = status
        self.headers = CaseInsensitiveDict(headers or {})
        self.cookies = FakeCookies(cookies)
        self._body = body if body is not None else {"status": "ok", "user": {"pk": 25025320, "username": "real_name"}}
        self.text = json.dumps(self._body)
    def json(self): return self._body

def client(**kw):
    kw.setdefault("delay_range", None)
    kw.setdefault("device_seed", "cookieacct")
    kw.setdefault("auto_geo", False)
    cl = InstagramAPI(**kw)
    return cl


SID = "25025320%3AAbCdEfGh%3A10%3AsomeTokenValue"

print("=== 1) IG-U-* routing headers: capture from response ===")
cl = client()
resp = FakeResp(headers={
    "ig-set-authorization": "Bearer IGT:2:NEWTOKEN",
    "x-ig-set-www-claim": "hmac.ABCDclaim",
    "ig-set-x-mid": "MIDfromserver",
    "ig-set-ig-u-rur": "NCB,25025320,1799999999:01abc",
    "ig-set-ig-u-shbid": "12345,25025320,1799999999:shb",
    "ig-set-ig-u-shbts": "1799999999",
    "ig-set-ig-u-ig-direct-region-hint": "ATN,25025320,1799999999:dr",
})
cl._update_from_response_headers(resp)
check("authorization captured", cl.authorization == "Bearer IGT:2:NEWTOKEN")
check("www_claim captured", cl.ig_www_claim == "hmac.ABCDclaim")
check("mid captured", cl.mid == "MIDfromserver")
check("ig_u_rur captured", cl.ig_u_rur == "NCB,25025320,1799999999:01abc")
check("ig_u_shbid captured", cl.ig_u_shbid.startswith("12345"))
check("ig_u_shbts captured", cl.ig_u_shbts == "1799999999")
check("direct_region_hint captured", cl.ig_direct_region_hint.startswith("ATN"))

print("\n=== 2) IG-U-* echoed back in base_headers ===")
cl.user_id = "25025320"
h = cl.base_headers
check("IG-U-RUR echoed", h.get("IG-U-RUR") == "NCB,25025320,1799999999:01abc")
check("IG-U-SHBID echoed", h.get("IG-U-SHBID", "").startswith("12345"))
check("IG-U-SHBTS echoed", h.get("IG-U-SHBTS") == "1799999999")
check("IG-U-DIRECT-REGION-HINT echoed", h.get("IG-U-IG-DIRECT-REGION-HINT", "").startswith("ATN"))
check("Authorization echoed", h.get("Authorization") == "Bearer IGT:2:NEWTOKEN")
check("X-MID echoed", h.get("X-MID") == "MIDfromserver")

print("\n=== 3) authorization '0' clears; rur/mid cookies captured ===")
cl2 = client()
cl2._update_from_response_headers(FakeResp(headers={"ig-set-authorization": "Bearer IGT:2:T"}))
check("auth set first", cl2.authorization == "Bearer IGT:2:T")
cl2._update_from_response_headers(FakeResp(headers={"ig-set-authorization": "0"}))
check("auth cleared on '0'", cl2.authorization == "")
cl3 = client()
cl3._update_from_response_headers(FakeResp(cookies={"rur": "RURCOOKIE", "mid": "MIDCOOKIE", "csrftoken": "CS"}))
check("rur cookie -> ig_u_rur", cl3.ig_u_rur == "RURCOOKIE")
check("mid cookie -> mid", cl3.mid == "MIDCOOKIE")
check("csrftoken cookie", cl3.csrftoken == "CS")

print("\n=== 4) settings round-trip preserves IG-U-* + geo + mode ===")
cl.ig_direct_region_hint = "ATN,1,1:dr"
cl.geo = geo.from_country("TH")
s = cl.get_settings()
for k in ("ig_u_rur", "ig_u_shbid", "ig_u_shbts", "ig_direct_region_hint", "mode", "geo", "eu_dc_enabled", "bloks_version_id"):
    check(f"settings has '{k}'", k in s)
cl_new = client()
cl_new.set_settings(s)
check("rur restored", cl_new.ig_u_rur == cl.ig_u_rur)
check("shbid restored", cl_new.ig_u_shbid == cl.ig_u_shbid)
check("region-hint restored", cl_new.ig_direct_region_hint == "ATN,1,1:dr")
check("geo restored", cl_new.geo is not None and cl_new.geo.country == "TH")

print("\n=== 5) geo provider parsers (every provider) ===")
p = geo._parse_ipapi_co({"country_code": "JP", "country_calling_code": "+81", "utc_offset": "+0900", "languages": "ja", "ip": "1.2.3.4"})
check("ipapi.co JP +81 tz32400", p.country == "JP" and p.country_code == 81 and p.timezone_offset == 32400)
p = geo._parse_ip_api_com({"status": "success", "countryCode": "DE", "offset": 7200, "query": "5.6.7.8"})
check("ip-api.com DE +49 tz7200 eu", p.country == "DE" and p.country_code == 49 and p.timezone_offset == 7200 and p.eu_dc == "true")
p = geo._parse_ipwho_is({"success": True, "country_code": "US", "calling_code": "1", "timezone": {"offset": -25200}, "ip": "9.9.9.9"})
check("ipwho.is US +1 tz-25200", p.country == "US" and p.country_code == 1 and p.timezone_offset == -25200 and p.eu_dc == "false")
p = geo._parse_cloudflare_trace("fl=abc\nip=2.2.2.2\nloc=BR\ntls=TLSv1.3")
check("cloudflare BR from table", p is not None and p.country == "BR" and p.country_code == 55)

print("\n=== 6) geo.detect through a fake session + apply consistency ===")
cl_g = client(auto_geo=True)
cl_g.session.request = lambda *a, **k: FakeResp(body={"country_code": "GB", "country_calling_code": "+44", "utc_offset": "+0000", "ip": "8.8.8.8"})
prof = cl_g.sync_geo(force=True)
check("sync_geo applied GB", prof is not None and cl_g.country == "GB")
check("country_code aligned +44", cl_g.country_code == 44)
check("eu_dc set true for GB", cl_g.eu_dc_enabled == "true")
h = cl_g.base_headers
check("startup-country header = GB", h.get("X-IG-App-Startup-Country") == "GB")
check("tz header matches", h.get("X-IG-Timezone-Offset") == str(cl_g.timezone_offset))

print("\n=== 7) web vs mobile mode ===")
m = client(mode="mobile")
check("mobile app-id 567...", m.base_headers.get("X-IG-App-ID") == config.APP_ID)
w = client(mode="web")
wh = w.base_headers
check("web app-id 936...", wh.get("X-IG-App-ID") == config.WEB_APP_ID)
check("web UA is browser", wh.get("User-Agent", "").startswith("Mozilla/5.0"))
check("web has Sec-Fetch-Site", wh.get("Sec-Fetch-Site") == "same-origin")
# web mode imports a sessionid WITHOUT reconstructing a Bearer
w.session.request = lambda *a, **k: FakeResp()
w.login_by_cookie(SID, verify=False)
check("web mode: no Bearer reconstructed", not w.authorization)
mm = client(mode="mobile")
mm.session.request = lambda *a, **k: FakeResp()
mm.login_by_cookie(SID, verify=False)
check("mobile mode: Bearer reconstructed", mm.authorization.startswith("Bearer IGT:2:"))

print("\n=== 8) nav-chain builder ===")
cn = client()
behaviors.push_nav(cn, "cold_start", "cold_start")
behaviors.push_nav(cn, "feed", "cold_start")
behaviors.push_nav(cn, "profile")
check("nav_chain non-empty", bool(cn.nav_chain))
check("nav_chain has feed module", "MainFeedFragment" in cn.nav_chain)
check("nav_chain in headers when set", cn.base_headers.get("X-IG-Nav-Chain") == cn.nav_chain)

print("\n=== 9) Content-Type on POST, none on GET ===")
captured = {}
cp = client()
def cap(method, url, **kw):
    captured["method"] = method
    captured["headers"] = kw.get("headers", {})
    return FakeResp()
cp.session.request = cap
cp.private_request("some/endpoint/", data={"a": "b"})
check("POST sets Content-Type form", "x-www-form-urlencoded" in captured["headers"].get("Content-Type", ""))
cp.private_request("some/endpoint/")  # GET
check("GET has no Content-Type", "Content-Type" not in captured["headers"])

print("\n=== 10) EU-DC auto from country at construct time ===")
check("DE client eu_dc true", client(country="DE", country_code=49).eu_dc_enabled == "true")
check("TH client eu_dc false", client(country="TH").eu_dc_enabled == "false")

print("\n=== 11) doctor flags a real contradiction (US country + Bangkok tz) ===")
bad = client(country="US", country_code=1)
bad.timezone_offset = 25200  # +7 while claiming US
rep = doctor.diagnose(bad, online=False)
tzc = next((c for c in rep["checks"] if c["name"] == "timezone"), None)
check("doctor catches tz/country contradiction", tzc and tzc["status"] == "fail")
good = client(country="TH")
rep2 = doctor.diagnose(good, online=False)
check("doctor clean for consistent TH", rep2["fails"] == 0)

print("\n=== 12) bootstrap() end-to-end (mock net) ===")
cb = client(auto_geo=True)
cb.session.request = lambda *a, **k: FakeResp(
    headers={"ig-set-ig-u-rur": "RURX", "ig-set-x-mid": "MIDX", "x-ig-set-www-claim": "claimX"},
    body={"status": "ok", "user": {"pk": 25025320, "username": "real_name"}},
)
ok = cb.bootstrap(SID, verify=True, warmup=True)
check("bootstrap returns True", ok is True)
check("bootstrap set username", cb.username == "real_name")
check("bootstrap captured rur via warmup", cb.ig_u_rur == "RURX")
check("bootstrap captured mid", cb.mid == "MIDX")

print("\n=== 13) offset parsing (clock needs explicit marker; minutes validated) ===")
from okgram.geo import _parse_offset
check("'+0700' -> 25200", _parse_offset("+0700") == 25200)
check("'07:00' -> 25200", _parse_offset("07:00") == 25200)
check("'-05:00' -> -18000", _parse_offset("-05:00") == -18000)
check("'25200' (bare) -> 25200 seconds", _parse_offset("25200") == 25200)
check("'7200' (bare) -> 7200 seconds", _parse_offset("7200") == 7200)
check("'+0560' (bad minutes) -> None", _parse_offset("+0560") is None)
check("int 7200 -> 7200", _parse_offset(7200) == 7200)

print("\n=== 14) auth clears ONLY on '0' (payload-less bearer is kept) ===")
ca = client()
ca._update_from_response_headers(FakeResp(headers={"ig-set-authorization": "Bearer IGT:2:REAL"}))
ca._update_from_response_headers(FakeResp(headers={"ig-set-authorization": "Bearer IGT:2:"}))
check("payload-less bearer NOT treated as clear", ca.authorization == "Bearer IGT:2:")
ca._update_from_response_headers(FakeResp(headers={"ig-set-authorization": "0"}))
check("'0' clears auth", ca.authorization == "")

print("\n=== 15) load_settings mode change rebuilds transport (no phone TLS on web) ===")
cm = client(mode="mobile")
check("starts tls_client(OkHttp) in mobile", cm.session.engine == "tls_client")
web_bundle = client(mode="web").get_settings()
cm.set_settings(web_bundle)
check("mode switched to web", cm.mode == "web")
check("transport rebuilt off OkHttp", cm.session.engine != "tls_client")
check("_transport_mode tracks web", getattr(cm, "_transport_mode", None) == "web")

print("\n=== 16) bootstrap is best-effort even if verify raises ===")
from okgram.exceptions import LoginRequired
cbx = client(auto_geo=False)
def boom(*a, **k):
    raise LoginRequired("session expired")
cbx.session.request = boom
ok = cbx.bootstrap(SID, verify=True, warmup=False, sync_geo=False, sync_config=False)
check("bootstrap returns False (no traceback) on verify failure", ok is False)

print("\n" + "=" * 52)
npass = sum(1 for _, s in results if s)
print(f"Total: {npass}/{len(results)} PASS")
print("ALL PASS" if npass == len(results) else "SOME FAILED: " + ", ".join(n for n, s in results if not s))
sys.exit(0 if npass == len(results) else 1)
