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
from typing import Optional

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
        locale: str = config.LOCALE,
        country: str = "US",
        country_code: int = 1,
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

        # --- HTTP transport that mimics the Instagram Android app ---
        # engine: 'auto' (tls_client > curl_cffi > requests) | 'tls_client'
        #         | 'curl_cffi' | 'requests'. tls_client impersonates OkHttp on
        # Android (HTTP/2 + OkHttp JA3/JA4) — the closest match to the real app.
        self.engine = engine
        self.impersonate = impersonate
        self.session = transport.build_session(
            engine=engine,
            impersonate=impersonate,
            android_release=self.device.profile.get("android_release"),
        )

        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        self.password: Optional[str] = None
        self.authorization: str = ""
        self.mid: str = ""
        self.ig_www_claim: str = "0"
        self.csrftoken: str = ""

        # --- adjustable config ---
        self.locale = locale
        self.country = country
        self.country_code = country_code
        self.timezone_offset = timezone_offset
        self.delay_range = delay_range
        self.app_version = app_version
        self.version_code = version_code
        self.request_timeout = request_timeout
        self.max_retries = max_retries

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

    @property
    def is_authenticated(self) -> bool:
        """Whether logged in (has a token or sessionid)"""
        return bool(
            self.authorization or self.session.cookies.get("sessionid")
        )

    def __repr__(self) -> str:
        who = self.username or "not logged in yet"
        return f"<InstagramAPI {who} v{self.app_version}>"
