# -*- coding: utf-8 -*-
"""
18 — HTTP engine & mobile TLS fingerprint.

Shows how to make traffic look like the real Instagram Android app (OkHttp,
HTTP/2, OkHttp JA3/JA4) and how to choose / inspect the transport engine.

Engines (auto-priority): tls_client (OkHttp Android) -> curl_cffi (browser) -> requests.
"""
from _common import section, show

from okgram import InstagramAPI
from okgram import transport


def demo_availability() -> None:
    section("Available engines")
    show("tls_client installed", transport.HAS_TLS_CLIENT)
    show("curl_cffi installed", transport.HAS_CURL_CFFI)
    show("auto resolves to", transport.resolve_engine("auto"))


def demo_profile_mapping() -> None:
    section("OkHttp profile auto-mapped from the device's Android version")
    for release in ("11", "12", "13", "14", None):
        show(f"android_release={release}", transport.okhttp_profile_for(release))


def demo_engine_choice() -> None:
    section("Choosing an engine per client")

    # default: auto -> tls_client, OkHttp profile from the simulated device
    cl = InstagramAPI(device_seed="acct")
    show("auto", (cl.session.engine, cl.session.impersonate))

    # force OkHttp-on-Android impersonation (best match for the Instagram UA)
    cl = InstagramAPI(engine="tls_client", impersonate="okhttp4_android_13")
    show("tls_client/okhttp4_android_13", (cl.session.engine, cl.session.impersonate))

    # curl-impersonate (real browser TLS + HTTP/2)
    cl = InstagramAPI(engine="curl_cffi", impersonate="chrome")
    show("curl_cffi/chrome", (cl.session.engine, cl.session.impersonate))

    # plain requests fallback (weak fingerprint — HTTP/1.1 + Python TLS)
    cl = InstagramAPI(engine="requests")
    show("requests", (cl.session.engine, cl.session.impersonate))


def demo_build_session() -> None:
    section("Building a transport session directly")
    sess = transport.build_session(engine="auto", android_release="13")
    show("session", repr(sess))
    # cookies behave like a requests cookie jar; proxies accept a dict or a string
    sess.proxies = "http://user:pass@host:port"
    show("proxies", sess.proxies)


def demo_live_fingerprint() -> None:
    """Optional: prove the fingerprint by hitting a TLS echo service (needs network)."""
    section("Live fingerprint check (optional, needs internet)")
    cl = InstagramAPI(device_seed="acct")
    try:
        r = cl.session.request("GET", "https://tls.peet.ws/api/all",
                               headers=cl.base_headers, timeout=20)
        j = r.json()
        show("http version", j.get("http_version"))
        show("ja4", (j.get("tls") or {}).get("ja4"))
        show("http2 fingerprint", (j.get("http2") or {}).get("akamai_fingerprint_hash"))
    except Exception as exc:  # noqa - network may be blocked
        print(f"  skipped (no network): {exc}")


def main() -> None:
    demo_availability()
    demo_profile_mapping()
    demo_engine_choice()
    demo_build_session()
    demo_live_fingerprint()
    print("\nEngine / fingerprint examples done.")


if __name__ == "__main__":
    main()
