"""
FriendshipMixin — manage relationships between accounts

Covers: follow/unfollow, followers/following (with pagination),
pending follow requests, block/unblock, remove follower,
mute/unmute posts and stories, restrict/unrestrict, friendship status
and the list of blocked accounts
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils  # noqa: F401  (config kept for later use)
from ..exceptions import ClientError, UserNotFound

# Maximum number of pages to iterate in pagination (avoids an endless loop when amount=0)
_MAX_PAGES = 50
# Default page size for followers/following
_DEFAULT_COUNT = 100

# User numeric id accepts both int and str
UserId = Union[int, str]


class FriendshipMixin:
    """Contains all methods of the friendship category"""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _friendship_action_payload(self, **extra: Any) -> Dict[str, Any]:
        """Build the standard action payload (follow/block/...) with identity fields"""
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        data.update(extra)
        return data

    # ==================================================================
    # FOLLOW / UNFOLLOW
    # ==================================================================
    def follow(
        self,
        user_id: UserId,
        *,
        container_module: str = "profile",
    ) -> Dict[str, Any]:
        """Follow a user; returns the latest friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(
            user_id=user_id,
            radio_type="wifi-none",
            container_module=container_module,
        )
        result = self.private_request(f"friendships/create/{user_id}/", data)
        return result.get("friendship_status", result)

    def unfollow(
        self,
        user_id: UserId,
        *,
        container_module: str = "profile",
    ) -> Dict[str, Any]:
        """Unfollow a user; returns the latest friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(
            user_id=user_id,
            radio_type="wifi-none",
            container_module=container_module,
        )
        result = self.private_request(f"friendships/destroy/{user_id}/", data)
        return result.get("friendship_status", result)

    # ==================================================================
    # FOLLOWERS (pagination)
    # ==================================================================
    def user_followers_page(
        self,
        user_id: UserId,
        max_id: str = "",
        count: int = _DEFAULT_COUNT,
        query: str = "",
    ) -> Dict[str, Any]:
        """Fetch one raw page of followers; returns the whole dict (with users, next_max_id)"""
        user_id = str(user_id)
        params: Dict[str, Any] = {
            "count": count,
            "rank_token": f"{self.user_id}_{self.device.uuid}",
            "search_surface": "follow_list_page",
        }
        if max_id:
            params["max_id"] = max_id
        if query:
            params["query"] = query
        return self.private_request(
            f"friendships/{user_id}/followers/", params=params
        )

    def user_followers(
        self,
        user_id: UserId,
        amount: int = 0,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fetch the full list of followers (amount=0) or until amount is reached
        Returns a list of user dicts
        """
        users: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.user_followers_page(
                user_id, max_id=max_id, query=query
            )
            page_users = result.get("users") or []
            users.extend(page_users)
            if amount and len(users) >= amount:
                return users[:amount]
            max_id = result.get("next_max_id") or ""
            if not max_id or not page_users:
                break
        return users[:amount] if amount else users

    # ==================================================================
    # FOLLOWING (pagination)
    # ==================================================================
    def user_following_page(
        self,
        user_id: UserId,
        max_id: str = "",
        count: int = _DEFAULT_COUNT,
        query: str = "",
    ) -> Dict[str, Any]:
        """Fetch one raw page of following; returns the whole dict (with users, next_max_id)"""
        user_id = str(user_id)
        params: Dict[str, Any] = {
            "count": count,
            "rank_token": f"{self.user_id}_{self.device.uuid}",
        }
        if max_id:
            params["max_id"] = max_id
        if query:
            params["query"] = query
        return self.private_request(
            f"friendships/{user_id}/following/", params=params
        )

    def user_following(
        self,
        user_id: UserId,
        amount: int = 0,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Fetch the full list of accounts a user is following (amount=0) or until amount is reached
        Returns a list of user dicts
        """
        users: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.user_following_page(
                user_id, max_id=max_id, query=query
            )
            page_users = result.get("users") or []
            users.extend(page_users)
            if amount and len(users) >= amount:
                return users[:amount]
            max_id = result.get("next_max_id") or ""
            if not max_id or not page_users:
                break
        return users[:amount] if amount else users

    # ==================================================================
    # PENDING REQUESTS (pending follow requests)
    # ==================================================================
    def pending_requests(self) -> List[Dict[str, Any]]:
        """Fetch the list of follow requests awaiting approval; returns a list of user dicts"""
        result = self.private_request("friendships/pending/")
        return result.get("users") or []

    def pending_inbox(self) -> Dict[str, Any]:
        """Fetch the full pending follow requests (with users, suggested_users, ...)"""
        return self.private_request("friendships/pending/")

    def approve_pending(self, user_id: UserId) -> Dict[str, Any]:
        """Approve a follow request from a user; returns the friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(user_id=user_id)
        result = self.private_request(f"friendships/approve/{user_id}/", data)
        return result.get("friendship_status", result)

    def reject_pending(self, user_id: UserId) -> Dict[str, Any]:
        """Reject/ignore a follow request from a user; returns the friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(user_id=user_id)
        result = self.private_request(f"friendships/ignore/{user_id}/", data)
        return result.get("friendship_status", result)

    # ==================================================================
    # BLOCK / UNBLOCK
    # ==================================================================
    def block(
        self,
        user_id: UserId,
        *,
        container_module: str = "profile",
    ) -> Dict[str, Any]:
        """Block a user; returns the friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(
            user_id=user_id,
            container_module=container_module,
        )
        result = self.private_request(f"friendships/block/{user_id}/", data)
        return result.get("friendship_status", result)

    def unblock(
        self,
        user_id: UserId,
        *,
        container_module: str = "profile",
    ) -> Dict[str, Any]:
        """Unblock a user; returns the friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(
            user_id=user_id,
            container_module=container_module,
        )
        result = self.private_request(f"friendships/unblock/{user_id}/", data)
        return result.get("friendship_status", result)

    def blocked_users(self) -> List[Dict[str, Any]]:
        """Fetch the list of accounts we have blocked; returns a list of user dicts"""
        result = self.private_request("users/blocked_list/")
        return result.get("blocked_list") or []

    # ==================================================================
    # REMOVE FOLLOWER
    # ==================================================================
    def remove_follower(
        self,
        user_id: UserId,
        *,
        container_module: str = "profile",
    ) -> Dict[str, Any]:
        """Remove this follower (without blocking); returns the friendship_status dict"""
        user_id = str(user_id)
        data = self._friendship_action_payload(
            user_id=user_id,
            container_module=container_module,
        )
        result = self.private_request(
            f"friendships/remove_follower/{user_id}/", data
        )
        return result.get("friendship_status", result)

    # ==================================================================
    # MUTE / UNMUTE (posts and stories)
    # ==================================================================
    def mute_posts(self, user_id: UserId) -> Dict[str, Any]:
        """Hide a user's posts from the feed (mute posts); returns the result dict"""
        data = self._friendship_action_payload(
            target_posts_author_id=str(user_id),
        )
        return self.private_request(
            "friendships/mute_posts_or_story_from_follow/", data
        )

    def unmute_posts(self, user_id: UserId) -> Dict[str, Any]:
        """Unmute a user's posts; returns the result dict"""
        data = self._friendship_action_payload(
            target_posts_author_id=str(user_id),
        )
        return self.private_request(
            "friendships/unmute_posts_or_story_from_follow/", data
        )

    def mute_stories(self, user_id: UserId) -> Dict[str, Any]:
        """Hide a user's stories (mute stories); returns the result dict"""
        data = self._friendship_action_payload(
            target_reel_author_id=str(user_id),
        )
        return self.private_request(
            "friendships/mute_posts_or_story_from_follow/", data
        )

    def unmute_stories(self, user_id: UserId) -> Dict[str, Any]:
        """Unmute a user's stories; returns the result dict"""
        data = self._friendship_action_payload(
            target_reel_author_id=str(user_id),
        )
        return self.private_request(
            "friendships/unmute_posts_or_story_from_follow/", data
        )

    def mute_posts_and_stories(self, user_id: UserId) -> Dict[str, Any]:
        """Hide both a user's posts and stories at once; returns the result dict"""
        uid = str(user_id)
        data = self._friendship_action_payload(
            target_posts_author_id=uid,
            target_reel_author_id=uid,
        )
        return self.private_request(
            "friendships/mute_posts_or_story_from_follow/", data
        )

    def unmute_posts_and_stories(self, user_id: UserId) -> Dict[str, Any]:
        """Unmute both a user's posts and stories at once; returns the result dict"""
        uid = str(user_id)
        data = self._friendship_action_payload(
            target_posts_author_id=uid,
            target_reel_author_id=uid,
        )
        return self.private_request(
            "friendships/unmute_posts_or_story_from_follow/", data
        )

    # ==================================================================
    # FRIENDSHIP STATUS (read relationship status)
    # ==================================================================
    def friendship_show(self, user_id: UserId) -> Dict[str, Any]:
        """
        View the relationship status with a single user
        Returns a dict such as {following, followed_by, blocking, is_private, muting, ...}
        """
        user_id = str(user_id)
        try:
            return self.private_request(f"friendships/show/{user_id}/")
        except ClientError as exc:
            code = getattr(exc, "code", None)
            if code == 404:
                raise UserNotFound(
                    f"User not found {user_id}", code=404
                ) from exc
            raise

    def friendship_show_many(
        self, user_ids: List[UserId]
    ) -> Dict[str, Dict[str, Any]]:
        """
        View the relationship status with multiple users at once (POST)
        Returns a dict map: {user_id(str): {following, followed_by, ...}}
        """
        ids_csv = ",".join(str(uid) for uid in user_ids)
        data = {
            "user_ids": ids_csv,
            "_uuid": self.device.uuid,
        }
        result = self.private_request("friendships/show_many/", data)
        return result.get("friendship_statuses") or {}

    # ==================================================================
    # RESTRICT / UNRESTRICT
    # ==================================================================
    def restrict(self, user_id: UserId) -> Dict[str, Any]:
        """Restrict a user; returns the result dict (with users/friendship_statuses)"""
        data = self._friendship_action_payload(
            target_user_id=str(user_id),
            container_module="profile",
        )
        return self.private_request("restrict_action/restrict/", data)

    def unrestrict(self, user_id: UserId) -> Dict[str, Any]:
        """Unrestrict a user; returns the result dict"""
        data = self._friendship_action_payload(
            target_user_id=str(user_id),
            container_module="profile",
        )
        return self.private_request("restrict_action/unrestrict/", data)

    def restricted_users(self) -> List[Dict[str, Any]]:
        """Fetch the list of accounts we have restricted; returns a list of user dicts"""
        result = self.private_request("restrict_action/get_restricted_users/")
        return result.get("users") or []

    # ==================================================================
    # convenience: fetch only user ids (not the full dict)
    # ==================================================================
    def user_followers_ids(
        self, user_id: UserId, amount: int = 0
    ) -> List[str]:
        """Return only the list of user ids (str) of followers"""
        return [
            str(u.get("pk"))
            for u in self.user_followers(user_id, amount=amount)
            if u.get("pk") is not None
        ]

    def user_following_ids(
        self, user_id: UserId, amount: int = 0
    ) -> List[str]:
        """Return only the list of user ids (str) of accounts being followed"""
        return [
            str(u.get("pk"))
            for u in self.user_following(user_id, amount=amount)
            if u.get("pk") is not None
        ]

    # convenience: check whether currently following
    def is_following(self, user_id: UserId) -> bool:
        """Return True if the current account is following this user"""
        status = self.friendship_show(user_id)
        return bool(status.get("following"))

    def is_followed_by(self, user_id: UserId) -> bool:
        """Return True if this user is following the current account"""
        status = self.friendship_show(user_id)
        return bool(status.get("followed_by"))
