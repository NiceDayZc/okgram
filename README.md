# okgram — Instagram Private API client (Python)

A Python client for the **Instagram Private API** (`i.instagram.com/api/v1`),
reverse-engineered from **Instagram Lite 516.0.0.8.103** + Instagram Android profiles.
It is bundled into a **single class**, `InstagramAPI`, that covers **every endpoint category** (19 categories / 348+ methods).

> ⚠️ **Disclaimer** Using the private API violates Instagram's Terms of Service and may cause your account
> to be challenged / restricted / suspended. Use it only on your own account, responsibly, and at your own risk.
> This code is intended for education / automation of your own account / security research.

---

## Installation

```bash
pip install -r okgram/requirements.txt
# or, minimal:
pip install requests pycryptodome tls-client curl_cffi
```

- `requests` — fallback HTTP engine
- `pycryptodome` — encrypts the password at login time (`#PWD_INSTAGRAM:4` = RSA + AES-GCM, just like the real app)
- `tls-client` — **recommended** HTTP engine: impersonates OkHttp on Android (HTTP/2 + real OkHttp JA3/JA4)
- `curl_cffi` — alternative engine (curl-impersonate: browser TLS + HTTP/2)
- (optional) `requests[socks]` for a socks5 proxy with the `requests` engine

Place the `okgram/` folder next to your script, then `from okgram import InstagramAPI`

---

## HTTP engine — looking like a real phone

Plain `requests` is trivially detectable: it uses Python's OpenSSL (a JA3/JA4 TLS fingerprint
no phone produces) and speaks HTTP/1.1, while the Instagram app speaks **HTTP/2 over OkHttp/BoringSSL**.
This client abstracts the HTTP layer and auto-selects the most app-like engine available:

| `engine=` | TLS / HTTP | Fingerprint | Notes |
|---|---|---|---|
| `"auto"` (default) | picks the best installed | — | tls_client → curl_cffi → requests |
| `"tls_client"` | **HTTP/2, OkHttp Android** | `t13d1513**h2**_…` (OkHttp) | **best match for the Instagram Android UA** |
| `"curl_cffi"` | HTTP/2, browser | `t13d1516h2_…` (Chrome) | real non-Python TLS, browser profile |
| `"requests"` | HTTP/1.1, Python | `t13d1812**h1**_…` (flagged) | fallback only |

```python
cl = InstagramAPI(device_seed="acct")                 # auto -> tls_client okhttp4_android_13
cl = InstagramAPI(engine="tls_client")                 # force OkHttp-Android impersonation
cl = InstagramAPI(engine="tls_client", impersonate="okhttp4_android_12")
cl = InstagramAPI(engine="curl_cffi", impersonate="chrome")
```

