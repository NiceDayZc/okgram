"""
okgram command-line interface -- a phone-grade Instagram session tool.

    okgram import "<sessionid|cookie-string|@cookies.txt|->" [--session s.json]
    okgram doctor   --session s.json [--online]
    okgram geo      [--proxy ...] [--session s.json --save]
    okgram whoami   --session s.json
    okgram warmup   --session s.json
    okgram feed     --session s.json
    okgram user <username> --session s.json
    okgram session show --session s.json
    okgram repl     --session s.json

The ``import`` command is the main entry point: it aligns the region to your
egress IP, pulls the live server config, installs the session, replays the app's
cold-start sequence, and saves a complete identity bundle you can reuse -- which
is exactly what keeps the session from getting bounced.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from . import __version__, config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _eprint(*a) -> None:
    print(*a, file=sys.stderr)


def _read_source(source: str) -> str:
    """Resolve a cookie source: '-' = stdin, '@path' = file, else literal."""
    if source == "-":
        return sys.stdin.read()
    if source.startswith("@"):
        return Path(source[1:]).read_text(encoding="utf-8", errors="ignore")
    return source


def _seed_from_source(raw: str) -> Optional[str]:
    """Best-effort ds_user_id from a sessionid so the device stays stable per account."""
    m = re.search(r"(\d{4,})%3A", raw) or re.search(r"sessionid[\"'=:\s]+(\d{4,})", raw)
    if m:
        return m.group(1)
    m = re.match(r"\s*(\d{4,}):", raw)
    return m.group(1) if m else None


def _build_client(args, *, for_import: bool = False):
    from .client import InstagramAPI

    device_seed = getattr(args, "device_seed", None)
    if for_import and not device_seed:
        try:
            device_seed = _seed_from_source(_read_source(args.source))
        except Exception:  # noqa: BLE001
            device_seed = None

    kwargs = dict(
        mode=getattr(args, "mode", config.MODE_MOBILE),
        device_seed=device_seed,
        auto_geo=not getattr(args, "no_geo", False),
        govern=getattr(args, "govern", False),
        guard=getattr(args, "guard", None) or False,
    )
    if getattr(args, "country", None):
        kwargs["country"] = args.country.upper()
        kwargs["country_code"] = config.COUNTRY_CALLING_CODES.get(
            args.country.upper(), config.DEFAULT_COUNTRY_CODE
        )
    if getattr(args, "locale", None):
        kwargs["locale"] = args.locale
    cl = InstagramAPI(**kwargs)
    if getattr(args, "proxy", None):
        cl.set_proxy(args.proxy)
    return cl


def _load_into(cl, args):
    path = getattr(args, "session", None)
    if path and os.path.exists(path):
        cl.load_settings(path)
        return True
    return False


def _require_session(args):
    cl = _build_client(args)
    if not _load_into(cl, args):
        _eprint(f"error: session file not found: {args.session!r} "
                f"(create one with: okgram import ...)")
        sys.exit(2)
    return cl


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def cmd_import(args) -> int:
    raw = _read_source(args.source)
    cl = _build_client(args, for_import=True)

    print(f"[*] mode={cl.mode} device_seed={'auto' if not args.device_seed else args.device_seed}")
    if cl.auto_geo:
        prof = cl.sync_geo()
        if prof is not None:
            print(f"[+] geo: {prof.country} +{prof.country_code} tz={prof.timezone_offset}s "
                  f"(ip {prof.ip} via {prof.source})")
        else:
            print(f"[i] geo: keep {cl.country} +{cl.country_code} (no detection)")

    ok = cl.bootstrap(
        raw,
        verify=not args.no_verify,
        warmup=not args.no_warmup,
        sync_geo=False,           # already done above
        sync_config=not args.no_config,
    )
    if not ok:
        _eprint("[x] could not verify the session (it may be invalid/expired)")
        # still save so the user can inspect / doctor it
    who = cl.username or "?"
    print(f"[{'+' if ok else '!'}] session {'ready' if ok else 'installed (unverified)'}: "
          f"@{who} id={cl.user_id}")

    out = args.session or "session.json"
    cl.dump_settings(out)
    print(f"[i] saved identity bundle -> {out}")

    from . import doctor
    rep = doctor.diagnose(cl, online=False)
    print()
    print(doctor.render(rep))
    return 0 if ok else 1


def cmd_doctor(args) -> int:
    cl = _build_client(args)
    loaded = _load_into(cl, args)
    if not loaded and args.session:
        _eprint(f"[i] no session file at {args.session}; diagnosing a fresh client")
    from . import doctor
    rep = doctor.diagnose(cl, online=args.online)
    print(doctor.render(rep))
    return 1 if rep["fails"] else 0


def cmd_geo(args) -> int:
    from . import geo as geo_mod
    cl = _build_client(args)
    _load_into(cl, args)
    prof = geo_mod.detect(cl.session)
    if prof is None:
        _eprint("[x] could not detect geo (no provider answered)")
        return 1
    print(json.dumps(prof.to_dict(), indent=2))
    if getattr(args, "save", False) and args.session:
        from . import live_config
        live_config.apply_geo(cl, prof)
        cl.dump_settings(args.session)
        print(f"[i] applied + saved geo -> {args.session}")
    return 0


def cmd_whoami(args) -> int:
    cl = _require_session(args)
    user = cl.get_current_user()
    u = user.get("user", user)
    print(json.dumps({
        "username": u.get("username") or cl.username,
        "pk": u.get("pk") or cl.user_id,
        "full_name": u.get("full_name"),
        "followers": u.get("follower_count"),
        "following": u.get("following_count"),
        "media": u.get("media_count"),
        "is_private": u.get("is_private"),
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_warmup(args) -> int:
    from . import behaviors
    cl = _require_session(args)
    rep = behaviors.cold_start(cl)
    cl.dump_settings(args.session)
    print(f"[+] warmup ran={rep['ran']} failed={rep['failed']}; session saved")
    return 0


def cmd_feed(args) -> int:
    cl = _require_session(args)
    tl = cl.get_timeline_feed(reason="pull_to_refresh")
    items = tl.get("feed_items", [])
    print(f"timeline: {len(items)} items, more_available={tl.get('more_available')}")
    for it in items[: args.limit]:
        media = it.get("media_or_ad") or it.get("media") or {}
        user = (media.get("user") or {}).get("username", "?")
        code = media.get("code", "")
        print(f"  @{user}  https://instagram.com/p/{code}/")
    return 0


def cmd_user(args) -> int:
    cl = _require_session(args)
    if hasattr(cl, "user_info_by_username_v1"):
        info = cl.user_info_by_username_v1(args.username)
    else:
        info = cl.user_info_by_username(args.username)
    u = info.get("user", info)
    print(json.dumps({
        "username": u.get("username"),
        "pk": u.get("pk"),
        "full_name": u.get("full_name"),
        "followers": u.get("follower_count"),
        "following": u.get("following_count"),
        "media": u.get("media_count"),
        "is_private": u.get("is_private"),
        "biography": (u.get("biography") or "")[:120],
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_session_show(args) -> int:
    data = json.loads(Path(args.session).read_text(encoding="utf-8"))

    def mask(v):
        if not v:
            return None
        s = str(v)
        return s[:6] + "..." + s[-4:] if len(s) > 12 else "set"

    auth = data.get("authorization_data", {})
    summary = {
        "mode": data.get("mode"),
        "username": auth.get("username"),
        "user_id": auth.get("user_id"),
        "authorization": mask(auth.get("authorization")),
        "mid": mask(data.get("mid")),
        "ig_www_claim": data.get("ig_www_claim"),
        "ig_u_rur": mask(data.get("ig_u_rur")),
        "ig_u_shbid": mask(data.get("ig_u_shbid")),
        "country": data.get("country"),
        "country_code": data.get("country_code"),
        "locale": data.get("locale"),
        "timezone_offset": data.get("timezone_offset"),
        "eu_dc_enabled": data.get("eu_dc_enabled"),
        "device": data.get("device_settings"),
        "geo": data.get("geo"),
        "cookies": sorted((data.get("cookies") or {}).keys()),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


def cmd_fingerprint(args) -> int:
    from . import fingerprint as fp_mod
    cl = _build_client(args)
    _load_into(cl, args)
    print(fp_mod.render(cl.fingerprint()))
    return 0


def _store(args):
    from .store import SessionStore
    return SessionStore(getattr(args, "store", None), password=getattr(args, "password", None))


def cmd_accounts_list(args) -> int:
    st = _store(args)
    names = st.list()
    if not names:
        print(f"(no accounts in {st.dir})")
        return 0
    for name in names:
        info = st.info(name)
        print(json.dumps(info, ensure_ascii=False))
    return 0


def cmd_accounts_add(args) -> int:
    st = _store(args)
    bundle = st.add(
        args.name, args.source,
        proxy=args.proxy, device_seed=args.device_seed,
        mode=args.mode, bootstrap=args.bootstrap, auto_geo=not args.no_geo,
    )
    auth = bundle.get("authorization_data", {})
    print(f"[+] saved account '{args.name}' (@{auth.get('username')} id={auth.get('user_id')}) "
          f"-> {st._path(args.name)}{' [encrypted]' if st.password else ''}")
    return 0


def cmd_accounts_use(args) -> int:
    st = _store(args)
    cl = st.open(args.name)
    from . import doctor
    print(f"[+] opened '{args.name}': @{cl.username} id={cl.user_id} mode={cl.mode} "
          f"proxy={'set' if getattr(cl, 'proxy', None) else 'none'}")
    print(doctor.render(doctor.diagnose(cl, online=args.online)))
    return 0


def cmd_accounts_remove(args) -> int:
    st = _store(args)
    print("[+] removed" if st.remove(args.name) else "[i] not found", args.name)
    return 0


def cmd_repl(args) -> int:
    cl = _require_session(args)
    banner = (
        f"okgram REPL -- client bound as `cl` (@{cl.username} id={cl.user_id}, mode={cl.mode})\n"
        "examples: cl.get_current_user(); cl.user_info_by_username_v1('instagram')\n"
    )
    import code as _code
    _code.interact(banner=banner, local={"cl": cl, "okgram": __import__("okgram")})
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="okgram",
        description="Phone-grade Instagram private API session tool.",
    )
    p.add_argument("--version", action="version", version=f"okgram {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp, *, session_required=False):
        sp.add_argument("--session", "-s", default="session.json",
                        help="path to the identity bundle JSON (default: session.json)")
        sp.add_argument("--proxy", help="http://user:pass@host:port or socks5://host:port")
        sp.add_argument("--mode", choices=[config.MODE_MOBILE, config.MODE_WEB],
                        default=config.MODE_MOBILE, help="request mode (default: mobile)")
        sp.add_argument("--device-seed", help="stable device seed (default: account id)")
        sp.add_argument("--govern", action="store_true",
                        help="enable the human-like rate governor for write actions")
        sp.add_argument("--guard", choices=["resync", "raise", "warn"],
                        help="egress-IP consistency guard policy")

    sp = sub.add_parser("import", help="install + bootstrap a session and save it")
    sp.add_argument("source", help="sessionid / cookie string / @file / - (stdin)")
    add_common(sp)
    sp.add_argument("--country", help="ISO-2 region override (else auto-detected)")
    sp.add_argument("--locale", help="UI locale e.g. en_US / th_TH")
    sp.add_argument("--no-verify", action="store_true", help="skip get_current_user check")
    sp.add_argument("--no-warmup", action="store_true", help="skip the cold-start sequence")
    sp.add_argument("--no-geo", action="store_true", help="do not auto-detect region")
    sp.add_argument("--no-config", action="store_true", help="skip live launcher/qe sync")
    sp.set_defaults(func=cmd_import)

    sp = sub.add_parser("doctor", help="diagnose why a session may bounce")
    add_common(sp)
    sp.add_argument("--online", action="store_true",
                    help="also detect the egress IP and flag region mismatch")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("geo", help="detect the egress-IP region")
    add_common(sp)
    sp.add_argument("--save", action="store_true", help="apply + save geo to --session")
    sp.set_defaults(func=cmd_geo)

    sp = sub.add_parser("whoami", help="print the logged-in account")
    add_common(sp)
    sp.set_defaults(func=cmd_whoami)

    sp = sub.add_parser("warmup", help="replay the app cold-start, then save")
    add_common(sp)
    sp.set_defaults(func=cmd_warmup)

    sp = sub.add_parser("feed", help="fetch the home timeline")
    add_common(sp)
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(func=cmd_feed)

    sp = sub.add_parser("user", help="fetch a user's profile")
    sp.add_argument("username")
    add_common(sp)
    sp.set_defaults(func=cmd_user)

    sp = sub.add_parser("fingerprint", help="probe + prove the live TLS/HTTP-2 fingerprint")
    add_common(sp)
    sp.set_defaults(func=cmd_fingerprint)

    sp = sub.add_parser("accounts", help="manage a multi-account vault (proxy + encryption)")
    asub = sp.add_subparsers(dest="accounts_command", required=True)

    def add_store_opts(x):
        x.add_argument("--store", help="vault directory (default: ~/.okgram/accounts)")
        x.add_argument("--password", help="passphrase to encrypt/decrypt the vault")

    a = asub.add_parser("list", help="list accounts")
    add_store_opts(a)
    a.set_defaults(func=cmd_accounts_list)

    a = asub.add_parser("add", help="add/replace an account")
    a.add_argument("name")
    a.add_argument("source", help="sessionid / cookie string / @file")
    a.add_argument("--proxy")
    a.add_argument("--mode", choices=[config.MODE_MOBILE, config.MODE_WEB], default=config.MODE_MOBILE)
    a.add_argument("--device-seed")
    a.add_argument("--bootstrap", action="store_true", help="geo+config+warmup before saving")
    a.add_argument("--no-geo", action="store_true")
    add_store_opts(a)
    a.set_defaults(func=cmd_accounts_add)

    a = asub.add_parser("use", help="open an account + diagnose it")
    a.add_argument("name")
    a.add_argument("--online", action="store_true")
    add_store_opts(a)
    a.set_defaults(func=cmd_accounts_use)

    a = asub.add_parser("remove", help="delete an account")
    a.add_argument("name")
    add_store_opts(a)
    a.set_defaults(func=cmd_accounts_remove)

    sp = sub.add_parser("session", help="inspect a saved session bundle")
    ssub = sp.add_subparsers(dest="session_command", required=True)
    sp_show = ssub.add_parser("show", help="print a masked summary")
    sp_show.add_argument("--session", "-s", default="session.json")
    sp_show.set_defaults(func=cmd_session_show)

    sp = sub.add_parser("repl", help="interactive shell with `cl` bound")
    add_common(sp)
    sp.set_defaults(func=cmd_repl)

    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        _eprint("\naborted")
        return 130
    except Exception as exc:  # noqa: BLE001
        _eprint(f"error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
