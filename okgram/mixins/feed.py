"""
FeedMixin — various feeds of the Instagram private API

Covers timeline feed, user feed (user feed / user medias),
liked posts (liked), saved posts (saved), as well as other feeds such as
reels tray and popular feed
Note: explore/search lives in search.py (not here)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError, PrivateAccount, UserNotFound

# Guard against infinite pagination loops (max number of pages to iterate)
_MAX_PAGES = 50


class FeedMixin:
    """Collection of methods related to fetching every kind of "feed"."""

    # attributes already provided by the main client (declared for type hints)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # timeline feed (home page)
    # ------------------------------------------------------------------
    def get_timeline_feed(
        self,
        reason: str = "pull_to_refresh",
        max_id: str = "",
        *,
        seen_posts: str = "",
        unseen_posts: str = "",
    ) -> Dict[str, Any]:
        """
        Fetch the first feed page (home timeline) — a POST even though it is a read
        Returns the raw dict with keys 'feed_items', 'next_max_id', 'more_available'
        """
        headers = {
            "X-Ads-Opt-Out": "0",
            "X-Google-AD-ID": self.device.advertising_id,
            "X-DEVICE-ID": self.device.uuid,
            "X-FB": "1",
        }
        data: Dict[str, Any] = {
            "feed_view_info": "[]",
            "phone_id": self.device.phone_id,
            "reason": reason,
            "battery_level": "100",
            "timezone_offset": str(getattr(self, "timezone_offset", config.TIMEZONE_OFFSET)),
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id or ""),
            "device_id": self.device.uuid,
            "request_id": utils.generate_uuid(),
            "is_charging": "1",
            "is_dark_mode": "1",
            "will_sound_on": "0",
            "session_id": self.device.client_session_id,
            "bloks_versioning_id": config.BLOKS_VERSION_ID,
        }
        if reason in ("pull_to_refresh", "auto_refresh", "cold_start_fetch", "warm_start_fetch"):
            data["is_pull_to_refresh"] = "1" if "pull" in reason else "0"
        else:
            data["is_pull_to_refresh"] = "0"
        if max_id:
            data["max_id"] = max_id
        if seen_posts:
            data["seen_posts"] = seen_posts
        if unseen_posts:
            data["unseen_posts"] = unseen_posts
        return self.private_request("feed/timeline/", data, headers=headers)

    def timeline_feed_items(
        self, amount: int = 0, reason: str = "pull_to_refresh"
    ) -> List[Dict[str, Any]]:
        """
        Fetch timeline posts by paginating; returns a list of feed_items
        amount=0 = fetch everything available (loop guarded to ~50 pages)
        """
        items: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.get_timeline_feed(reason=reason, max_id=max_id)
            page = result.get("feed_items") or []
            items.extend(page)
            if amount and len(items) >= amount:
                return items[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return items[:amount] if amount else items

    # ------------------------------------------------------------------
    # user feed (posts of a single user)
    # ------------------------------------------------------------------
    def user_feed_page(
        self,
        user_id: Union[str, int],
        max_id: str = "",
        *,
        count: int = 12,
    ) -> Dict[str, Any]:
        """
        Fetch one page of a user's post feed (GET) — accepts max_id to page through
        Returns the raw dict with 'items', 'next_max_id', 'more_available'
        """
        params: Dict[str, Any] = {
            "count": count,
            "exclude_comment": "true",
            "only_fetch_first_carousel_media": "false",
        }
        if max_id:
            params["max_id"] = max_id
        try:
            return self.private_request(f"feed/user/{user_id}/", params=params)
        except ClientNotFoundError as exc:
            raise UserNotFound(f"user {user_id} not found", **getattr(exc, "extra", {})) from exc

    def user_medias(
        self, user_id: Union[str, int], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch all of a user's posts by paginating; returns a list of media dicts
        amount=0 = fetch everything (loop guarded to ~50 pages)
        """
        medias: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            try:
                result = self.user_feed_page(user_id, max_id)
            except PrivateAccount:
                raise
            page = result.get("items") or []
            medias.extend(page)
            if amount and len(medias) >= amount:
                return medias[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return medias[:amount] if amount else medias

    def user_feed_by_username(
        self, username: str, amount: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch a user's posts directly by username (uses the .../username/ endpoint)
        Returns a list of media dicts
        """
        params: Dict[str, Any] = {
            "count": 12,
            "exclude_comment": "true",
            "only_fetch_first_carousel_media": "false",
        }
        medias: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            if max_id:
                params["max_id"] = max_id
            try:
                result = self.private_request(
                    f"feed/user/{username}/username/", params=params
                )
            except ClientNotFoundError as exc:
                raise UserNotFound(
                    f"user {username} not found", **getattr(exc, "extra", {})
                ) from exc
            page = result.get("items") or []
            medias.extend(page)
            if amount and len(medias) >= amount:
                return medias[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return medias[:amount] if amount else medias

    # ------------------------------------------------------------------
    # posts of the current account (shortcut)
    # ------------------------------------------------------------------
    def my_medias(self, amount: int = 0) -> List[Dict[str, Any]]:
        """Fetch all posts of the logged-in account; returns a list of media dicts"""
        if not self.user_id:
            raise ClientError("not logged in — no user_id")
        return self.user_medias(self.user_id, amount=amount)

    # ------------------------------------------------------------------
    # liked posts (liked)
    # ------------------------------------------------------------------
    def liked_medias_page(self, max_id: str = "") -> Dict[str, Any]:
        """Fetch one page of posts we have liked (GET) — returns the raw dict"""
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        return self.private_request("feed/liked/", params=params or None)

    def liked_medias(self, amount: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch all posts we have liked by paginating; returns a list of media dicts
        amount=0 = all
        """
        medias: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.liked_medias_page(max_id)
            page = result.get("items") or []
            medias.extend(page)
            if amount and len(medias) >= amount:
                return medias[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return medias[:amount] if amount else medias

    # ------------------------------------------------------------------
    # saved posts (saved)
    # ------------------------------------------------------------------
    def saved_medias_page(self, max_id: str = "") -> Dict[str, Any]:
        """Fetch one page of saved posts (GET) — returns the raw dict"""
        params: Dict[str, Any] = {
            "include_igtv_preview": "false",
            "show_igtv_first": "false",
        }
        if max_id:
            params["max_id"] = max_id
        try:
            return self.private_request("feed/saved/posts/", params=params)
        except ClientNotFoundError:
            # fallback to the old endpoint
            return self.private_request("feed/saved/", params=params)

    def saved_medias(self, amount: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch all saved posts by paginating; returns a list of media dicts
        (each item's structure is nested under 'media') — amount=0 = all
        """
        medias: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.saved_medias_page(max_id)
            page = result.get("items") or []
            for entry in page:
                # the saved feed wraps media inside the 'media' key
                media = entry.get("media") if isinstance(entry, dict) else None
                medias.append(media if media is not None else entry)
            if amount and len(medias) >= amount:
                return medias[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return medias[:amount] if amount else medias

    def collection_medias_page(
        self, collection_id: Union[str, int], max_id: str = ""
    ) -> Dict[str, Any]:
        """Fetch one page of posts in a saved collection (GET) — returns the raw dict"""
        params: Dict[str, Any] = {
            "include_igtv_preview": "false",
        }
        if max_id:
            params["max_id"] = max_id
        return self.private_request(
            f"feed/collection/{collection_id}/posts/", params=params
        )

    def collection_medias(
        self, collection_id: Union[str, int], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch all posts in a saved collection by paginating; returns a list of media dicts"""
        medias: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.collection_medias_page(collection_id, max_id)
            page = result.get("items") or []
            for entry in page:
                media = entry.get("media") if isinstance(entry, dict) else None
                medias.append(media if media is not None else entry)
            if amount and len(medias) >= amount:
                return medias[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return medias[:amount] if amount else medias

    # ------------------------------------------------------------------
    # reels tray (stories at the top of the feed) + popular
    # ------------------------------------------------------------------
    def reels_tray_feed(self, reason: str = "pull_to_refresh") -> Dict[str, Any]:
        """
        Fetch the reels tray (the story row at the top of home) — a POST
        Returns the raw dict with 'tray' (each user's stories)
        """
        data: Dict[str, Any] = {
            "supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES),
            "reason": reason,
            "timezone_offset": str(getattr(self, "timezone_offset", config.TIMEZONE_OFFSET)),
            "tray_session_id": utils.generate_uuid(),
            "request_id": utils.generate_uuid(),
            "_uuid": self.device.uuid,
            "page_size": "50",
        }
        return self.private_request("feed/reels_tray/", data)

    def reels_tray(self, reason: str = "pull_to_refresh") -> List[Dict[str, Any]]:
        """Fetch the reels tray and return only the tray list (stories per user)"""
        result = self.reels_tray_feed(reason=reason)
        return result.get("tray") or []

    def popular_feed_page(self, max_id: str = "") -> Dict[str, Any]:
        """Fetch one page of the popular feed (GET) — returns the raw dict"""
        params: Dict[str, Any] = {
            "people_teaser_supported": "1",
            "rank_token": utils.generate_uuid(),
            "ranked_content": "true",
        }
        if max_id:
            params["max_id"] = max_id
        return self.private_request("feed/popular/", params=params)

    def popular_feed(self, amount: int = 0) -> List[Dict[str, Any]]:
        """Fetch the entire popular feed by paginating; returns a list of media dicts"""
        medias: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.popular_feed_page(max_id)
            page = result.get("items") or []
            medias.extend(page)
            if amount and len(medias) >= amount:
                return medias[:amount]
            if not result.get("more_available"):
                break
            max_id = result.get("next_max_id") or ""
            if not max_id:
                break
        return medias[:amount] if amount else medias
