# -*- coding: utf-8 -*-
"""Verify login_by_cookie (all formats) + Bearer reconstruction + pigeon stability (offline)."""
import base64
import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from requests.structures import CaseInsensitiveDict
from okgram import InstagramAPI
from okgram.exceptions import ClientError

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


# ---- mock network returning a logged-in user ----
class FakeCookies:
    def get(self, k, d=None): return d
class FakeResp:
    status_code = 200
    def __init__(self): self.headers = CaseInsensitiveDict(); self.cookies = FakeCookies(); self.text = "{}"
    def json(self): return {"status": "ok", "user": {"pk": 25025320, "username": "real_name"}}

def client():
    cl = InstagramAPI(delay_range=None, device_seed="cookieacct")
    cl.session.request = lambda *a, **k: FakeResp()
    return cl


SID = "25025320%3AAbCdEfGh%3A10%3AsomeTokenValue"

print("=== 1) parse_cookies — every format ===")
P = InstagramAPI.parse_cookies
fmts = {
    "header string": f"sessionid={SID}; ds_user_id=25025320; csrftoken=CSRF123; mid=MIDxyz; ig_did=DID",
    "Cookie: prefix": f"Cookie: sessionid={SID}; csrftoken=CSRF123",
    "dict": {"sessionid": SID, "ds_user_id": "25025320"},
    "json list": json.dumps([
        {"name": "sessionid", "value": SID, "domain": ".instagram.com"},
        {"name": "ds_user_id", "value": "25025320"},
        {"name": "csrftoken", "value": "CSRF123"},
    ]),
    "json dict": json.dumps({"sessionid": SID, "mid": "MIDxyz"}),
    "netscape": "\n".join([
        "# Netscape HTTP Cookie File",
        f".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{SID}",
        ".instagram.com\tTRUE\t/\tTRUE\t0\tds_user_id\t25025320",
    ]),
    "bare sessionid": SID,
}
for label, raw in fmts.items():
    d = P(raw)
    check(f"{label}: sessionid parsed", d.get("sessionid") == SID)

print("\n=== 2) login_by_cookie (header string) — jar/user/token/verify ===")
cl = client()
ok = cl.login_by_cookie(fmts["header string"])
check("returns True (verified)", ok is True)
check("user_id from server (pk)", cl.user_id == "25025320")
check("username from server", cl.username == "real_name")
check("csrftoken carried", cl.csrftoken == "CSRF123")
check("mid carried", cl.mid == "MIDxyz")
check("sessionid in jar", cl.session.cookies.get("sessionid") == SID)
# decode reconstructed Bearer
assert cl.authorization.startswith("Bearer IGT:2:")
blob = json.loads(base64.b64decode(cl.authorization.split("IGT:2:", 1)[1]))
check("Bearer has ds_user_id", blob.get("ds_user_id") == "25025320")
check("Bearer has sessionid", blob.get("sessionid") == SID)

print("\n=== 3) login_by_cookie (json list) ===")
cl = client()
check("json list login ok", cl.login_by_cookie(fmts["json list"]) is True)

print("\n=== 4) login_by_cookie (bare sessionid) + login_by_sessionid delegate ===")
cl = client()
check("bare sessionid login ok", cl.login_by_cookie(SID) is True)
cl2 = client()
check("login_by_sessionid still works", cl2.login_by_sessionid(SID) is True)
check("login_by_sessionid now sets Bearer", cl2.authorization.startswith("Bearer IGT:2:"))

print("\n=== 5) errors ===")
cl = client()
try:
    cl.login_by_cookie("foo=bar; baz=qux")   # no sessionid
    check("missing sessionid raises", False)
except ClientError:
    check("missing sessionid raises ClientError", True)

print("\n=== 6) verify=False (no network) ===")
cl = InstagramAPI(delay_range=None, device_seed="x")
check("verify=False returns True without network", cl.login_by_cookie(SID, verify=False) is True)

print("\n=== 7) X-Pigeon-Session-Id stability (phone-like) ===")
cl = InstagramAPI(delay_range=None, device_seed="p1")
h1 = cl.base_headers["X-Pigeon-Session-Id"]
h2 = cl.base_headers["X-Pigeon-Session-Id"]
check("pigeon stable across requests (same instance)", h1 == h2)
clb = InstagramAPI(delay_range=None, device_seed="p2")
check("pigeon differs across instances", clb.base_headers["X-Pigeon-Session-Id"] != h1)
# rawclienttime must still change per request
t1 = cl.base_headers["X-Pigeon-Rawclienttime"]; import time; time.sleep(0.01)
t2 = cl.base_headers["X-Pigeon-Rawclienttime"]
check("rawclienttime changes per request", t1 != t2)

print("\n" + "=" * 50)
npass = sum(1 for _, s in results if s)
print(f"Total: {npass}/{len(results)} PASS")
print("ALL PASS" if npass == len(results) else "SOME FAILED: " + ", ".join(n for n, s in results if not s))
