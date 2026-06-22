"""
InstagramAPI — the main class that combines all mixins together

Usage:
    from okgram import InstagramAPI

    cl = InstagramAPI()
    cl.login("username", "password")
    cl.dump_settings("session.json")        # save for next time

    me = cl.get_current_user()
    user = cl.user_info_by_username_v1("instagram")
    cl.follow(user["pk"])
    cl.media_like("3123456789_123")
    cl.direct_send_text("Hello", user_ids=[user["pk"]])

Next time no need to login again:
    cl = InstagramAPI()
    cl.load_settings("session.json")
    cl.login("username", "password")        # reuses the existing token if not yet expired
"""
from __future__ import annotations

import logging
from typing import Optional, Union

from . import config, transport
from .device import Device
from .mixins.account import AccountMixin
from .mixins.auth import AuthMixin
from .mixins.clips import ClipsMixin
from .mixins.collection import CollectionMixin
from .mixins.comment import CommentMixin
from .mixins.direct import DirectMixin
from .mixins.feed import FeedMixin
from .mixins.friendship import FriendshipMixin
from .mixins.hashtag import HashtagMixin
from .mixins.insights import InsightsMixin
from .mixins.live import LiveMixin
from .mixins.location import LocationMixin
from .mixins.media import MediaMixin
from .mixins.notification import NotificationMixin
from .mixins.private import PrivateRequestMixin
from .mixins.search import SearchMixin
from .mixins.story import StoryMixin
from .mixins.upload import UploadMixin
from .mixins.user import UserMixin

logger = logging.getLogger("okgram")