With `tls_client` the OkHttp profile is **auto-mapped from the simulated device's Android version**
(e.g. Android 13 → `okhttp4_android_13`), so the TLS fingerprint, HTTP/2 settings, header order, and
the `User-Agent` all agree — exactly like the real app. (Verified end-to-end: requests go out as `h2`
with an OkHttp JA3/JA4, not Python's.)

---

## Quick start

```python
from okgram import InstagramAPI
from okgram.exceptions import TwoFactorRequired, ChallengeRequired, BadPassword

cl = InstagramAPI(
    device_seed="myusername",     # bind a stable device per account (important! don't randomize it every time)
    locale="th_TH", country="TH", country_code=66, timezone_offset=25200,
    delay_range=(1.0, 3.0),       # random delay to avoid rate-limiting (None = disabled)
)

try:
    cl.login("myusername", "mypassword")
except TwoFactorRequired:
    code = input("Enter the 6-digit 2FA code: ")
    cl.two_factor_login(code)
except ChallengeRequired:
    cl.challenge_resolve(choice=1)              # 1=Email, 0=SMS
    cl.challenge_submit_code(input("Enter the code you received: "))
except BadPassword:
    print("Wrong password")

# Save the session for next time (so you don't have to log in often = fewer flags)
cl.dump_settings("session.json")
```

Next time:

```python
cl = InstagramAPI(device_seed="myusername")
cl.load_settings("session.json")      # restore the same device + token + cookies
cl.login("myusername", "mypassword")  # reuse the existing token if it hasn't expired
```

Or log in with an existing `sessionid`:

```python
cl.login_by_sessionid("xxxxxxxxxxxxxx%3Ayyyyyyy%3A...")
```

---

## Real-world usage examples

```python
# --- Profile / users ---
me   = cl.get_current_user()
user = cl.user_info_by_username_v1("instagram")
uid  = cl.username_to_user_id("instagram")
cl.set_biography("Hello from the API 🐍")
cl.account_set_private()

# --- Following / followers ---
cl.follow(uid)
cl.unfollow(uid)
followers = cl.user_followers(uid, amount=200)   # paginates automatically
following = cl.user_following(uid, amount=0)      # 0 = all
cl.mute_stories(uid)
cl.block(uid); cl.unblock(uid)

# --- Media / posts ---
m = cl.media_info("3123456789_17841400000000000")
cl.media_like(m["pk"]); cl.media_unlike(m["pk"])
cl.media_save(m["pk"])
cl.media_comment(m["pk"], "So cool!")
comments = cl.media_comments(m["pk"])
cl.media_edit(m["pk"], "Edited caption")
cl.media_delete(m["pk"])

# --- Feeds ---
timeline = cl.get_timeline_feed()
posts    = cl.user_medias(uid, amount=50)
liked    = cl.liked_medias(amount=20)
saved    = cl.saved_medias(amount=20)

# --- Uploads ---
cl.photo_upload("pic.jpg", caption="Posted from the API")
cl.video_upload("clip.mp4", caption="video", thumbnail="thumb.jpg")
cl.album_upload(["a.jpg", "b.jpg", "c.jpg"], caption="album")
cl.photo_upload_to_story("story.jpg")
cl.clip_upload("reel.mp4", caption="New reel")

# --- Stories / highlights ---
tray   = cl.reels_tray()
story  = cl.user_stories(uid)
viewers = cl.story_viewers(story_pk, amount=0)
cl.highlight_create("Japan trip", media_ids=[...])

# --- Direct (messages) ---
inbox  = cl.direct_threads(amount=20)
cl.direct_send_text("Hello there", user_ids=[uid])
cl.direct_send_photo("pic.jpg", user_ids=[uid])
cl.direct_send_media_share(m["pk"], user_ids=[uid])
recips = cl.direct_search("john")

# --- Search / explore ---
res    = cl.fbsearch_topsearch("cat memes")
users  = cl.search_users("cat")
tags   = cl.search_hashtags("cat")
explore = cl.explore_medias(amount=30)

# --- Hashtags / places ---
cl.hashtag_info("cats")
top    = cl.hashtag_medias_top("cats", amount=27)
cl.hashtag_follow("cats")
places = cl.fbsearch_places("Bangkok")
loc    = cl.location_info(location_pk)

# --- Reels / clips ---
reels  = cl.user_clips(uid, amount=20)
disc   = cl.clips_discover()

# --- Notifications / insights (business/creator accounts) ---
news   = cl.news_inbox()
badge  = cl.notification_badge()
acc_in = cl.insights_account()
md_in  = cl.insights_media(m["pk"])
```

You can always hit endpoints yourself at a low level:

```python
cl.private_request("users/123/info/")                 # GET
cl.private_request("friendships/create/123/", data={...})  # POST (signed_body automatically)
cl.public_request("users/web_profile_info/", params={"username": "instagram"})
```

---

## Full method catalog

| Mixin | Count | Example methods |
|---|---|---|
| **AuthMixin** | 15 | `login`, `two_factor_login`, `challenge_resolve`, `challenge_submit_code`, `login_by_sessionid`, `relogin`, `logout`, `get_settings`/`set_settings`, `dump_settings`/`load_settings`, `encrypt_password`, `pre_login_flow` |
| **AccountMixin** | 26 | `get_current_user`, `edit_profile`, `set_biography`, `set_username`, `set_email`, `set_phone_number`, `set_gender`, `change_password`, `change_profile_picture`, `account_set_private`/`account_set_public`, `enable_totp_two_factor`, `set_account_type`, `account_security_info` |
| **UserMixin** | 31 | `user_info`, `user_info_by_username_v1`, `web_profile_info`, `username_to_user_id`, `user_id_to_username`, `user_followers`, `user_following`, `search_users`, `user_similar_accounts`, `user_mutual_followers`, `usertag_medias` |
| **FriendshipMixin** | 29 | `follow`, `unfollow`, `friendship_show`/`show_many`, `user_followers_page`, `user_following_page`, `pending_requests`, `approve_pending`/`reject_pending`, `remove_follower`, `block`/`unblock`, `mute_posts`/`mute_stories`, `restrict`/`unrestrict` |
| **MediaMixin** | 26 | `media_info`, `media_info_by_code`/`by_url`, `media_like`/`unlike`, `media_save`/`unsave`, `media_delete`, `media_edit`, `media_likers`, `media_archive`/`unarchive`, `media_seen`, `media_pk_from_code`/`from_url`, `media_oembed` |
| **CommentMixin** | 17 | `media_comment`, `media_comments`, `reply_to_comment`, `comment_delete`/`bulk_delete`, `comment_like`/`unlike`, `comment_pin`/`unpin`, `comment_likers`, `comment_replies`, `enable_comments`/`disable_comments` |
| **FeedMixin** | 16 | `get_timeline_feed`, `user_medias`, `user_feed_page`, `liked_medias`, `saved_medias`, `collection_medias`, `reels_tray`, `popular_feed`, `my_medias` |
| **UploadMixin** | 8 | `photo_upload`, `video_upload`, `album_upload`, `photo_rupload`, `video_rupload`, `photo_configure`, `video_configure`, `change_profile_picture` |
| **StoryMixin** | 23 | `user_stories`, `reels_tray`, `story_viewers`, `story_seen`, `story_like`/`unlike`, `story_vote_poll`, `story_vote_slider`, `story_answer_quiz`, `highlight_create`/`edit`/`delete`, `highlight_info`, `user_highlights` |
| **ClipsMixin** | 21 | `user_clips`, `clips_discover`, `clips_by_music`, `clip_upload`, `clip_info`, `clip_like`/`unlike`, `clip_comment`, `music_search`, `igtv_upload`, `igtv_channel` |
| **DirectMixin** | 35 | `direct_threads`, `direct_thread`, `direct_send_text`/`link`/`photo`/`media_share`/`profile`/`hashtag`/`like`, `direct_mark_seen`, `direct_search`, `direct_thread_mute`/`hide`/`approve`/`leave`/`add_users`, `direct_presence` |
| **HashtagMixin** | 12 | `hashtag_info`, `hashtag_medias_top`/`recent`, `hashtag_follow`/`unfollow`, `hashtags_followed`, `hashtag_related`, `hashtag_story` |
| **LocationMixin** | 11 | `location_search`, `location_info`, `location_medias_top`/`recent`, `fbsearch_places`, `location_related`, `location_story` |
| **SearchMixin** | 17 | `fbsearch_topsearch`, `search_users`, `search_hashtags`, `search_places`, `explore_medias`, `explore_feed`, `suggested_users`, `discover_chaining`, `recent_searches`, `register_recent_search_click` |
| **CollectionMixin** | 13 | `collections`, `collection_create`, `collection_add_media`, `collection_remove_media`, `collection_edit_name`, `collection_delete`, `collection_medias`, `saved_medias` |
| **InsightsMixin** | 16 | `insights_account`, `insights_media`, `insights_story`, `insights_media_feed_all`, `media_engagement`/`impressions`/`reach`/`saves`, `account_reach`/`impressions` *(requires a professional account)* |
| **LiveMixin** | 23 | `live_create`, `live_start`, `live_end`, `live_info`, `live_comment`/`comments`, `live_like`, `live_viewers`/`viewer_count`, `live_heartbeat`, `live_pin_comment`, `live_enable_comments`/`disable_comments` |
| **NotificationMixin** | 17 | `news_inbox`, `news_following`, `notification_badge`, `activity_count`, `direct_unread_count`, `mark_news_seen`, `push_register`/`unregister`, `notification_settings` |

See the full list of methods:

```python
import inspect
from okgram import InstagramAPI
cl = InstagramAPI()
print([m for m in dir(cl) if not m.startswith("_") and callable(getattr(cl, m))])
```

---

## Project structure

```
okgram/
├── __init__.py          # exports InstagramAPI, Device, exceptions
├── client.py            # main InstagramAPI class (combines all mixins)
├── config.py            # constants: app version, app id, capabilities, host, UA template
├── device.py            # simulates an Android device + builds the User-Agent (deterministic per seed)
├── exceptions.py        # exception hierarchy + maps IG errors
├── utils.py             # sign body, uuid, media pk<->code, helpers
├── requirements.txt
└── mixins/
    ├── private.py       # ⭐ core: private_request / public_request / graphql_request + headers + retry
    ├── auth.py          # login / 2FA / challenge / session
    ├── account.py  user.py  friendship.py  media.py  comment.py  feed.py
    ├── upload.py  story.py  clips.py  direct.py  hashtag.py  location.py
    └── search.py  collection.py  insights.py  live.py  notification.py
```

**Architecture:** every category is a separate *mixin* file, and `InstagramAPI` inherits all of them together.
Every mixin calls the backend through `self.private_request(...)` in `mixins/private.py`, which handles:
- adding the full set of `X-IG-*` / `X-Bloks-*` / `Authorization` headers
- wrapping the body as `signed_body=SIGNATURE.<json>` automatically (the modern unsigned format)
- updating token/claim/mid from the response headers
- converting error JSON → exception + retry + random delay

---

## Error handling

```python
from okgram.exceptions import (
    LoginRequired, ChallengeRequired, TwoFactorRequired, BadPassword,
    FeedbackRequired, PleaseWaitFewMinutes, ClientThrottledError,
    MediaNotFound, UserNotFound, PrivateAccount, ClientError,
)
```

- `LoginRequired` → session expired, call `cl.relogin()`
- `ChallengeRequired` → `cl.challenge_resolve()` then `cl.challenge_submit_code(code)`
- `FeedbackRequired` / `PleaseWaitFewMinutes` → you hit an action block, take a break first
- `ClientThrottledError` (429) → requests too frequent, wait and slow down

---

## Tips to "make it actually work" and reduce the chance of getting banned

1. **Use the same `device_seed` per account** and always `dump_settings`/`load_settings` — don't create a new device every time
2. **Enable `delay_range`** (random delay between requests), don't fire requests back-to-back
3. **Set `locale`/`country`/`timezone_offset` to match the real account**
4. **Use a proxy located in the same country as the account** if running from a server: `InstagramAPI(proxy="http://user:pass@host:port")`
5. **New accounts / accounts that just changed IP** are often challenged — this is normal
6. **The app version may get rejected** over time → update `APP_VERSION`/`VERSION_CODE` in `config.py`
   (or `cl.set_user_agent(app_version=..., version_code=...)`) to a matching, newer pair

> Note on "actually works": the request structure / signing / headers / payload / endpoints are all
> correct, matching what the real app sends (verified by capturing requests offline). What's left is
> a real account + password and Instagram not blocking your IP/behavior, which no client can guarantee.

---

## Origin

- The target/host/app-id were extracted from a decompile of **Instagram Lite 516.0.0.8.103** (`X-IG-App-ID: 567067343352427`, host `i.instagram.com` / `iglite-z.instagram.com`, `SIGNATURE`-style signing)
- The endpoint set is the Instagram Private API `v1`, the same one used by the Instagram Android/Lite app
