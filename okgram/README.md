# okgram — Instagram Private API Client (Python)

A Python client covering **every endpoint category** of the Instagram Private API (mobile),
reverse-engineered from **Instagram Lite 516.0.0.8.103** plus an Instagram Android profile.
It talks to the same `i.instagram.com/api/v1/` backend the real app uses.

- One main class: `InstagramAPI` (composed of 19 mixins)
- ~350 public methods spanning 17 functional areas
- Real login: password encryption in the `#PWD_INSTAGRAM:4` format (RSA + AES-GCM), just like the app
- Supports 2FA, challenge, save/load session, proxy, retry, and error handling via exceptions

> ⚠️ **Read the [Important Warnings](#important-warnings) section before using this for real.**

---

## Important Warnings

1. **Against Instagram's ToS** — using the private API violates Instagram's terms of use.
   Accounts may be challenged / restricted / banned. Use at your own risk and only on accounts
   whose risk you accept.
2. **What "actually works" means** — the request structure / signing / headers / endpoints
   are correct, matching what the real app sends, so the requests that go out are valid.
   But **no client can guarantee you won't get blocked** — Instagram has anti-bot systems;
   new accounts / new IPs / high request rates get challenged easily.
3. **The app version will go stale** — Instagram periodically rejects versions that are too old.
   If logins start failing, update `APP_VERSION` / `VERSION_CODE` in [config.py](config.py)
   (or call `cl.set_user_agent(app_version=..., version_code=...)`).
4. **Use a proxy in/near the account's country** and set `locale` / `timezone_offset` / `country`
   to match the real account to reduce the chance of being flagged.
5. **Don't fire requests too fast** — the default already adds a random 1–3s delay per request.
   Don't set `delay_range=None` for high-volume jobs.

---

## Installation

```bash
pip install -r requirements.txt
```

| Library | Required? | Purpose |
|---|---|---|
| `requests` | ✅ Required | fallback HTTP engine + cookie jar/types |
| `pycryptodome` | ✅ Strongly recommended | `:4` password encryption (without it, falls back to plaintext, which IG may reject) |
| `tls-client` | ✅ Recommended | HTTP engine that impersonates **OkHttp on Android** (HTTP/2 + OkHttp JA3/JA4) — auto-selected |
| `curl_cffi` | Optional | alternative engine (curl-impersonate: browser TLS + HTTP/2) |
| `Pillow` | Optional | Reading image dimensions on upload |
| `moviepy` | Optional | Reading video metadata on upload (or pass `width/height/duration_ms` yourself) |

### HTTP engine (mobile-grade TLS fingerprint)

`requests` is easy to fingerprint (Python OpenSSL JA3 + HTTP/1.1). The client abstracts the
transport and auto-picks the most app-like engine: **`tls_client`** (OkHttp on Android — HTTP/2,
real OkHttp JA3/JA4) → `curl_cffi` (browser TLS) → `requests` (fallback). With `tls_client` the
OkHttp profile is auto-mapped from the device's Android version, so TLS + HTTP/2 + header order +
User-Agent all match the real app.

```python
cl = InstagramAPI(engine="auto")                                  # default
cl = InstagramAPI(engine="tls_client", impersonate="okhttp4_android_13")
cl = InstagramAPI(engine="curl_cffi", impersonate="chrome")
```

Drop the `okgram/` folder next to your script, then `from okgram import InstagramAPI`.

---

## Quick Start

```python
from okgram import InstagramAPI
from okgram.exceptions import TwoFactorRequired, ChallengeRequired, BadPassword

# Recommended: bind a stable device to the account (use the username as the seed) -> fewer challenges
cl = InstagramAPI(
    device_seed="my_account",
    locale="th_TH", country="TH", country_code=66, timezone_offset=25200,
    # proxy="http://user:pass@host:port",
)

try:
    cl.login("USERNAME", "PASSWORD")
except TwoFactorRequired:
    code = input("Enter 2FA code: ")
    cl.two_factor_login(code)
except ChallengeRequired:
    cl.challenge_resolve(choice=1)          # 1=email, 0=SMS
    cl.challenge_submit_code(input("Code from email/SMS: "))
except BadPassword:
    print("Wrong password")

# Save the session for next time (no need to log in again)
cl.dump_settings("session.json")
```

Next time:

```python
cl = InstagramAPI(device_seed="my_account")
cl.load_settings("session.json")           # restores the token + device + cookies
# if the token is still valid you can call the API directly; if expired, cl.login(...) again
print(cl.get_current_user()["username"])
```

Or log in with an existing sessionid:

```python
cl.login_by_sessionid("xxxx%3Ayyyy%3Azzzz")
```

### Common usage examples

```python
# Profile
u = cl.user_info_by_username("instagram")
uid = u["pk"]
print(u["follower_count"], u["biography"])

# Follow / unfollow
cl.follow(uid)
cl.unfollow(uid)

# followers / following (auto-paginates every page; amount=0 = all)
followers = cl.user_followers(uid, amount=200)
following = cl.user_following(uid, amount=200)

# Posts
media = cl.media_info("3252452305878029866_25025320")
cl.media_like(media["pk"])
cl.media_comment(media["pk"], "So beautiful! 🔥")

# A user's feed
posts = cl.user_medias(uid, amount=24)

# Upload
cl.photo_upload("pic.jpg", "My caption #test")
cl.video_upload("clip.mp4", "Video", thumbnail="cover.jpg")
cl.album_upload(["1.jpg", "2.jpg", "3.jpg"], "Photo album")

# Story
cl.photo_upload_to_story("story.jpg")
cl.photo_upload_to_story("story.jpg", mentions=[{"user_id": uid, "x": 0.5, "y": 0.4}])
tray = cl.reels_tray()                        # stories of accounts you follow
cl.user_stories(uid)                          # a single user's stories

# Direct message
cl.direct_send_text("Hello!", user_ids=[uid])
threads = cl.direct_threads(amount=10)

# Search
res = cl.fbsearch_topsearch("chiang mai")     # people + hashtags + places
cl.hashtag_medias_top("travel", amount=27)
```

---

## Project Structure

```
okgram/
├── __init__.py            # exports InstagramAPI, exceptions
├── client.py              # main InstagramAPI class (combines all mixins + __init__)
├── config.py              # constants: version, app id, host, capabilities, etc.
├── exceptions.py          # exception hierarchy + IG error mapper
├── utils.py               # sign body, uuid, media id <-> code conversion
├── device.py              # build a simulated device + User-Agent
├── requirements.txt
└── mixins/
    ├── private.py         # ★ request core (headers/sign/retry/parse/error)
    ├── auth.py            # ★ login, password encryption, 2FA, challenge, session
    ├── account.py         # own account / edit profile / settings
    ├── user.py            # user info / profile
    ├── friendship.py      # follow / followers / block / mute
    ├── media.py           # posts: info / like / save / delete / edit
    ├── comment.py         # comments
    ├── feed.py            # timeline / user feed / liked / saved
    ├── upload.py          # upload photo/video/album (rupload + configure)
    ├── story.py           # stories + highlights
    ├── clips.py           # Reels (clips) + IGTV
    ├── direct.py          # direct messages (DM)
    ├── hashtag.py         # hashtags
    ├── location.py        # locations
    ├── search.py          # search + explore
    ├── collection.py      # collections (saved)
    ├── insights.py        # insights (business/creator accounts only)
    ├── live.py            # live
    └── notification.py    # notifications / activity
```

At the core are two methods in `private.py` that every endpoint goes through:

```python
self.private_request(endpoint, data=None, params=None)   # mobile api; data=None=GET, data=dict=POST(signed_body)
self.public_request(path, params=None)                   # web api (www.instagram.com)
```

Both handle headers/signing/retry/JSON parsing and **raise exceptions automatically on IG errors**.

---

## Full Method Index (by category)

> `*_page` / `*_chunk` methods are the raw one-page-at-a-time variants; methods with `amount=0`
> auto-paginate through every page.

### Auth & Session (`auth.py`)
`login` · `two_factor_login` · `login_by_sessionid` · `relogin` · `logout` ·
`challenge_resolve` · `challenge_send_code` · `challenge_submit_code` ·
`encrypt_password` · `pre_login_flow` ·
`get_settings` · `set_settings` · `dump_settings` · `load_settings`

### Account — own account (`account.py`)
`get_current_user` · `account_info` · `get_account_settings` · `edit_profile` ·
`set_name` · `set_username` · `set_biography` · `set_external_url` · `set_gender` ·
`set_phone_number` · `set_email` · `account_set_private` · `account_set_public` ·
`change_password` · `change_profile_picture` · `remove_profile_picture` ·
`account_security_info` · `request_two_factor_enable` · `enable_totp_two_factor` ·
`disable_totp_two_factor` · `send_recovery_flow_email` · `send_password_reset` ·
`set_presence_disabled` · `set_account_type` · `get_account_family` · `get_profile_completion`

### User — users/profiles (`user.py`)
`user_info` · `user_info_by_username` · `web_profile_info` ·
`username_to_user_id` · `user_id_to_username` ·
`search_users` · `search_users_web` ·
`user_following_count` · `user_followers_count` · `user_media_count` · `user_is_private` ·
`reel_settings` · `user_mutual_followers` · `user_similar_accounts` ·
`user_related_profiles` · `user_about` · `usertag_medias` · `user_highlights`

### Friendship — relationships (`friendship.py`)
`follow` · `unfollow` · `user_followers` · `user_following` ·
`user_followers_ids` · `user_following_ids` · `is_following` · `is_followed_by` ·
`pending_requests` · `pending_inbox` · `approve_pending` · `reject_pending` ·
`block` · `unblock` · `blocked_users` · `remove_follower` ·
`mute_posts` · `unmute_posts` · `mute_stories` · `unmute_stories` ·
`mute_posts_and_stories` · `unmute_posts_and_stories` ·
`friendship_show` · `friendship_show_many` ·
`restrict` · `unrestrict` · `restricted_users`

### Media — posts (`media.py`)
`media_info` · `media_info_by_code` · `media_info_by_url` · `media_oembed` ·
`media_pk` · `media_pk_from_url` · `media_code_from_url` · `media_pk_from_code` · `media_code_from_pk` ·
`media_user` · `media_comment_count` · `media_like_count` ·
`media_like` · `media_unlike` · `media_like_toggle` ·
`media_save` · `media_unsave` · `media_archive` · `media_unarchive` ·
`media_edit` · `media_delete` · `media_likers` · `media_comment_likers` ·
`media_seen` · `media_blocked` · `media_permalink`

### Comment — comments (`comment.py`)
`media_comment` · `reply_to_comment` · `media_comments` · `media_comments_page` ·
`comment_replies` · `comment_like` · `comment_unlike` · `comment_likers` ·
`comment_delete` · `comment_bulk_delete` · `comment_pin` · `comment_unpin` ·
`comment_info` · `enable_comments` · `disable_comments`

### Feed — feeds (`feed.py`)
`get_timeline_feed` · `timeline_feed_items` · `user_medias` · `user_feed_page` ·
`user_feed_by_username` · `my_medias` ·
`liked_medias` · `saved_medias` · `collection_medias` ·
`reels_tray` (from story) · `popular_feed`

### Upload — uploading (`upload.py`)
`photo_upload` · `video_upload` · `album_upload` ·
`photo_upload_to_story` · `video_upload_to_story` · `story_configure` ·
`photo_rupload` · `video_rupload` · `photo_configure` · `video_configure` ·
`change_profile_picture`

### Story — stories + highlights (`story.py`)
`reels_tray` · `reels_tray_items` · `user_stories` · `user_stories_reel` · `users_stories` ·
`user_story_by_username` · `story_seen` · `story_seen_one` ·
`story_viewers` · `story_likers` · `story_like` · `story_unlike` ·
`story_vote_poll` · `story_answer_quiz` · `story_vote_slider` ·
`user_highlights` · `user_highlights_by_username` · `highlight_info` · `highlight_items` ·
`highlight_create` · `highlight_delete` · `highlight_edit`

### Clips (Reels) + IGTV (`clips.py`)
`user_clips` · `clips_discover` · `clips_by_music` · `clip_info` · `clip_info_by_pk` ·
`clip_like` · `clip_unlike` · `clip_seen` · `clip_comment` ·
`clip_configure` · `clip_upload` ·
`music_search` · `music_by_id` ·
`igtv_channel` · `igtv_videos` · `igtv_configure` · `igtv_upload`

### Direct — messages (`direct.py`)
`direct_threads` · `direct_inbox_page` · `direct_pending_threads` · `direct_pending_inbox` ·
`direct_pending_count` · `direct_thread` · `direct_messages` · `direct_thread_by_participants` ·
`direct_send_text` · `direct_send_link` · `direct_send_media_share` · `direct_send_media_share_by_pk` ·
`direct_send_photo` · `direct_send_hashtag` · `direct_send_profile` · `direct_send_like` ·
`direct_mark_seen` · `direct_message_delete` ·
`direct_thread_approve` · `direct_thread_decline` · `direct_thread_hide` ·
`direct_thread_mute` · `direct_thread_unmute` · `direct_thread_mark_unread` ·
`direct_thread_add_users` · `direct_thread_remove_users` · `direct_thread_update_title` · `direct_thread_leave` ·
`direct_search` · `direct_ranked_recipients` · `direct_presence` · `direct_send_typing_indicator`

### Hashtag — hashtags (`hashtag.py`)
`hashtag_info` · `hashtag_related` · `hashtag_medias_top` · `hashtag_medias_recent` ·
`hashtag_follow` · `hashtag_unfollow` · `hashtag_story` ·
`hashtags_followed` · `hashtag_following`

### Location — locations (`location.py`)
`location_info` · `location_complaint_info` · `location_story` · `location_related` ·
`location_medias_top` · `location_medias_recent` ·
`location_search` · `location_search_one` · `fbsearch_places` · `location_build`

### Search & Explore (`search.py`)
`fbsearch_topsearch` · `fbsearch_topsearch_flat` ·
`search_users` · `search_users_by_keyword` · `search_hashtags` · `search_locations` · `search_places` ·
`explore_feed` · `explore_medias` · `discover_chaining` ·
`suggested_users` · `suggested_searches` · `recent_searches` · `clear_search_history`

### Collection — collections (`collection.py`)
`collections` · `collection_info` · `collection_id_by_name` ·
`collection_create` · `collection_delete` · `collection_edit_name` ·
`collection_add_media` · `collection_remove_media` · `collection_add_media_by_pk` ·
`collection_medias` · `saved_medias`

### Insights (business/creator accounts only) (`insights.py`)
`insights_account` · `insights_account_summary` · `insights_media` · `insights_media_by_pk` ·
`insights_media_by_url` · `insights_media_feed_all` · `insights_story` · `insights_stories_all` ·
`media_reach` · `media_impressions` · `media_engagement` · `media_saves` ·
`account_reach` · `account_impressions`

### Live — live (`live.py`)
`live_create` · `live_start` · `live_end` · `live_info` · `live_heartbeat` ·
`live_viewer_count` · `live_viewers` · `live_join_requests` ·
`live_comments` · `live_comment` · `live_pin_comment` · `live_unpin_comment` ·
`live_enable_comments` · `live_disable_comments` · `live_like` · `live_like_count` · `live_wave` ·
`live_post_info` · `live_post_comments` · `live_get_final_viewer_list`

### Notification — notifications (`notification.py`)
`news_inbox` · `news_inbox_stories` · `news_inbox_counts` ·
`news_following` · `news_following_stories` ·
`notification_badge` · `direct_badge_count` · `direct_unread_count` · `activity_count` ·
`mark_news_seen` · `mark_story_seen` ·
`push_register` · `push_unregister` · `notification_settings` · `set_user_notification`

---

## Error Handling

Every IG error is converted into an exception (see [exceptions.py](exceptions.py)):

```python
from okgram.exceptions import (
    ClientError,            # base of all errors
    LoginRequired,          # session expired -> relogin
    BadPassword,
    TwoFactorRequired,
    ChallengeRequired, CheckpointRequired,
    FeedbackRequired, PleaseWaitFewMinutes,   # action blocked / throttled
    ClientThrottledError,   # rate limit (429)
    MediaNotFound, UserNotFound, PrivateAccount,
)

try:
    cl.media_like(media_id)
except PleaseWaitFewMinutes:
    print("Throttled — take a break")
except LoginRequired:
    cl.relogin()
```

`cl.last_response` / `cl.last_json` hold the latest raw response for debugging.

---

## Configuration

Adjustable when constructing `InstagramAPI(...)` or via methods:

| Parameter | Default | Meaning |
|---|---|---|
| `device_seed` | random | device seed (use the username to keep the device stable) |
| `engine` | `"auto"` | HTTP engine: `auto` / `tls_client` / `curl_cffi` / `requests` |
| `impersonate` | None | profile override (e.g. `okhttp4_android_12`, `chrome`); auto-mapped from the device's Android version for tls_client |
| `proxy` | None | `"http://user:pass@host:port"` or `"socks5://..."` |
| `locale` / `country` / `country_code` / `timezone_offset` | en_US/US/1/+7 | match the real account |
| `delay_range` | `(1.0, 3.0)` | random delay range (seconds); `None` = no delay |
| `app_version` / `version_code` | see config.py | app version (change when IG rejects it) |
| `request_timeout` | 30 | timeout (seconds) |
| `max_retries` | 3 | retry on network/throttle errors |

Helper methods: `cl.set_proxy(...)` · `cl.set_locale(...)` · `cl.set_user_agent(...)` · `cl.is_authenticated`

---

## Verify the package assembles correctly (offline)

There is a project-level smoke test (does not hit the real network):

```bash
python _smoke_test.py
```

It checks: import/instantiate, method counts, presence of key methods, utils,
password encryption, and the session round-trip.

---

## Technical Notes (what was reverse-engineered from the APK)

| Item | Value |
|---|---|
| App | Instagram Lite 516.0.0.8.103 (APKPure) |
| `X-IG-App-ID` | `567067343352427` (extracted from classes.dex) |
| Host | `i.instagram.com` (Lite: `iglite-z.instagram.com`) — same backend |
| Signing | `signed_body=SIGNATURE.<json>` (modern IG no longer checks HMAC; confirmed by the `SIGNATURE` string in the dex) |
| Password | `#PWD_INSTAGRAM:4:<ts>:<base64>` = RSA(session_key) + AES-GCM(password) |

> Instagram Lite is built primarily on the Bloks/MSYS (server-driven UI) architecture, so the REST
> endpoints live in native code / compressed modules and don't appear directly in the dex — this client
> therefore targets the Instagram Private API v1, the same backend that both the main app and Lite call.
