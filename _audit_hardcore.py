# -*- coding: utf-8 -*-
"""
Offline audit for the hardcore layer:
  - RateGovernor: classify, hourly/daily caps, sleep-window, cooldown, persistence,
    and integration into private_request (write gating, feedback cooldown)
  - guard: verify_egress (resync/raise/warn), Retry-After aware backoff
  - fingerprint: probe parsing + grade classification
  - store: AES-GCM encryption round-trip, proxy binding/masking, add/open
"""
import io
import json
import os
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from requests.structures import CaseInsensitiveDict
from okgram import InstagramAPI, RateGovernor, SessionStore, guard, fingerprint, limits
from okgram.exceptions import (
    RateLimitReached, EgressMismatch, ClientThrottledError, FeedbackRequired,
)

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


class FakeCookies:
    def __init__(self, d=None): self._d = d or {}
    def get(self, k, default=None): return self._d.get(k, default)

class FakeResp:
    def __init__(self, *, headers=None, cookies=None, body=None, status=200):
        self.status_code = status
        self.headers = CaseInsensitiveDict(headers or {})
        self.cookies = FakeCookies(cookies)
        self._body = body if body is not None else {"status": "ok", "user": {"pk": 1, "username": "u"}}
        self.text = json.dumps(self._body)
    def json(self): return self._body

def client(**kw):
    kw.setdefault("delay_range", None)
    kw.setdefault("auto_geo", False)
    kw.setdefault("device_seed", "acct")
    return InstagramAPI(**kw)


print("=== 1) governor: endpoint classification ===")
g = RateGovernor(think_time=None)
check("like", g.classify("media/123/like/") == "like")
check("unlike", g.classify("media/123/unlike/") == "unlike")
check("comment before like", g.classify("media/123/comment/") == "comment")
check("follow", g.classify("friendships/create/9/") == "follow")
check("unfollow", g.classify("friendships/destroy/9/") == "unfollow")
check("dm", g.classify("direct_v2/threads/broadcast/text/") == "dm")
check("save", g.classify("media/1/save/") == "save")
check("read exempt (timeline)", g.classify("feed/timeline/") is None)
check("read exempt (user info)", g.classify("users/9/info/") is None)

print("\n=== 2) governor: hourly + daily caps (raise mode) ===")
g = RateGovernor(think_time=None, mode="raise", limits={"like": (2, 3)})
g.gate("media/1/like/"); g.gate("media/2/like/")
try:
    g.gate("media/3/like/"); check("hourly cap raises", False)
except RateLimitReached:
    check("hourly cap raises", True)
check("counts reflect 2 likes", g.counts("like")[0] == 2)
gd = RateGovernor(think_time=None, mode="raise", limits={"follow": (100, 2)})
gd.gate("friendships/create/1/"); gd.gate("friendships/create/2/")
try:
    gd.gate("friendships/create/3/"); check("daily cap raises", False)
except RateLimitReached:
    check("daily cap raises", True)

print("\n=== 3) governor: sleep window + cooldown ===")
gw = RateGovernor(think_time=None, timezone_offset=0, sleep_window=(0, 24))  # always "asleep"
try:
    gw.gate("media/1/like/"); check("sleep window blocks", False)
except RateLimitReached:
    check("sleep window blocks", True)
gc = RateGovernor(think_time=None, mode="raise")
sec = gc.note_block()
check("note_block sets cooldown ~5m", 290 <= sec <= 301)
check("consecutive grows backoff", gc.note_block() > sec)
try:
    gc.gate("media/1/like/"); check("cooldown blocks gate", False)
except RateLimitReached:
    check("cooldown blocks gate", True)
gc.note_success()
check("note_success resets streak", gc._consecutive_blocks == 0)

print("\n=== 4) governor: persistence round-trip ===")
g = RateGovernor(think_time=None)
g.gate("media/1/like/"); g.gate("friendships/create/2/")
snap = g.to_dict()
g2 = RateGovernor(think_time=None)
g2.load_dict(snap)
check("restored like count", g2.counts("like")[1] == 1)
check("restored follow count", g2.counts("follow")[1] == 1)

print("\n=== 5) governor: wired into private_request (write gated, read not) ===")
cl = client(govern=True, max_retries=0)
cl.governor = RateGovernor(think_time=None, mode="raise", limits={"like": (1, 5)})
cl.session.request = lambda *a, **k: FakeResp()
cl.private_request("media/1/like/", data={"x": "1"})  # first like ok
try:
    cl.private_request("media/2/like/", data={"x": "1"}); check("2nd like gated -> raise", False)
