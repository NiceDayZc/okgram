# Examples

Runnable, copy-paste examples for **every** `InstagramAPI` method, one file per category.

## Setup

```bash
pip install -r ../okgram/requirements.txt   # requests pycryptodome tls-client curl_cffi ...
```

Configure via environment variables (never hard-code secrets):

| Var | Default | Meaning |
|---|---|---|
| `IG_USER` / `IG_PASS` | — | your credentials |
| `IG_SESSION` | `session_<user>.json` | session file (reused across examples) |
| `IG_COOKIE` | — | log in with a cookie string instead of a password |
| `IG_TARGET` | `instagram` | a public account the read-only examples inspect |
| `IG_ENGINE` | `auto` | HTTP engine: `auto` / `tls_client` / `curl_cffi` / `requests` |
| `IG_RUN_WRITES` | `0` | set to `1` to allow WRITE/destructive actions |

> By default the examples are **read-only** — they never modify your account.
> WRITE actions (follow, like, comment, upload, send, delete, settings…) only run
> when `IG_RUN_WRITES=1`.

## Run

```bash
# one-time: log in and save a session
IG_USER=me IG_PASS=secret python examples/00_login.py     # (edit main() to pick a login method)

# then run any category (reuses the saved session)
python examples/02_user.py
python examples/04_media.py
IG_RUN_WRITES=1 python examples/03_friendship.py          # enable writes
```

(On Windows PowerShell: `$env:IG_USER="me"; python examples\02_user.py`)

## Files

| File | Category | Notes |
|---|---|---|
| `_common.py` | shared helpers | client builder, `login()`, resolvers, safety switch |
| `00_login.py` | **Auth & session** | password / 2FA / challenge / sessionid / **cookie** / cookie-file / settings |
| `01_account.py` | Account (own) | profile, privacy, security, 2FA |
| `02_user.py` | Users / profiles | info, id↔username, search, counts |
| `03_friendship.py` | Follow graph | follow, followers/following, block, mute, restrict |
| `04_media.py` | Posts | info, like, save, archive, edit, delete, likers |
| `05_comment.py` | Comments | comment, reply, like, pin, delete |
| `06_feed.py` | Feeds | timeline, user/liked/saved/collection feeds |
| `07_upload.py` | Upload | photo / video / album / story / reel (rupload + configure) |
| `08_story.py` | Stories + highlights | view, viewers, seen, vote, highlights |
| `09_clips.py` | Reels + IGTV | user clips, discover, by-music, upload |
| `10_direct.py` | Direct (DM) | inbox, threads, send text/photo/media, thread admin |
| `11_hashtag.py` | Hashtags | info, top/recent, follow, story |
| `12_location.py` | Locations | search, info, feed, build-tag |
| `13_search.py` | Search & explore | topsearch, users/tags/places, explore |
| `14_collection.py` | Saved collections | list, create, add/remove media |
| `15_insights.py` | Insights | account/media insights (professional accounts only) |
| `16_live.py` | Live | create, start, comment, viewers, end |
| `17_notification.py` | Notifications | activity, badges, push, settings |
| `18_engine_fingerprint.py` | HTTP engine | pick/inspect engine; live TLS/HTTP2 fingerprint check |
| `19_session_management.py` | Session/proxy/errors | construct, proxy, persist, exception handling |
| `20_phone_grade.py` | Anti-bounce | geo auto-sync, IG-U-RUR routing, mobile/web modes, `bootstrap()`, `doctor` |
| `21_hardcore.py` | Hardcore layer | rate governor, egress guard, fingerprint proof, multi-account encrypted vault |

> ⚠️ Using the private API violates Instagram's ToS and may get your account
> challenged/restricted. Use your own account, at your own risk.
