"""
UserMixin — user info / profile

Contains methods for fetching user profile info, converting username <-> user_id,
searching users, fetching follower/following lists, fetching tagged media, etc.
(follow/unfollow live in FriendshipMixin — not duplicated here)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import (
    ClientError,
    ClientNotFoundError,
    PrivateAccount,
    UserNotFound,
)

# Maximum number of pages to iterate in "fetch all" pagination to avoid an endless loop
_MAX_PAGES = 50


class UserMixin:
    """Contains methods related to user info / profile (mixin — no __init__)"""

    # attributes provided by the main client (declared for type hinting only)
    user_id: Optional[str]
    username: Optional[str]
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # Fetch user info (private mobile API)
    # ------------------------------------------------------------------
    def user_info_v1(self, pk: Union[int, str]) -> Dict[str, Any]:
        """Fetch user info by user pk via the private API; returns the user dict"""
        try:
            result = self.private_request(f"users/{pk}/info/")
        except ClientNotFoundError as exc:
            raise UserNotFound(f"User not found pk={pk}", **getattr(exc, "extra", {}))
        user = (result or {}).get("user")
        if not user:
            raise UserNotFound(f"User not found pk={pk}")
        return user

    def user_info_by_username_v1(self, username: str) -> Dict[str, Any]:
        """Fetch user info by username via the private API; returns the user dict"""
        username = str(username).lower().strip()
        try:
            result = self.private_request(f"users/{username}/usernameinfo/")
        except ClientNotFoundError as exc:
            raise UserNotFound(
                f"User not found username={username}", **getattr(exc, "extra", {})
            )
        user = (result or {}).get("user")
        if not user:
            raise UserNotFound(f"User not found username={username}")
        return user

    def user_info(self, pk: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch user info by pk (wrapper around v1, in case of a web fallback later)
        Returns the user dict
        """
        try:
            return self.user_info_v1(pk)
        except ClientError:
            # fallback: try fetching via web with username if a username is available
            raise

    def user_info_by_username(self, username: str) -> Dict[str, Any]:
        """Fetch user info by username (wrapper around v1); returns the user dict"""
        return self.user_info_by_username_v1(username)

    # ------------------------------------------------------------------
    # web profile info (public web API)
    # ------------------------------------------------------------------
    def web_profile_info(self, username: str) -> Dict[str, Any]:
        """Fetch profile info via the web API (users/web_profile_info/); returns the user dict"""
        username = str(username).lower().strip()
        try:
            result = self.public_request(
                "users/web_profile_info/", params={"username": username}
            )
        except ClientNotFoundError:
            raise UserNotFound(f"User not found username={username}")
        user = utils.safe_get(result or {}, "data", "user")
        if not user:
            raise UserNotFound(f"User not found username={username}")
        return user

    # ------------------------------------------------------------------
    # Convert username <-> user_id
    # ------------------------------------------------------------------
    def username_to_user_id(self, username: str) -> str:
        """Convert username -> user_id (str)"""
        user = self.user_info_by_username_v1(username)
        return str(user.get("pk") or user.get("pk_id") or "")

    def user_id_to_username(self, pk: Union[int, str]) -> str:
        """Convert user_id -> username (str)"""
        user = self.user_info(pk)
        return str(user.get("username") or "")

    # ------------------------------------------------------------------
    # Search users
    # ------------------------------------------------------------------
    def search_users(self, query: str, count: int = 30) -> List[Dict[str, Any]]:
        """Search users by query; returns a list of user dicts"""
        params = {
            "q": query,
            "count": int(count),
            "search_surface": "user_search_page",
            "timezone_offset": str(getattr(self, "timezone_offset", config.TIMEZONE_OFFSET)),
        }
        result = self.private_request("users/search/", params=params)
        return (result or {}).get("users", []) or []

    def search_users_web(self, query: str) -> List[Dict[str, Any]]:
        """Search users via the web API (topsearch); returns a list of user dicts"""
        params = {"context": "blended", "query": query, "count": 30}
        result = self.public_request("web/search/topsearch/", params=params)
        users = (result or {}).get("users", []) or []
        return [u.get("user", u) for u in users]

    # ------------------------------------------------------------------
    # Helpers for reading fields from user_info
    # ------------------------------------------------------------------
    def user_following_count(self, pk: Union[int, str]) -> int:
        """Number of accounts this user is following"""
        user = self.user_info(pk)
        return int(user.get("following_count") or 0)

    def user_followers_count(self, pk: Union[int, str]) -> int:
        """Number of followers of this user"""
        user = self.user_info(pk)
        return int(user.get("follower_count") or 0)

    def user_media_count(self, pk: Union[int, str]) -> int:
        """Total number of posts by this user"""
        user = self.user_info(pk)
        return int(user.get("media_count") or 0)

    def user_is_private(self, pk: Union[int, str]) -> bool:
        """Whether this user is a private account"""
        user = self.user_info(pk)
        return bool(user.get("is_private"))

    # ------------------------------------------------------------------
    # Current user
    # ------------------------------------------------------------------
    def get_current_user(self) -> Dict[str, Any]:
        """Fetch the profile info of the logged-in account; returns the user dict"""
        result = self.private_request("accounts/current_user/", params={"edit": "true"})
        return (result or {}).get("user", {}) or {}

    def account_info(self) -> Dict[str, Any]:
        """alias of get_current_user — own account info"""
        return self.get_current_user()

    def reel_settings(self) -> Dict[str, Any]:
        """Fetch the reel/story settings of the own account"""
        result = self.private_request("users/reel_settings/")
        return result or {}

    # ------------------------------------------------------------------
    # followers — two-level pagination
    # ------------------------------------------------------------------
    def user_followers_gql(
        self, pk: Union[int, str], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """alias: fetch all followers (uses the private API) — kept for the legacy name"""
        return self.user_followers(pk, amount=amount)

    def user_followers_v1_chunk(
        self,
        pk: Union[int, str],
        max_id: str = "",
        query: str = "",
    ) -> Dict[str, Any]:
        """
        Fetch one page of followers (raw); returns the full dict (with users + next_max_id)
        """
        params: Dict[str, Any] = {
            "search_surface": "follow_list_page",
            "order": "default",
            "enable_groups": "true",
            "rank_token": self._rank_token(pk),
        }
        if query:
            params["query"] = query
        if max_id:
            params["max_id"] = max_id
        return self.private_request(f"friendships/{pk}/followers/", params=params)

    def user_followers(
        self,
        pk: Union[int, str],
        amount: int = 0,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fetch the full list of followers (iterating by next_max_id); returns a list of user dicts
        amount=0 = fetch all (loop capped at ~50 pages)
        """
        return self._paginate_users(
            self.user_followers_v1_chunk, pk, amount=amount, query=query
        )

    # ------------------------------------------------------------------
    # following — two-level pagination
    # ------------------------------------------------------------------
    def user_following_v1_chunk(
        self,
        pk: Union[int, str],
        max_id: str = "",
        query: str = "",
    ) -> Dict[str, Any]:
        """Fetch one page of the accounts a user is following (raw); returns the full dict"""
        params: Dict[str, Any] = {
            "includes_hashtags": "false",
            "search_surface": "follow_list_page",
            "order": "default",
            "enable_groups": "true",
            "rank_token": self._rank_token(pk),
        }
        if query:
            params["query"] = query
        if max_id:
            params["max_id"] = max_id
        return self.private_request(f"friendships/{pk}/following/", params=params)

    def user_following(
        self,
        pk: Union[int, str],
        amount: int = 0,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fetch the full list of accounts a user is following (iterating by next_max_id); returns a list of user dicts
        amount=0 = fetch all (loop capped at ~50 pages)
        """
        return self._paginate_users(
            self.user_following_v1_chunk, pk, amount=amount, query=query
        )

    # ------------------------------------------------------------------
    # mutual followers / similar / related
    # ------------------------------------------------------------------
    def user_mutual_followers(self, pk: Union[int, str]) -> List[Dict[str, Any]]:
        """Fetch mutual followers with this user; returns a list of user dicts"""
        result = self.private_request(
            f"friendships/{pk}/mutual_followers/",
            params={"rank_token": self._rank_token(pk)},
        )
        return (result or {}).get("users", []) or []

    def user_similar_accounts(self, pk: Union[int, str]) -> List[Dict[str, Any]]:
        """Fetch similar/suggested accounts from this user (chaining); returns a list of user dicts"""
        params = {
            "target_id": str(pk),
            "include_reel": "true",
        }
        result = self.private_request("discover/chaining/", params=params)
        return (result or {}).get("users", []) or []

    def user_related_profiles(self, pk: Union[int, str]) -> List[Dict[str, Any]]:
        """alias of user_similar_accounts — related/suggested profiles"""
        return self.user_similar_accounts(pk)

    # ------------------------------------------------------------------
    # user about / account details (about this account)
    # ------------------------------------------------------------------
    def user_about(self, pk: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch the 'about this account' info (signup date, country, etc.); returns a dict
        """
        params = {
            "user_id": str(pk),
            "referer_type": "ProfileMore",
        }
        result = self.private_request(
            "users/get_disclosure_text/", params=params
        )
        return result or {}

    # ------------------------------------------------------------------
    # tagged media / usertag — two-level pagination
    # ------------------------------------------------------------------
    def usertag_medias_chunk(
        self, pk: Union[int, str], max_id: str = ""
    ) -> Dict[str, Any]:
        """Fetch one page of media this user is tagged in (raw); returns the full dict"""
        params: Dict[str, Any] = {
            "rank_token": self._rank_token(pk),
            "count": 20,
        }
        if max_id:
            params["max_id"] = max_id
        return self.private_request(f"usertags/{pk}/feed/", params=params)

    def usertag_medias(
        self, pk: Union[int, str], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch all media this user is tagged in (iterating by next_max_id); returns a list of media dicts
        amount=0 = fetch all (loop capped at ~50 pages)
        """
        return self._paginate_items(
            self.usertag_medias_chunk, pk, items_key="items", amount=amount
        )

    # ------------------------------------------------------------------
    # user highlights
    # ------------------------------------------------------------------
    def user_highlights(self, pk: Union[int, str]) -> List[Dict[str, Any]]:
        """Fetch all story highlights of a user; returns a list of tray (reel) dicts"""
        params = {
            "supported_capabilities_new": utils.json_dumps(
                config.SUPPORTED_CAPABILITIES
            ),
            "phone_id": getattr(self.device, "phone_id", ""),
            "battery_level": "100",
            "is_charging": "0",
            "will_sound_on": "0",
        }
        result = self.private_request(
            f"highlights/{pk}/highlights_tray/", params=params
        )
        return (result or {}).get("tray", []) or []

    # ------------------------------------------------------------------
    # block / mute (write action — POST)
    # ------------------------------------------------------------------
    def user_block(
        self, pk: Union[int, str], surface: str = "profile"
    ) -> Dict[str, Any]:
        """Block this user; returns the result dict"""
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "user_id": str(pk),
            "device_id": self.device.device_id,
            "container_module": surface,
        }
        result = self.private_request(f"friendships/block/{pk}/", data)
        return result or {}

    def user_unblock(
        self, pk: Union[int, str], surface: str = "profile"
    ) -> Dict[str, Any]:
        """Unblock this user; returns the result dict"""
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "user_id": str(pk),
            "device_id": self.device.device_id,
            "container_module": surface,
        }
        result = self.private_request(f"friendships/unblock/{pk}/", data)
        return result or {}

    def blocked_users(self) -> List[Dict[str, Any]]:
        """Fetch the list of users we have blocked; returns a list of user dicts"""
        result = self.private_request("users/blocked_list/")
        return (result or {}).get("blocked_list", []) or []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _rank_token(self, pk: Union[int, str]) -> str:
        """Build a rank_token in the form '<uid>_<uuid>' required by several endpoints"""
        uid = self.user_id or pk
        uuid_ = getattr(self.device, "uuid", "")
        return f"{uid}_{uuid_}"

    def _paginate_users(
        self,
        chunk_func: Any,
        pk: Union[int, str],
        amount: int = 0,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Iterate pagination of an endpoint that returns {'users': [...], 'next_max_id': ...}
        until amount is reached or pages run out (loop capped at ~50 pages)
        """
        users: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            try:
                result = chunk_func(pk, max_id=max_id, query=query)
            except PrivateAccount:
                raise
            except ClientError:
                break
            page = (result or {}).get("users", []) or []
            users.extend(page)
            if amount and len(users) >= amount:
                return users[:amount]
            max_id = (result or {}).get("next_max_id") or ""
            if not max_id or not page:
                break
        if amount:
            return users[:amount]
        return users

    def _paginate_items(
        self,
        chunk_func: Any,
        pk: Union[int, str],
        items_key: str = "items",
        amount: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Iterate pagination of a feed endpoint that returns {'<items_key>': [...],
        'next_max_id': ..., 'more_available': bool} until amount is reached or pages run out
        """
        items: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            try:
                result = chunk_func(pk, max_id=max_id)
            except ClientError:
                break
            page = (result or {}).get(items_key, []) or []
            items.extend(page)
            if amount and len(items) >= amount:
                return items[:amount]
            more = (result or {}).get("more_available")
            max_id = (result or {}).get("next_max_id") or ""
            if not max_id or not page or more is False:
                break
        if amount:
            return items[:amount]
        return items