except RateLimitReached:
    check("2nd like gated -> raise", True)
# reads are never gated even as POST (timeline)
calls = {"n": 0}
def count_req(*a, **k):
    calls["n"] += 1
    return FakeResp()
cl.session.request = count_req
for _ in range(5):
    cl.private_request("feed/timeline/", data={"r": "cold"})
check("timeline POST never gated", calls["n"] == 5)

print("\n=== 6) governor: feedback_required triggers cooldown (no retry) ===")
clf = client(govern=True, max_retries=2)
clf.governor = RateGovernor(think_time=None)
sends = {"n": 0}
def fb(*a, **k):
    sends["n"] += 1
    return FakeResp(status=400, body={"status": "fail", "message": "feedback_required",
                                      "error_type": "feedback_required"})
clf.session.request = fb
try:
    clf.private_request("media/1/like/", data={"x": "1"})
    check("feedback raises", False)
except FeedbackRequired:
    check("feedback raises", True)
check("feedback NOT retried (1 send)", sends["n"] == 1)
check("governor cooled down", clf.governor._cooldown_until > 0)

print("\n=== 7) guard: Retry-After aware backoff ===")
class _R:
    def __init__(self, h): self.headers = CaseInsensitiveDict(h)
class _E(Exception):
    def __init__(self, h): self.response = _R(h)
check("reads Retry-After seconds", guard.retry_after_seconds(_R({"Retry-After": "12"})) == 12.0)
w = guard.retry_wait(_E({"Retry-After": "9"}), 0)
check("retry_wait honors Retry-After", 9.0 <= w <= 10.0)
w2 = guard.retry_wait(_E({}), 2)
check("retry_wait exp fallback grows", w2 >= 4.0)

print("\n=== 8) guard: verify_egress (resync / raise / warn) ===")
def geo_client(country_code, calling="+1"):
    cl = client()
    cl.country = "TH"; cl.country_code = 66
    cl.session.request = lambda *a, **k: FakeResp(body={
        "country_code": country_code, "country_calling_code": calling,
        "utc_offset": "-0500", "ip": "5.6.7.8"})
    return cl
rep = geo_client("TH", "+66")
rep.session.request = lambda *a, **k: FakeResp(body={"country_code": "TH", "country_calling_code": "+66", "utc_offset": "+0700", "ip": "1.1.1.1"})
r = guard.verify_egress(rep, policy="warn")
check("matching egress -> ok", r["ok"] is True)
mm = geo_client("US")
r = guard.verify_egress(mm, policy="resync")
check("mismatch resync applied", r["ok"] is False and mm.country == "US")
mm2 = geo_client("US")
try:
    guard.verify_egress(mm2, policy="raise"); check("mismatch raise", False)
except EgressMismatch:
    check("mismatch raise", True)

print("\n=== 9) fingerprint: probe parse + grade ===")
PEET = {"tls": {"ja3": "771,4865-4866", "ja3_hash": "abc123", "ja4": "t13d1516h2",
                "tls_version_negotiated": "772", "peetprint_hash": "pp"},
        "http_version": "h2", "http2": {"akamai_fingerprint": "1:65536;..."},
        "user_agent": "Instagram 314 Android", "ip": "9.9.9.9"}
cl = client()
cl.session.request = lambda *a, **k: FakeResp(body=PEET)
fp = fingerprint.probe(cl.session)
check("probe ja3_hash", fp["ja3_hash"] == "abc123")
check("probe akamai", fp["akamai"].startswith("1:"))
s = fingerprint.summary(cl)
check("tls_client + h2 -> phone grade", s["grade"] == "phone")
cl.session.engine = "requests"
s2 = fingerprint.summary(cl)
check("requests engine -> weak grade", s2["grade"] == "weak")
check("render produces JA3 line", "JA3:" in fingerprint.render(s))

