# -*- coding: utf-8 -*-
"""
19 — Session management, proxy, locale, retries & error handling.

Covers the client-level knobs and the exception hierarchy you should catch in
production code.
"""
from _common import get_client, login, section, show

from okgram import InstagramAPI
from okgram.exceptions import (
    ClientError,
    LoginRequired,
    ChallengeRequired,
    TwoFactorRequired,
    FeedbackRequired,
    PleaseWaitFewMinutes,
    ClientThrottledError,
    MediaNotFound,
    UserNotFound,
    PrivateAccount,
)


def demo_construction_options() -> None:
    section("Client construction options")
    cl = InstagramAPI(
        device_seed="my_account",      # stable device per account (important)
        locale="th_TH",
        country="TH",
        country_code=66,
        timezone_offset=25200,          # +07:00
        delay_range=(1.0, 3.0),         # random delay between requests; None disables
        engine="auto",                  # tls_client > curl_cffi > requests
        request_timeout=30,
        max_retries=3,
    )
    show("repr", repr(cl))
    show("is_authenticated", cl.is_authenticated)


def demo_runtime_setters() -> None:
    section("Runtime setters")
    cl = get_client()
    cl.set_proxy("http://user:pass@host:port")          # http or socks5
    cl.set_locale("en_US", country="US", country_code=1)  # change locale/country
    cl.set_user_agent(app_version="314.0.0.20.114", version_code="542473058")  # bump when IG rejects
    show("proxy applied", cl.session.proxies)


def demo_persistence() -> None:
    section("Save / restore a session")
    cl = get_client()
    data = cl.get_settings()                 # everything as a dict
    cl.dump_settings("session.json")         # ...or straight to a file
    cl.set_settings(data)                    # restore from dict
    cl.load_settings("session.json")         # restore from file
    show("settings keys", sorted(data.keys()))


def demo_error_handling() -> None:
    section("Error handling pattern")
    cl = login(get_client())
    try:
        cl.media_info("0_0")                 # will fail -> mapped exception
    except MediaNotFound:
        print("  media not found")
    except UserNotFound:
        print("  user not found")
    except PrivateAccount:
        print("  account is private")
    except (FeedbackRequired, PleaseWaitFewMinutes):
        print("  action blocked / throttled — back off")
    except ClientThrottledError:
        print("  rate limited (429) — slow down")
    except LoginRequired:
        cl.relogin()                         # session expired
    except (TwoFactorRequired, ChallengeRequired):
        print("  re-auth required")
    except ClientError as exc:
        print(f"  other client error: {exc}")
    # the raw last response is always available for debugging:
    show("last_json (truncated)", cl.last_json)


def main() -> None:
    demo_construction_options()
    demo_runtime_setters()
    demo_persistence()
    # demo_error_handling()   # needs a real login; uncomment to run
    print("\nSession-management examples done.")


if __name__ == "__main__":
    main()
