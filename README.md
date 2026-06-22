# okgram — Instagram Private API client (Python)

A Python client for the **Instagram Private API** (`i.instagram.com/api/v1`),
reverse-engineered from **Instagram Lite 516.0.0.8.103** + Instagram Android profiles.
It is bundled into a **single class**, `InstagramAPI`, that covers **every endpoint category** (19 categories / 348+ methods).

It is **phone-grade**: it keeps the whole identity (device + `IG-U-RUR` routing +
`X-MID` + `X-IG-WWW-Claim` + geo + app-id + OkHttp TLS) internally consistent and
stable, **auto-syncs your region to your real IP in any country**, replays the
app's cold-start, and ships an `okgram` CLI with a `doctor` that tells you exactly
why a session is bouncing. See **[Phone-grade sessions](#phone-grade-sessions--why-your-sessionid-stops-bouncing)**.

> ⚠️ **Disclaimer** Using the private API violates Instagram's Terms of Service and may cause your account
> to be challenged / restricted / suspended. Use it only on your own account, responsibly, and at your own risk.
> This code is intended for education / automation of your own account / security research.

---

## Installation

Install directly from GitHub with **pip** — it pulls every dependency automatically:

```bash
pip install git+https://github.com/NiceDayZc/okgram.git
```

Pin a branch / tag:

```bash
pip install "git+https://github.com/NiceDayZc/okgram.git@main"
```

Upgrade later:

```bash
pip install --upgrade --force-reinstall "git+https://github.com/NiceDayZc/okgram.git"
```

Editable / development install (clone, then hack on it):

```bash
git clone https://github.com/NiceDayZc/okgram.git
cd okgram
pip install -e .
```

Optional extras:

```bash
# + Pillow (read image sizes on upload)
pip install "okgram[media] @ git+https://github.com/NiceDayZc/okgram.git"
# + socks5 proxy support for the requests engine
pip install "okgram[socks] @ git+https://github.com/NiceDayZc/okgram.git"
```

**Dependencies (installed for you):**

| Package | Why |
|---|---|
| `requests` | fallback HTTP engine + cookie jar |
| `pycryptodome` | password encryption at login (`#PWD_INSTAGRAM:4` = RSA + AES-GCM) |
| `tls-client` | **recommended** engine — impersonates OkHttp on Android (HTTP/2 + OkHttp JA3/JA4) |
| `curl_cffi` | alternative engine (curl-impersonate: browser TLS + HTTP/2) |

Verify the install:

```bash
python -c "import okgram; print('okgram', okgram.__version__)"
```

Then in your code:

```python
from okgram import OkGram          # aliases: InstagramAPI, Client (same class)
cl = OkGram()
```

> No pip? You can also just drop the `okgram/` folder next to your script and
> `pip install requests pycryptodome tls-client curl_cffi` manually.

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

## Phone-grade sessions — why your `sessionid` stops bouncing

Instagram does **not** identify a session by `sessionid` alone. It correlates
`sessionid` + the **device** + `X-MID` + **`IG-U-RUR`** (region routing) +
`X-IG-WWW-Claim` + the **egress IP / geo** + the **app-id**. If any of those
contradict each other, IG treats it as a takeover → `login_required` / challenge
(the dreaded "เด้ง"). okgram now keeps the whole identity **internally consistent
and stable**, which is what actually keeps a session alive:

- **Routing headers captured + echoed.** `IG-U-RUR`, `IG-U-SHBID`, `IG-U-SHBTS`,
  `IG-U-IG-DIRECT-REGION-HINT` are read from every response and replayed on every
  request (and persisted in the session bundle). Missing `IG-U-RUR` is a top cause
  of bounces — it is now handled end-to-end.
- **Geo auto-sync, every country.** The client detects your **real egress IP**
  region (through your proxy, if any) and aligns `country` / calling-code /
  `timezone` / `X-IG-EU-DC-ENABLED` so the fingerprint can never contradict the
  network. No more "US locale + Bangkok timezone" mismatches.
- **Live app-config.** `bloks_version_id` / password public key / routing are
  pulled live from IG's own `launcher/sync` + `qe/sync` instead of going stale.
- **Cold-start behavior.** On bring-up it replays the app's real sequence
  (timeline → stories → inbox → me) with a believable `X-IG-Nav-Chain`, so the
  session doesn't "pop into existence and immediately act" like a bot.
- **Stable TLS.** OkHttp JA3/JA4 with a **fixed** extension order (randomising it
  per request was itself a bot signal).
- **Mobile vs web mode.** A `sessionid` exported from a **browser** is a *web*
  session bound to the web app-id. `mode="web"` talks to `www.instagram.com` with
  the browser app-id / UA / Chrome TLS — *origin-consistent* with that session, so
  it bounces far less than forcing a web session to impersonate a phone.

### One-call bring-up (recommended)

```python
from okgram import InstagramAPI

cl = InstagramAPI(device_seed="<account-id>")   # auto_geo=True by default
cl.bootstrap("<sessionid or cookie string>")    # geo→config→install→warmup
cl.dump_settings("session.json")                # save the full identity bundle

print(cl.get_current_user()["username"])
```

`bootstrap()` runs, in order: align region to your IP → pull live config →
install the session → replay the cold-start. Reload it later with the exact same
identity:

```python
cl = InstagramAPI()
cl.load_settings("session.json")     # restores device + rur + mid + claim + geo + mode
```

### The `okgram` CLI

Installing the package also installs an `okgram` command (also `python -m okgram`):

```bash
# install a browser sessionid as a phone-grade session and save it
okgram import "25025320%3A...%3A..." --session acct.json
okgram import @cookies.txt --session acct.json          # cookie file / EditThisCookie JSON
echo "$SID" | okgram import - --session acct.json        # from stdin

# diagnose WHY a session is at risk (region/routing/device/TLS contradictions)
okgram doctor --session acct.json --online               # --online also checks egress IP

okgram whoami  --session acct.json
okgram warmup  --session acct.json                       # replay cold-start, re-save
okgram feed    --session acct.json
okgram user    instagram --session acct.json
okgram geo     --save --session acct.json                # detect + pin region
okgram session show --session acct.json                  # masked summary
okgram repl    --session acct.json                       # interactive shell, `cl` bound
```

If a browser `sessionid` still bounces in mobile mode, switch to the
origin-consistent web mode:

```bash
okgram import "<sessionid>" --mode web --session acct.json
```

`okgram doctor` is the fastest way to find the exact problem — it prints each
check (region, calling-code, timezone, EU-DC, `X-MID`, `IG-U-RUR`, `www-claim`,
device, transport, and with `--online` the egress-IP region + live TLS/HTTP-2
fingerprint) as `OK / WARN / FAIL` with the fix.

---

## Hardcore layer (rate governor · egress guard · fingerprint proof · vault)

Four opt-in subsystems for serious, multi-account use:

**1. Rate governor — stops `feedback_required` / action blocks.** Cadence is the
other thing IG watches. The governor enforces human-like per-action caps
(per-hour + per-day for likes / follows / DMs …), a randomised think-time, an
optional sleep window, and an automatic cool-down that backs off when IG returns
`feedback_required`. Reads are never gated; counts persist in the session bundle.

```python
cl = InstagramAPI(device_seed="acct", govern=True)   # or cl.enable_governor(mode="raise")
cl.media_like(media_id)          # gated: paced + counted; raises/sleeps at the cap
```

**2. Egress guard — blocks the instant-challenge IP switch.** Before acting,
verify the egress IP's region still matches the session; on drift it re-syncs
(or raises) instead of letting IG see a sudden country change.

```python
cl.guard_egress(policy="resync")     # 'resync' | 'raise' | 'warn'
```

The request layer also does **smart retry**: it honours IG's `Retry-After` header
instead of a blind fixed sleep, and never retries an action block.

**3. Fingerprint proof — measure what actually leaves the socket.**

```bash
okgram fingerprint --session acct.json
# -> JA3 hash, JA4, HTTP/2 Akamai fingerprint, negotiated TLS, the UA IG saw,
#    and a verdict: PHONE-GRADE (OkHttp/h2) / BROWSER-GRADE / WEAK (Python/h1)
```

```python
print(cl.fingerprint()["verdict"])
```

**4. Multi-account vault — one device + one proxy + one identity per account,
encrypted at rest.**

```bash
okgram accounts add alice "<sessionid>" --proxy http://u:p@host:port --bootstrap \
        --store ./vault --password "secret"
okgram accounts list  --store ./vault --password "secret"
okgram accounts use   alice --store ./vault --password "secret" --online
```

```python
from okgram import SessionStore
vault = SessionStore("./vault", password="secret")     # AES-GCM (PBKDF2) at rest
vault.add("alice", "<sessionid>", proxy="http://u:p@host:port", bootstrap=True)
cl = vault.open("alice")                                # device + routing + proxy restored
```

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
├── __init__.py          # exports InstagramAPI, Device, GeoProfile, geo/doctor/behaviors/live_config
├── __main__.py          # `python -m okgram` -> CLI
├── cli.py               # the `okgram` command (import/doctor/geo/whoami/warmup/feed/user/session/repl)
├── client.py            # main InstagramAPI class (combines all mixins) + bootstrap/sync_geo/sync_config
├── config.py            # constants + geo tables (calling codes, EU-DC, providers) + mode/live-sync config
├── geo.py               # egress-IP geo auto-detection -> consistent region profile (every country)
├── live_config.py       # pull bloks/public-key/routing live from launcher+qe sync
├── behaviors.py         # cold-start sequence + X-IG-Nav-Chain builder + human pacing
├── doctor.py            # session-identity consistency diagnostics (the bounce finder)
├── limits.py            # rate governor: per-action caps + think-time + sleep window + cooldown
├── guard.py             # egress-IP consistency check + Retry-After-aware smart retry
├── fingerprint.py       # live JA3/JA4/HTTP-2 fingerprint probe + grade
├── store.py             # multi-account vault: proxy-per-account + AES-GCM encryption
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

1. **Use `bootstrap()` (or `okgram import`)** instead of a bare `login_by_sessionid` — it aligns geo, pulls live config, and warms up so the very first requests are consistent
2. **Run `okgram doctor --online`** whenever it bounces — it points at the exact contradiction (region/routing/device/IP) instead of guessing
3. **Use the same `device_seed` per account** and always `dump_settings`/`load_settings` — the saved bundle now carries `IG-U-RUR`/mid/claim/geo, so reloading reproduces the exact identity IG last saw
4. **Let geo auto-sync** (`auto_geo=True`, default) align `country`/`timezone`/EU-DC to your real IP — or set them by hand to match. Don't mix (e.g. `country="US"` on a Thai IP)
5. **Enable `delay_range`**, don't fire requests back-to-back
6. **Match the egress IP to the account's region.** A clean **residential** IP in the account's country (even your home connection) is ideal; route a server through a same-country proxy: `InstagramAPI(proxy="http://user:pass@host:port")` — geo auto-sync detects through the proxy
7. **A browser `sessionid` is a web session** — if mobile mode bounces, use `mode="web"` (origin-consistent)
8. **New accounts / accounts that just changed IP** are often challenged — this is normal
9. **The app version may get rejected** over time → update `APP_VERSION`/`VERSION_CODE` in `config.py`
   (or `cl.set_user_agent(app_version=..., version_code=...)`) to a matching, newer pair

> Note on "actually works": the request structure / signing / headers / payload / endpoints are all
> correct, matching what the real app sends (verified by capturing requests offline). What's left is
> a real account + password and Instagram not blocking your IP/behavior, which no client can guarantee.

---

## Origin

- The target/host/app-id were extracted from a decompile of **Instagram Lite 516.0.0.8.103** (`X-IG-App-ID: 567067343352427`, host `i.instagram.com` / `iglite-z.instagram.com`, `SIGNATURE`-style signing)
- The endpoint set is the Instagram Private API `v1`, the same one used by the Instagram Android/Lite app