print("\n=== 10) store: encryption round-trip + proxy + add/open ===")
d = tempfile.mkdtemp()
st = SessionStore(d, password="hunter2")
src = client(device_seed="acctZ")
src.user_id = "777"; src.username = "zoe"; src.ig_u_rur = "RURZ"
st.add("zoe", src, proxy="socks5://user:pw@host:9050")
raw = open(os.path.join(d, "zoe.json"), encoding="utf-8").read()
check("file is encrypted", "okgram_enc" in raw and "RURZ" not in raw and "user:pw" not in raw)
b = st.load_bundle("zoe")
check("decrypts username", b["authorization_data"]["username"] == "zoe")
check("decrypts proxy", b["proxy"] == "socks5://user:pw@host:9050")
check("info masks proxy", "***" in st.info("zoe")["proxy"])
opened = st.open("zoe")
check("open restores user_id", opened.user_id == "777")
check("open restores rur", opened.ig_u_rur == "RURZ")
check("open restores proxy", getattr(opened, "proxy", None) == "socks5://user:pw@host:9050")
check("list shows account", "zoe" in st.list())
# plain (no password) store
stp = SessionStore(tempfile.mkdtemp())
stp.save_bundle("a", {"authorization_data": {"username": "x"}, "mode": "mobile"})
check("plain store readable", stp.load_bundle("a")["authorization_data"]["username"] == "x")
check("remove works", stp.remove("a") and not stp.exists("a"))

print("\n=== 11) settings round-trip carries proxy + governor ===")
cg = client(govern=True)
cg.set_proxy("http://h:8080")
cg.governor.gate("media/1/like/")
s = cg.get_settings()
check("settings has proxy", s["proxy"] == "http://h:8080")
check("settings has governor", s["governor"] is not None and s["governor"]["events"].get("like"))
cg2 = client(govern=True)
cg2.set_settings(s)
check("proxy restored", getattr(cg2, "proxy", None) == "http://h:8080")
check("governor state restored", cg2.governor.counts("like")[1] == 1)

print("\n=== 12) review fixes ===")
# 12a comment_unlike is now classified + gated (was bypassing limits)
gu = RateGovernor(think_time=None)
check("comment_unlike classified", gu.classify("media/9/comment_unlike/") == "comment_unlike")
check("comment_like still classified", gu.classify("media/9/comment_like/") == "comment_like")
check("plain comment still classified", gu.classify("media/9/comment/") == "comment")

# 12b governor persistence into a client WITHOUT govern=True (was lost)
src = client(govern=True)
src.governor.gate("media/1/like/")
snap = src.get_settings()
dst = client()  # no govern
dst.set_settings(snap)
check("governor auto-restored without govern=True", dst.governor is not None)
check("governor count restored", dst.governor.counts("like")[1] == 1)

# 12c store wrong-password info() does not crash (returns error dict)
import tempfile as _tf
d2 = _tf.mkdtemp()
SessionStore(d2, password="right").save_bundle("x", {"authorization_data": {"username": "x"}, "uuids": {"profile": {}}})
wrong = SessionStore(d2, password="WRONG")
info = wrong.info("x")
check("wrong-password info() returns error, no crash", "error" in info)

# 12d store.add rejects malformed dict bundle
try:
    SessionStore(_tf.mkdtemp()).add("bad", {"foo": "bar"})
    check("add rejects malformed dict", False)
except ValueError:
    check("add rejects malformed dict", True)

# 12e fingerprint.probe survives malformed (non-dict) tls/http2
cl = client()
cl.session.request = lambda *a, **k: FakeResp(body={"tls": "oops", "http2": 123, "http_version": "h2"})
check("probe survives non-dict tls/http2", fingerprint.probe(cl.session) is not None)

# 12f fingerprint grade 'unknown' for unknown engine
cl2 = client()
cl2.session.engine = "?"
cl2.session.request = lambda *a, **k: FakeResp(body={"tls": {"ja3_hash": "h"}, "http_version": "h2"})
check("unknown engine -> unknown grade", fingerprint.summary(cl2)["grade"] == "unknown")

# 12g egress guard auto-enforced once on first write (policy=raise)
cg = client(guard="raise")
cg.country = "TH"
cg.session.request = lambda *a, **k: FakeResp(body={"country_code": "US", "country_calling_code": "+1", "utc_offset": "-0500", "ip": "1.2.3.4"})
try:
    cg.private_request("media/1/like/", data={"x": "1"})
    check("first write triggers egress guard -> raise", False)
except EgressMismatch:
    check("first write triggers egress guard -> raise", True)

print("\n" + "=" * 52)
npass = sum(1 for _, s in results if s)
print(f"Total: {npass}/{len(results)} PASS")
print("ALL PASS" if npass == len(results) else "SOME FAILED: " + ", ".join(n for n, s in results if not s))
sys.exit(0 if npass == len(results) else 1)
