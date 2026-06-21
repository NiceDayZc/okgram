# -*- coding: utf-8 -*-
"""
Example of using okgram through the full flow (login -> use -> save session)

Run:
    pip install -r okgram/requirements.txt
    python example.py

Set USERNAME / PASSWORD below first (or use the IG_USER / IG_PASS environment variables)
"""
import getpass
import os

from okgram import InstagramAPI
from okgram.exceptions import (
    BadPassword,
    ChallengeRequired,
    ClientError,
    LoginRequired,
    TwoFactorRequired,
)

USERNAME = os.environ.get("IG_USER") or "your_username"
PASSWORD = os.environ.get("IG_PASS") or "your_password"
SESSION_FILE = f"session_{USERNAME}.json"


def get_client() -> InstagramAPI:
    """Create a client and load the existing session if present"""
    cl = InstagramAPI(
        device_seed=USERNAME,          # bind a stable device per account
        locale="th_TH",
        country="TH",
        country_code=66,
        timezone_offset=25200,         # +07:00
        delay_range=(1.0, 3.0),        # random delay to avoid rate-limiting
    )
    if os.path.exists(SESSION_FILE):
        print(f"[i] Loading session from {SESSION_FILE}")
        cl.load_settings(SESSION_FILE)
    return cl


def do_login(cl: InstagramAPI) -> bool:
    """login with handling for 2FA / challenge"""
    try:
        cl.login(USERNAME, PASSWORD)
        print(f"[+] login successful: {cl.username} (id={cl.user_id})")
        return True

    except TwoFactorRequired:
        code = input("Enter the 6-digit 2FA code: ").strip()
        cl.two_factor_login(code)
        print("[+] 2FA passed")
        return True

    except ChallengeRequired:
        print("[!] Challenge required")
        # 1 = receive the code by Email, 0 = by SMS
        cl.challenge_resolve(choice=1)
        code = input("Enter the verification code you received: ").strip()
        cl.challenge_submit_code(code)
        print("[+] challenge passed")
        return True

    except BadPassword:
        print("[x] Incorrect password")
        return False


def main() -> None:
    cl = get_client()

    if not do_login(cl):
        return

    # Save the session for next time (very important, reduces repeated logins)
    cl.dump_settings(SESSION_FILE)
    print(f"[i] Saved session to {SESSION_FILE}")

    try:
        # ----- Your own account info -----
        me = cl.get_current_user()
        print("\n=== My account ===")
        u = me.get("user", me)
        print(f"  {u.get('username')} | followers={u.get('follower_count')} "
              f"| following={u.get('following_count')} | posts={u.get('media_count')}")

        # ----- View another user's info -----
        target = "instagram"
        info = cl.user_info_by_username_v1(target)
        tu = info.get("user", info)
        print(f"\n=== @{target} ===")
        print(f"  id={tu.get('pk')} | followers={tu.get('follower_count')} "
              f"| bio={ (tu.get('biography') or '')[:50] }")

        # ----- Home feed -----
        timeline = cl.get_timeline_feed()
        print(f"\n=== timeline: {len(timeline.get('feed_items', []))} items ===")

        # ----- Activity / notifications -----
        badge = cl.notification_badge()
        print(f"\n=== badge ===\n  {badge.get('badge_count', badge)}")

        # --- Example actions (commented out to avoid running them by accident) ---
        # uid = cl.username_to_user_id(target)
        # cl.follow(uid)
        # cl.media_like("3123456789_17841400000000000")
        # cl.media_comment("3123456789_17841400000000000", "Awesome!")
        # cl.direct_send_text("Hello", user_ids=[uid])
        # cl.photo_upload("pic.jpg", caption="Posted from the API 🐍")

    except LoginRequired:
        print("[!] session expired, trying relogin")
        cl.relogin()
    except ClientError as e:
        print(f"[x] error: {e}")


if __name__ == "__main__":
    main()
