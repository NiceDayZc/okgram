# -*- coding: utf-8 -*-
"""
Shared helpers for every example in this folder.

Run any example from the repo root or from this folder, e.g.:

    python examples/02_user.py
    python examples/04_media.py

Configuration via environment variables (so you never hard-code secrets):

    IG_USER        your username           (default: "your_username")
    IG_PASS        your password           (default: "your_password")
    IG_SESSION     session file path       (default: "session_<user>.json")
    IG_COOKIE      a cookie string         (optional; login via cookie instead of password)
    IG_TARGET      a public account to read (default: "instagram")
    IG_ENGINE      http engine             (default: "auto" -> tls_client/curl_cffi/requests)
    IG_RUN_WRITES  "1" to allow WRITE/destructive actions (follow/like/comment/upload/send/...)
                   Default OFF: examples only READ, never modify your account.

The login flow reuses a saved session when possible, then falls back to cookie
or password login (handling 2FA / challenge interactively).
"""
from __future__ import annotations

import os
import sys

# make the local "okgram" package importable no matter the working dir
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from okgram import InstagramAPI  # noqa: E402
from okgram.exceptions import (  # noqa: E402
    BadPassword,
    ChallengeRequired,
    ClientError,
    LoginRequired,
    TwoFactorRequired,
)

# --- configuration from the environment ------------------------------------
USERNAME = os.environ.get("IG_USER", "your_username")
PASSWORD = os.environ.get("IG_PASS", "your_password")
SESSION_FILE = os.environ.get("IG_SESSION", f"session_{USERNAME}.json")
COOKIE = os.environ.get("IG_COOKIE", "")
TARGET_USERNAME = os.environ.get("IG_TARGET", "instagram")
ENGINE = os.environ.get("IG_ENGINE", "auto")
RUN_WRITES = os.environ.get("IG_RUN_WRITES") == "1"


# --- pretty printing -------------------------------------------------------
def section(title: str) -> None:
    """Print a section header."""
    print("\n" + "=" * 64)
    print(f"# {title}")
    print("=" * 64)


def show(label: str, value, limit: int = 400) -> None:
    """Print a labelled value, truncated so output stays readable."""
    text = repr(value)
    if len(text) > limit:
        text = text[:limit] + f"... ({len(text)} chars)"
    print(f"  {label}: {text}")


def writes_disabled_note() -> None:
    print("  (WRITE actions skipped — set IG_RUN_WRITES=1 to enable them)")


# --- client / login --------------------------------------------------------
def get_client(**kwargs) -> InstagramAPI:
    """Build a client (engine from IG_ENGINE) and restore a saved session if any."""
    cl = InstagramAPI(
        device_seed=USERNAME,
        locale="en_US",
        country="US",
        country_code=1,
        engine=ENGINE,
        **kwargs,
    )
    if os.path.exists(SESSION_FILE):
        try:
            cl.load_settings(SESSION_FILE)
        except Exception as exc:  # noqa
            print(f"[warn] could not load {SESSION_FILE}: {exc}")
    return cl


def login(cl: InstagramAPI) -> InstagramAPI:
    """
    Authenticate the client.

    Priority: reuse saved session -> IG_COOKIE -> username/password
    (interactive 2FA / challenge). Saves the session on success.
    """
    # 1) reuse an existing session
    if cl.is_authenticated:
        try:
            cl.get_current_user()
            print(f"[+] reused session as {cl.username or USERNAME}")
            return cl
        except LoginRequired:
            print("[i] saved session expired, logging in again")

    # 2) cookie login
    if COOKIE:
        cl.login_by_cookie(COOKIE)
        cl.dump_settings(SESSION_FILE)
        print(f"[+] logged in via cookie as {cl.username}")
        return cl

    # 3) username / password (with 2FA / challenge handling)
    try:
        cl.login(USERNAME, PASSWORD)
    except TwoFactorRequired:
        cl.two_factor_login(input("Enter 2FA code: ").strip())
    except ChallengeRequired:
        cl.challenge_resolve(choice=1)  # 1 = email, 0 = SMS
        cl.challenge_submit_code(input("Enter the code from email/SMS: ").strip())
    except BadPassword:
        print("[x] wrong password — set IG_USER / IG_PASS")
        raise

    cl.dump_settings(SESSION_FILE)
    print(f"[+] logged in as {cl.username} (id={cl.user_id})")
    return cl


# --- convenience resolvers used across examples ----------------------------
def my_user_id(cl: InstagramAPI) -> str:
    """The logged-in account's user id."""
    return str(cl.user_id)


def target_user_id(cl: InstagramAPI) -> str:
    """Resolve IG_TARGET (a username) to a user id."""
    return str(cl.username_to_user_id(TARGET_USERNAME))


def first_media_of(cl: InstagramAPI, user_id: str) -> dict:
    """Return the first media dict of a user's feed (or {} if none)."""
    medias = cl.user_medias(user_id, amount=1)
    return medias[0] if medias else {}
