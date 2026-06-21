# -*- coding: utf-8 -*-
"""In-depth test that the package is assembled correctly and that the core functions actually work (offline)"""
import sys
import io
import inspect

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from okgram import InstagramAPI, config, utils, exceptions
from okgram.mixins import (
    UserMixin, FriendshipMixin, MediaMixin, CommentMixin, FeedMixin,
    UploadMixin, StoryMixin, ClipsMixin, DirectMixin, HashtagMixin,
    LocationMixin, SearchMixin, AccountMixin, CollectionMixin, InsightsMixin,
    LiveMixin, NotificationMixin, PrivateRequestMixin, AuthMixin,
)

print("=== 1) instantiate ===")
cl = InstagramAPI(delay_range=None, device_seed="testuser")
print("OK:", repr(cl))
print("device ua:", cl.device.user_agent()[:60], "...")

print("\n=== 2) Count all public methods on InstagramAPI ===")
public = [n for n in dir(cl) if not n.startswith("_") and callable(getattr(cl, n))]
print("number of public methods/properties:", len(public))

print("\n=== 3) Check for method clashes (duplicate names across mixins) ===")
ALL_MIXINS = [
    UserMixin, FriendshipMixin, MediaMixin, CommentMixin, FeedMixin,
    UploadMixin, StoryMixin, ClipsMixin, DirectMixin, HashtagMixin,
    LocationMixin, SearchMixin, AccountMixin, CollectionMixin, InsightsMixin,
    LiveMixin, NotificationMixin, PrivateRequestMixin, AuthMixin,
]
owner = {}
clashes = {}
for mx in ALL_MIXINS:
    for name, val in vars(mx).items():
        if name.startswith("_") or not callable(val):
            continue
        if name in owner:
            clashes.setdefault(name, [owner[name]]).append(mx.__name__)
        else:
            owner[name] = mx.__name__
if clashes:
    print("found duplicate method names (the first one in the MRO is used):")
    for name, owners in sorted(clashes.items()):
        print(f"  - {name}: {owners}")
else:
    print("no method clashes")

print("\n=== 4) Check that all the important methods are present ===")
required = [
    "login", "two_factor_login", "logout", "login_by_sessionid",
    "dump_settings", "load_settings", "get_settings", "set_settings",
    "encrypt_password", "private_request", "public_request",
    "get_current_user", "user_info_v1", "user_info_by_username_v1",
    "username_to_user_id", "search_users",
    "follow", "unfollow", "user_followers", "user_following",
    "block", "unblock", "friendship_show",
    "media_info", "media_like", "media_unlike", "media_save", "media_delete",
    "media_comment", "media_comments", "comment_like",
    "get_timeline_feed", "user_medias", "liked_medias", "saved_medias",
    "photo_upload", "video_upload", "album_upload",
    "reels_tray", "user_stories", "story_seen", "user_highlights",
    "user_clips", "clip_upload",
    "direct_threads", "direct_thread", "direct_send_text", "direct_send_photo",
    "hashtag_info", "hashtag_medias_top", "hashtag_follow",
    "location_info", "location_search",
    "fbsearch_topsearch", "explore_feed",
    "edit_profile", "set_biography", "account_set_private", "change_password",
    "collections", "collection_create",
    "insights_account", "insights_media",
    "live_create", "live_start", "live_comment",
    "news_inbox", "notification_badge",
]
missing = [m for m in required if not hasattr(cl, m)]
if missing:
    print("missing methods:", missing)
else:
    print(f"all {len(required)} important methods present")

print("\n=== 5) Test utils ===")
pk = 3252452305878029866
code = utils.media_pk_to_code(pk)
back = utils.media_code_to_pk(code)
print(f"pk->code->pk: {pk} -> {code} -> {back}  {'OK' if back == pk else 'FAIL'}")
sb = utils.generate_signed_body({"a": 1, "b": "x"})
print("signed_body:", sb["signed_body"][:40], "...", "OK" if sb["signed_body"].startswith("SIGNATURE.") else "FAIL")
print("jazoest:", utils.generate_jazoest("abc123"))

print("\n=== 6) Test base_headers ===")
h = cl.base_headers
print("X-IG-App-ID:", h.get("X-IG-App-ID"))
print("number of headers:", len(h))
print("has User-Agent:", "User-Agent" in h)

print("\n=== 7) Test encrypt_password (fallback, no pubkey) ===")
enc = cl.encrypt_password("mypassword")
print("enc format:", enc[:25], "...", "OK" if enc.startswith("#PWD_INSTAGRAM:") else "FAIL")

print("\n=== 8) Test encrypt_password (with a real RSA pubkey) ===")
try:
    from Crypto.PublicKey import RSA
    import base64
    key = RSA.generate(2048)
    pub_pem = key.publickey().export_key()
    cl.password_encryption_pub_key = base64.b64encode(pub_pem).decode()
    cl.password_encryption_key_id = 99
    enc2 = cl.encrypt_password("mypassword")
    ok = enc2.startswith("#PWD_INSTAGRAM:4:")
    print("enc:4 format:", enc2[:30], "...", "OK" if ok else "FAIL")
except Exception as e:
    print("ERROR:", e)

print("\n=== 9) Test set/dump/load settings (round-trip) ===")
import tempfile, os
s = cl.get_settings()
print("settings keys:", sorted(s.keys()))
tmp = os.path.join(tempfile.gettempdir(), "_ig_test_settings.json")
cl.dump_settings(tmp)
cl2 = InstagramAPI(delay_range=None)
cl2.load_settings(tmp)
print("device uuid equal after load:", cl.device.uuid == cl2.device.uuid)
os.remove(tmp)

print("\n=== 10) MRO sanity: which mixin does get_current_user belong to ===")
print("get_current_user ->", InstagramAPI.get_current_user.__qualname__)
print("user_followers ->", InstagramAPI.user_followers.__qualname__)

print("\nALL SMOKE TESTS DONE")