# mixin order = priority order in the MRO (the topmost wins when method names collide)
# place the "appropriate owner" of each duplicated method first:
#   AccountMixin    -> account_info, get_current_user, change_profile_picture
#   FriendshipMixin -> user_followers, user_following, blocked_users
#   StoryMixin      -> reels_tray, user_highlights
#   CollectionMixin -> collection_medias*, saved_medias*
#   UserMixin       -> search_users, user_related_profiles, user_info*
class InstagramAPI(
    PrivateRequestMixin,
    AuthMixin,
    AccountMixin,
    FriendshipMixin,
    StoryMixin,
    CollectionMixin,
    UserMixin,
    SearchMixin,
    MediaMixin,
    CommentMixin,
    UploadMixin,
    ClipsMixin,
    DirectMixin,
    HashtagMixin,
    LocationMixin,
    FeedMixin,
    InsightsMixin,
    LiveMixin,
    NotificationMixin,
):
    """
    Instagram Private API client covering every endpoint category

    Parameters
    ----------
    settings : dict | None
        previously dumped state (from get_settings()) — if provided, restores immediately
    proxy : str | None
        proxy in the form "http://user:pass@host:port" or "socks5://host:port"
    device_seed : str | None
        seed for the device (recommended to use the username so the device stays consistent per account)
    locale, country, country_code, timezone_offset :
        set these to match the real account to reduce the risk of being flagged
    delay_range : tuple | None
        random delay range between requests (seconds) — None = no delay (fast but risky)
    """

    def __init__(
        self,
        settings: Optional[dict] = None,
        *,
        proxy: Optional[str] = None,
        device_seed: Optional[str] = None,
        mode: str = config.MODE_MOBILE,
        auto_geo: bool = True,
        govern: bool = False,
        guard: Union[bool, str] = False,
        locale: str = config.LOCALE,
        country: str = config.DEFAULT_COUNTRY,
        country_code: int = config.DEFAULT_COUNTRY_CODE,
        timezone_offset: int = config.TIMEZONE_OFFSET,
        delay_range: Optional[tuple] = config.REQUEST_DELAY_RANGE,
        app_version: str = config.APP_VERSION,
        version_code: str = config.VERSION_CODE,
        request_timeout: int = config.REQUEST_TIMEOUT,
        max_retries: int = config.MAX_RETRIES,
        engine: str = "auto",
        impersonate: Optional[str] = None,
    ):
        # --- device first (its Android version picks the TLS/OkHttp profile) ---
        self.device = Device(seed=device_seed)

        # mode: 'mobile' (i.instagram.com, OkHttp TLS, Bearer) or 'web'
        # (www.instagram.com, Chrome TLS, cookie+csrf) -- pick the one that matches
        # where the session was minted to stay origin-consistent.
        self.mode = mode
        self.auto_geo = auto_geo

        # --- HTTP transport that mimics the real client for the chosen mode ---
        # mobile -> tls_client OkHttp (HTTP/2 + OkHttp JA3/JA4); web -> curl_cffi
        # Chrome so the TLS matches the browser UA the web session expects.
        self.engine = engine
        self.impersonate = impersonate
        if mode == config.MODE_WEB and engine == "auto":
            # web needs browser TLS; if curl_cffi is missing, fall back to
            # 'requests' (Python TLS) NOT 'auto' -- 'auto' would resolve to
            # tls_client/OkHttp, i.e. a *phone* fingerprint on a web session.
            engine = "curl_cffi" if transport.HAS_CURL_CFFI else "requests"
            if impersonate is None:
                impersonate = transport.WEB_IMPERSONATE_DEFAULT
        self.session = transport.build_session(
            engine=engine,
            impersonate=impersonate,
            android_release=self.device.profile.get("android_release"),
        )
        # remember which mode the transport was built for, so a later
        # load_settings() that changes the mode can rebuild it to match.
        self._transport_mode = self.mode

        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.authorization: str = ""
        self.mid: str = ""
        self.ig_www_claim: str = "0"
        self.csrftoken: str = ""
        # session-routing headers (captured live, echoed back, persisted)
        self.ig_u_rur: str = ""
        self.ig_u_shbid: str = ""
        self.ig_u_shbts: str = ""
        self.ig_direct_region_hint: str = ""

        # --- adjustable config / region (kept internally consistent) ---
        self.locale = locale
        self.country = country
        self.country_code = country_code
        self.timezone_offset = timezone_offset
        self.eu_dc_enabled = (
            "true" if str(country).upper() in config.EU_DC_COUNTRIES else "false"
        )
        self.delay_range = delay_range
        self.app_version = app_version
        self.version_code = version_code
        self.bloks_version_id = config.BLOKS_VERSION_ID
        self.nav_chain = ""
        self.request_timeout = request_timeout
        self.max_retries = max_retries

        # geo / live-config state
        self.geo = None
        self._geo_synced = False
        self._live_config_synced_at = 0.0

        # hardcore layer: rate governor + egress guard (opt-in)
        self.governor = None
        # guard policy: False | True ("resync") | "resync" | "raise" | "warn"
        self.guard_policy = ("resync" if guard is True else guard) or None
        self._egress_checked = False

        # auth state
        self.password_encryption_pub_key = None
        self.password_encryption_key_id = None
        self.last_login = None
        self.challenge_context = None
        self.two_factor_info = None

        # latest response
        self.last_response = None
        self.last_json = {}

        if proxy:
            self.set_proxy(proxy)
        if govern:
            self.enable_governor()
        if settings:
            self.set_settings(settings)

    # ------------------------------------------------------------------
    def set_proxy(self, proxy: str) -> "InstagramAPI":
        """Set the proxy ('http://...', 'socks5://...') — socks requires requests[socks]"""
        self.proxy = proxy
        self.session.proxies = {"http": proxy, "https": proxy}
        return self

    def set_locale(self, locale: str, country: str = None, country_code: int = None):
        """Change the locale/country"""
        self.locale = locale
        if country:
            self.country = country
        if country_code:
            self.country_code = country_code
        return self

    def set_user_agent(self, app_version: str = None, version_code: str = None):
        """Change the app version (use when IG starts to reject old versions)"""
        if app_version:
            self.app_version = app_version
        if version_code:
            self.version_code = version_code
        return self

    def set_mode(self, mode: str) -> "InstagramAPI":
        """Switch between 'mobile' and 'web' request modes (rebuilds the transport
        so the TLS fingerprint matches the new mode)."""
        self.mode = mode
        self._sync_transport_to_mode()
        return self

    def _sync_transport_to_mode(self) -> None:
        """
        Rebuild the transport if the engine no longer matches ``self.mode`` (e.g.
        after load_settings restored a different mode). Web => browser TLS
        (curl_cffi Chrome, else requests); mobile => OkHttp (tls_client). Preserves
        the proxy; cookies are (re)loaded by the caller afterwards.
        """
        if getattr(self, "_transport_mode", None) == self.mode:
            return
        if self.mode == config.MODE_WEB:
            engine = "curl_cffi" if transport.HAS_CURL_CFFI else "requests"
            impersonate = self.impersonate or transport.WEB_IMPERSONATE_DEFAULT
        else:
            engine = self.engine or "auto"
            impersonate = self.impersonate
        self.session = transport.build_session(
            engine=engine,
            impersonate=impersonate,
            android_release=self.device.profile.get("android_release"),
        )
        self._transport_mode = self.mode
        if getattr(self, "proxy", None):
            self.set_proxy(self.proxy)

    # ------------------------------------------------------------------
    # self-configuring sync (geo + live app-config)
    # ------------------------------------------------------------------
    def sync_geo(self, *, force: bool = False):
        """
        Detect the egress-IP region and align country / calling-code / timezone /
        EU-DC so the fingerprint matches the network. Works for any country and is
        honoured through the active proxy. Best-effort: returns the applied
        GeoProfile or None, never raises.
        """
        from . import live_config

        profile = live_config.maybe_sync_geo(self, force=force)
        self._geo_synced = profile is not None or self._geo_synced
        return profile

    def sync_config(self, *, login: bool = False, force: bool = False) -> dict:
        """
        Pull the live server config (launcher/sync + qe/sync): the current bloks
        version, the password public key, and the routing headers. Best-effort.
        """
        from . import live_config

        return live_config.sync(self, login=login, force=force)

    def bootstrap(
        self,
        cookies=None,
        *,
        sessionid: Optional[str] = None,
        verify: bool = True,
        warmup: bool = True,
        sync_geo: bool = True,
        sync_config: bool = True,
    ) -> bool:
        """
        One-call, phone-grade session bring-up -- the recommended entry point.

        Order mirrors a real app launch, so every request after this is internally
        consistent:
            1. align region to the egress IP   (sync_geo)
            2. pull live server config         (sync_config: bloks/pubkey/routing)
            3. install the session             (login_by_cookie, if cookies given)
            4. replay the cold-start sequence  (warmup: timeline/stories/inbox/me)

        Pass ``cookies`` (any format :meth:`parse_cookies` accepts) or ``sessionid``
        to install a session; omit both to just sync geo/config on an already
        loaded session. Returns True if a usable session is present afterwards.
        """
        if sync_geo and self.auto_geo:
            try:
                self.sync_geo()
            except Exception:  # noqa: BLE001
                logger.debug("bootstrap: geo sync skipped", exc_info=True)
        if sync_config:
            try:
                self.sync_config(login=not self.is_authenticated)
            except Exception:  # noqa: BLE001
                logger.debug("bootstrap: config sync skipped", exc_info=True)

        if sessionid and not cookies:
            cookies = {"sessionid": str(sessionid).strip()}
        if cookies is not None:
            try:
                return self.login_by_cookie(cookies, verify=verify, warmup=warmup)
            except Exception:  # noqa: BLE001 -- bootstrap is best-effort; an invalid
                # or expired session surfaces as False, not an uncaught traceback.
                logger.debug("bootstrap: login_by_cookie failed", exc_info=True)
                return False

        # no new cookies -> just (optionally) warm up the existing session
        if warmup and self.is_authenticated:
            try:
                from . import behaviors
                behaviors.cold_start(self)
            except Exception:  # noqa: BLE001
                pass
        return self.is_authenticated

    # ------------------------------------------------------------------
    # hardcore layer: rate governor / egress guard / fingerprint
    # ------------------------------------------------------------------
    def enable_governor(self, **kwargs):
        """
        Attach a human-like rate governor (per-action caps + think-time + cooldown)
        so write actions can't burst into a ``feedback_required`` block. Reads are
        never gated. Returns the governor. kwargs pass through to RateGovernor
        (limits, think_time, sleep_window, mode, ...).
        """
        from .limits import RateGovernor

        kwargs.setdefault("timezone_offset", self.timezone_offset)
        self.governor = RateGovernor(**kwargs)
        return self.governor

    def disable_governor(self) -> "InstagramAPI":
        self.governor = None
        return self

    def guard_egress(self, *, policy: Optional[str] = None) -> dict:
        """
        Verify the egress IP's region still matches the session's region.
        policy: 'resync' (re-align, default) | 'raise' | 'warn'.
        """
        from . import guard

        return guard.verify_egress(self, policy=policy or self.guard_policy or "resync")

    def fingerprint(self, *, timeout: int = 10) -> dict:
        """Probe + classify the live TLS/HTTP-2 fingerprint of this client."""
        from . import fingerprint as fp

        return fp.summary(self, timeout=timeout)

    @property
    def is_authenticated(self) -> bool:
        """Whether logged in (has a token or sessionid)"""
        return bool(
            self.authorization or self.session.cookies.get("sessionid")
        )

    def __repr__(self) -> str:
        who = self.username or "not logged in yet"
        return f"<InstagramAPI {who} v{self.app_version}>"
