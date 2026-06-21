# -*- coding: utf-8 -*-
"""
Runtime audit: call every public method through a mock network to catch "real crashes"
(AttributeError / NameError / KeyError / internal TypeError / references to missing config/attr)

The mock always returns an "end-of-list" response -> the paginate helper won't loop forever
API-level exceptions (ClientError and its children) are considered "normal" (not a code bug)
"""
import inspect
import io
import os
import sys
import tempfile
import traceback
import typing

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from requests.structures import CaseInsensitiveDict

from okgram import InstagramAPI
from okgram import exceptions as exc

# ---- mock network that always returns an "end" payload ----
TERMINAL_JSON = {
    "status": "ok",
    "more_available": False,
    "big_list": False,
    "next_max_id": None,
    "users": [], "items": [], "comments": [], "sections": [],
    "feed_items": [], "broadcasts": [], "threads": [], "inbox": {"threads": [], "has_older": False},
    "user": {"pk": 1, "username": "x", "follower_count": 0, "following_count": 0},
    "logged_in_user": {"pk": 1, "username": "x"},
    "upload_id": "1", "media": {"pk": 1, "id": "1_1", "code": "ABC"},
    "thread_id": "1", "media_id": "1_1",
    "highlight_reels": [], "tray": [], "reels": {}, "reels_media": [],
    "ranked_recipients": [], "results": [], "tags": [], "places": [],
    "story_viewers": [], "viewers": [], "collections": [], "items_count": 0,
    "thread": {"thread_id": "1", "items": []},
    "broadcast_id": "1", "media_or_ad": {},
}


class FakeCookies:
    def get(self, k, d=None):
        return {"csrftoken": "C", "sessionid": "1%3Aabc", "ds_user_id": "1"}.get(k, d)
    def get_dict(self):
        return {"csrftoken": "C", "sessionid": "1%3Aabc", "ds_user_id": "1"}
    def set(self, *a, **k):
        pass
    def clear(self):
        pass


class FakeResp:
    status_code = 200
    text = "{}"
    def __init__(self):
        self.headers = CaseInsensitiveDict()
        self.cookies = FakeCookies()
    def json(self):
        return dict(TERMINAL_JSON)


calls = {"n": 0}
def fake_request(method, url, params=None, data=None, headers=None, timeout=None, files=None, **kw):
    calls["n"] += 1
    return FakeResp()


JPG = None
def make_jpg():
    global JPG
    import base64
    if JPG:
        return JPG
    data = base64.b64decode(
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
        "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
        "AAAAAAAAAAAAAAAAAAAACP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AfwD/2Q=="
    )
    f = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    f.write(data); f.close()
    JPG = f.name
    return JPG


def dummy_for(name, param, cl):
    p = name.lower()
    ann = ""
    if param.annotation is not inspect.Parameter.empty:
        ann = str(param.annotation).lower()

    # path / file -> temporary jpg
    if p in ("path", "thumbnail") or p.endswith("_path") or "pathlike" in ann:
        return make_jpg()
    if "settings" in p:
        return cl.get_settings()
    # list
    if "list" in ann or p.endswith("_ids") or p in ("user_ids", "media_ids", "comment_ids", "thread_ids", "paths", "add", "remove"):
        return ["123"]
    if "bool" in ann:
        return False
    if "int" in ann and "optional" not in ann:
        return 1
    if "float" in ann or p in ("lat", "lng", "latitude", "longitude"):
        return 13.7 if "l" in p else 1.0
    if p in ("amount", "count", "limit", "page_size", "thread_count", "choice", "first"):
        return 1
    if p in ("code", "verification_code", "security_code", "two_factor_identifier"):
        return "123456"
    if "password" in p:
        return "Passw0rd!"
    if "email" in p:
        return "a@b.com"
    if "phone" in p:
        return "+10000000000"
    if "url" in p or "link" in p:
        return "https://example.com"
    if "media_id" in p:
        return "111_222"
    if p.endswith("_id") or p in ("pk", "uid", "target_id", "audio_id", "location_pk", "story_pk",
                                   "highlight_id", "collection_id", "comment_id", "thread_id",
                                   "item_id", "broadcast_id", "user_id"):
        return "123"
    if p in ("query", "text", "title", "caption", "name", "username", "biography",
             "word", "tab", "reason", "first_name", "gender", "raw_text", "new_name"):
        return "test"
    # has a default -> use the default
    if param.default is not inspect.Parameter.empty and param.default is not None:
        return param.default
    return "x"


