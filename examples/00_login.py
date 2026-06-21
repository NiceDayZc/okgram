# -*- coding: utf-8 -*-
"""
00 — Authentication & session: every way to log in.

Covers AuthMixin end to end:
  password login (+ 2FA / challenge) · login_by_sessionid · login_by_cookie
  (string / JSON / netscape / dict / bare id) · login_by_cookie_file · parse_cookies
  · relogin · logout · get_settings / set_settings / dump_settings / load_settings
  · pre_login_flow · encrypt_password

Safe to run: only the offline demos and a single session-based login actually
execute. The interactive / destructive variants are shown as functions you call.
"""
import os
import tempfile

from _common import get_client, section, show, USERNAME, PASSWORD, SESSION_FILE


# ---------------------------------------------------------------------------
# 1) Parse cookies from any format (offline, always safe)
# ---------------------------------------------------------------------------
def demo_parse_cookies() -> None:
    from okgram import InstagramAPI
    section("parse_cookies — supported formats")
    samples = {
        "header string": "sessionid=123%3Aabc%3A10; ds_user_id=123; csrftoken=xyz; mid=M",
        "Cookie: prefix": "Cookie: sessionid=123%3Aabc%3A10; csrftoken=xyz",
        "dict": {"sessionid": "123%3Aabc%3A10", "ds_user_id": "123"},
        "json list": '[{"name":"sessionid","value":"123%3Aabc%3A10"},{"name":"ds_user_id","value":"123"}]',
        "json dict": '{"sessionid":"123%3Aabc%3A10","mid":"M"}',
        "netscape": ".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t123%3Aabc%3A10",
        "bare sessionid": "123%3Aabc%3A10",
    }
    for label, raw in samples.items():
        show(label, InstagramAPI.parse_cookies(raw))


# ---------------------------------------------------------------------------
# 2) Login with username / password (handles 2FA and challenge)
# ---------------------------------------------------------------------------
def login_with_password(cl) -> bool:
    from okgram.exceptions import TwoFactorRequired, ChallengeRequired, BadPassword
    section("login(username, password)")
    try:
        cl.login(USERNAME, PASSWORD)            # also: relogin=True to force a fresh login
    except TwoFactorRequired:
        # cl.two_factor_info holds the 2FA context
        cl.two_factor_login(input("2FA code: ").strip())
    except ChallengeRequired:
        cl.challenge_resolve(choice=1)          # 1=email, 0=SMS  (-> challenge_send_code internally)
        cl.challenge_submit_code(input("verification code: ").strip())
    except BadPassword:
        print("  wrong password"); return False
    print(f"  logged in as {cl.username} (id={cl.user_id})")
    return True


# ---------------------------------------------------------------------------
# 3) Login with an existing sessionid
# ---------------------------------------------------------------------------
def login_with_sessionid(cl, sessionid: str) -> bool:
    section("login_by_sessionid(sessionid)")
    return cl.login_by_sessionid(sessionid)     # reconstructs the Bearer token for you


# ---------------------------------------------------------------------------
# 4) Login with cookies you exported from your computer / browser
# ---------------------------------------------------------------------------
def login_with_cookie(cl, cookies) -> bool:
    section("login_by_cookie(cookies)")
    # `cookies` can be: header string / JSON (extension export) / dict / netscape / bare sessionid
    return cl.login_by_cookie(cookies)          # verify=False to skip the network check


def login_with_cookie_file(cl, path: str) -> bool:
    section("login_by_cookie_file(path)")
    return cl.login_by_cookie_file(path)        # reads cookies.txt / JSON file then logs in


# ---------------------------------------------------------------------------
# 5) Session persistence (dump / load) — offline round-trip demo
# ---------------------------------------------------------------------------
def demo_settings_roundtrip() -> None:
    section("get_settings / dump_settings / load_settings (round-trip)")
    cl = get_client()
    settings = cl.get_settings()                # full state as a dict (device, cookies, tokens...)
    show("settings keys", sorted(settings.keys()))

    tmp = os.path.join(tempfile.gettempdir(), "_demo_ig_settings.json")
    cl.dump_settings(tmp)                        # write to disk
    cl2 = get_client()
    cl2.set_settings(settings)                   # restore from a dict
    cl2.load_settings(tmp)                       # or restore from a file
    show("same device after reload", cl.device.uuid == cl2.device.uuid)
    os.remove(tmp)


# ---------------------------------------------------------------------------
# 6) Low-level auth helpers
# ---------------------------------------------------------------------------
def demo_low_level(cl) -> None:
    section("pre_login_flow / encrypt_password")
    # pre_login_flow fetches mid, csrftoken and the password public key (call before login)
    # cl.pre_login_flow()
    enc = cl.encrypt_password("hunter2")         # -> "#PWD_INSTAGRAM:4:..." (or :0: without a pubkey)
    show("encrypted password format", enc[:30] + "...")


def demo_relogin_logout(cl) -> None:
    section("relogin / logout")
    # cl.relogin()   # log in again with the same username/password + same device
    # cl.logout()    # invalidate the session and clear cookies
    print("  (relogin/logout shown as comments — uncomment to run)")


def main() -> None:
    # always-safe offline demos
    demo_parse_cookies()
    demo_settings_roundtrip()

    cl = get_client()
    demo_low_level(cl)

    # Pick ONE real login method (uncomment what you use):
    # login_with_password(cl)
    # login_with_sessionid(cl, os.environ["IG_SESSIONID"])
    # login_with_cookie(cl, os.environ["IG_COOKIE"])
    # login_with_cookie_file(cl, "cookies.txt")

    # If logged in, persist the session for the other examples to reuse:
    if cl.is_authenticated:
        cl.dump_settings(SESSION_FILE)
        print(f"\n[+] session saved to {SESSION_FILE}")
    else:
        print("\n[i] no real login performed — uncomment a method in main()")

    print("\nLogin examples done.")


if __name__ == "__main__":
    main()
