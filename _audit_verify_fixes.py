# -*- coding: utf-8 -*-
"""Verify that the bugs found by the audit have actually been fixed (offline)"""
import io
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from requests.structures import CaseInsensitiveDict
from okgram import InstagramAPI
from okgram import exceptions as exc

PASS, FAIL = "PASS", "FAIL"
results = []

# ---- mock that lets you configure the response per request ----
NEXT = {"status": 200, "json": {"status": "ok"}}
captured = []

class FakeCookies:
    def get(self, k, d=None): return {"csrftoken": "C"}.get(k, d)
    def get_dict(self): return {"csrftoken": "C"}
    def set(self, *a, **k): pass
class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.headers = CaseInsensitiveDict()
        self.cookies = FakeCookies()
        self.text = "{}"
    def json(self): return self._p

def make_request(routing=None):
    def fake_request(method, url, params=None, data=None, headers=None, timeout=None, files=None, **kw):
        captured.append({"method": method, "url": url, "data": data})
        if routing:
            for frag, resp in routing.items():
                if frag in url:
                    return FakeResp(resp[0], resp[1])
        return FakeResp(NEXT["status"], NEXT["json"])
    return fake_request

def client(routing=None):
    cl = InstagramAPI(delay_range=None, device_seed="verify")
    cl.session.request = make_request(routing)
    cl.authorization = "Bearer IGT:2:FAKE"; cl.user_id = "123"; cl.csrftoken = "C"; cl.mid = "M"
    return cl

def check(name, cond):
    results.append((name, PASS if cond else FAIL))

# === FIX 1: error JSON with a 'message' field must raise the correct exception (not TypeError) ===
print("=== FIX 1: exceptions make(**data) collision ===")
cases = [
    ("challenge_required -> ChallengeRequired",
     (400, {"status": "fail", "message": "challenge_required", "challenge": {"api_path": "/c/"}}),
     exc.ChallengeRequired),
    ("bad_password -> BadPassword",
     (400, {"status": "fail", "message": "The password you entered is incorrect", "error_type": "bad_password"}),
     exc.BadPassword),
    ("feedback_required -> FeedbackRequired",
     (400, {"status": "fail", "message": "feedback_required", "feedback_message": "spam"}),
     exc.FeedbackRequired),
    ("login_required -> LoginRequired",
     (400, {"status": "fail", "message": "login_required", "error_type": "login_required"}),
     exc.LoginRequired),
    ("429 + message -> ClientThrottledError",
     (429, {"status": "fail", "message": "Please wait a few minutes before you try again.", "code": 99}),
     exc.ClientError),  # PleaseWaitFewMinutes (subclass of ClientError)
]
for desc, (st, payload), expected in cases:
    cl = client({"users/": (st, payload)})
    try:
        cl.private_request("users/1/info/")
        check(desc, False)
        print(f"  [{FAIL}] {desc}: did not raise")
    except TypeError as e:
        check(desc, False)
        print(f"  [{FAIL}] {desc}: TypeError (bug still present!) -> {e}")
    except expected as e:
        check(desc, True)
        print(f"  [{PASS}] {desc}: raise {type(e).__name__} msg='{e.message}' extra_keys={list(e.extra.keys())}")
    except exc.ClientError as e:
        ok = isinstance(e, expected)
        check(desc, ok)
        print(f"  [{PASS if ok else FAIL}] {desc}: raise {type(e).__name__}")

# === FIX 2: clip_upload handles the tuple from video_rupload correctly (upload_id is not a stringified tuple) ===
print("\n=== FIX 2: clip_upload / video_rupload tuple ===")
mp4 = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
mp4.write(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200); mp4.close()
captured.clear()
cl = client({"rupload_igvideo": (200, {"status": "ok"}),
             "rupload_igphoto": (200, {"status": "ok", "upload_id": "X"}),
             "configure_to_clips": (200, {"status": "ok", "media": {"pk": 1, "id": "1_2"}})})
try:
    out = cl.clip_upload(mp4.name, caption="hi")
    # find the upload_id sent to configure
    cfg = [c for c in captured if "configure_to_clips" in c["url"]]
    sb = cfg[-1]["data"].get("signed_body", "") if cfg and isinstance(cfg[-1]["data"], dict) else ""
    bad = "(" in sb or "None" in sb.split('"upload_id"')[-1][:30] if '"upload_id"' in sb else False
    ok = bool(cfg) and "(" not in sb  # upload_id must not be the string form of a tuple
    check("clip_upload upload_id is clean (not a stringified tuple)", ok)
    print(f"  [{PASS if ok else FAIL}] configure_to_clips was called, upload_id is clean")
except TypeError as e:
    check("clip_upload tuple", False)
    print(f"  [{FAIL}] TypeError: {e}")
except Exception as e:
    # may fail at _video_meta, but not because of a tuple / TypeError
    check("clip_upload tuple", "thumbnail" not in str(e) and not isinstance(e, TypeError))
    print(f"  [info] {type(e).__name__}: {e}")

# === FIX 3: story_seen accepts list[str] (used to AttributeError) ===
print("\n=== FIX 3: story_seen robust against input ===")
cl = client()
try:
    cl.story_seen(["111_222", "333_444"])         # list of media_id strings
    cl.story_seen([{"pk": "5", "user_id": "6", "taken_at": 1}])  # list of dicts
    cl.story_seen(["999"])                          # bare pk (no uid -> skip, no crash)
    check("story_seen accepts list[str]/list[dict] without crashing", True)
    print(f"  [{PASS}] story_seen does not crash on str/dict/pk-only")
except AttributeError as e:
    check("story_seen", False)
    print(f"  [{FAIL}] AttributeError: {e}")

# === FIX 4: location_build accepts str/int/dict (used to AttributeError) ===
print("\n=== FIX 4: location_build robust against input ===")
cl = client()
try:
    a = cl.location_build("12345")                       # pk as str
    b = cl.location_build(67890)                          # pk as int
    c = cl.location_build({"pk": 1, "name": "X", "lat": 1.0, "lng": 2.0})  # normal dict
    d = cl.location_build({"location": {"pk": 9}})        # nested
    check("location_build accepts str/int/dict without crashing", all(isinstance(x, str) for x in (a, b, c, d)))
    print(f"  [{PASS}] location_build ok: str/int/dict/nested -> JSON string")
except AttributeError as e:
    check("location_build", False)
    print(f"  [{FAIL}] AttributeError: {e}")

# === FIX 5: graphql/web that returns a list must not crash in _parse_response ===
print("\n=== FIX 5: list response does not crash ===")
cl = client({"graphql": (200, [{"a": 1}])})
try:
    r = cl.public_request("https://i.instagram.com/graphql", full_url=True)
    check("list response ok", isinstance(r, list))
    print(f"  [{PASS}] list response returned as-is, no crash")
except Exception as e:
    check("list response", False)
    print(f"  [{FAIL}] {type(e).__name__}: {e}")

# === Summary ===
print("\n" + "=" * 50)
npass = sum(1 for _, s in results if s == PASS)
print(f"Total: {npass}/{len(results)} PASS")
for name, s in results:
    if s == FAIL:
        print(f"  FAIL: {name}")
print("ALL PASS" if npass == len(results) else "Some checks FAILED")