SKIP = {
    "logout",            # clears state
    "set_proxy",         # needs a real proxy
    "graphql_request",   # needs a real query_hash (checked statically instead)
}


def build_client():
    cl = InstagramAPI(delay_range=None, device_seed="audit")
    cl.session.request = fake_request
    cl.session.cookies = FakeCookies()
    cl.authorization = "Bearer IGT:2:FAKE"
    cl.user_id = "123"
    cl.username = "audit"
    cl.password = "Passw0rd!"
    cl.csrftoken = "C"
    cl.mid = "M"
    # set a fake pubkey so encrypt_password can take the RSA path
    try:
        from Crypto.PublicKey import RSA
        import base64
        key = RSA.generate(1024)
        cl.password_encryption_pub_key = base64.b64encode(key.publickey().export_key()).decode()
        cl.password_encryption_key_id = 7
    except Exception:
        pass
    # set context in case of challenge/2fa
    cl.two_factor_info = {"two_factor_identifier": "X", "verification_method": "1"}
    cl.challenge_context = {"api_path": "/challenge/1/abc/"}
    cl.last_login = {}
    return cl


def main():
    cl = build_client()
    methods = sorted(
        n for n in dir(cl)
        if not n.startswith("_") and callable(getattr(cl, n))
    )
    crashes = []
    api_errs = 0
    ok = 0
    skipped = []
    called = 0

    CRASH_TYPES = (AttributeError, NameError, TypeError, KeyError, IndexError,
                   UnboundLocalError, ValueError, ImportError, RuntimeError)

    for name in methods:
        if name in SKIP:
            skipped.append(name)
            continue
        fn = getattr(cl, name)
        try:
            sig = inspect.signature(fn)
        except (TypeError, ValueError):
            skipped.append(name)
            continue
        kwargs = {}
        ok_to_call = True
        for pname, param in sig.parameters.items():
            if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if param.default is inspect.Parameter.empty:
                try:
                    kwargs[pname] = dummy_for(pname, param, cl)
                except Exception:
                    ok_to_call = False
        if not ok_to_call:
            skipped.append(name)
            continue
        # partially reset the client (logout/login may change state)
        called += 1
        try:
            fn(**kwargs)
            ok += 1
        except exc.ClientError:
            api_errs += 1
        except CRASH_TYPES as e:
            tb = traceback.extract_tb(sys.exc_info()[2])
            # find the last frame that belongs to our package
            loc = ""
            for fr in reversed(tb):
                if "okgram" in fr.filename:
                    loc = f"{os.path.basename(fr.filename)}:{fr.lineno} ({fr.name})"
                    break
            crashes.append((name, type(e).__name__, str(e)[:160], loc))
        except Exception as e:
            tb = traceback.extract_tb(sys.exc_info()[2])
            loc = ""
            for fr in reversed(tb):
                if "okgram" in fr.filename:
                    loc = f"{os.path.basename(fr.filename)}:{fr.lineno} ({fr.name})"
                    break
            crashes.append((name, type(e).__name__, str(e)[:160], loc))

    print(f"total methods: {len(methods)} | called: {called} | ok: {ok} | api-exc(normal): {api_errs} | skip: {len(skipped)}")
    print(f"network calls captured: {calls['n']}")
    print(f"\n=== CRASHES that are real bugs: {len(crashes)} ===")
    for name, etype, msg, loc in crashes:
        print(f"  [{etype}] {name}()  @ {loc}\n      {msg}")
    print("\n=== SKIPPED ===")
    print("  " + ", ".join(skipped))


if __name__ == "__main__":
    main()
