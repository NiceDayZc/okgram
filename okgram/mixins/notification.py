"""
NotificationMixin — notifications/activity of the Instagram private API

Covers: our own activity notification inbox (news inbox: like/comment/follow),
activity of accounts we follow (news following — possibly deprecated), badges for
the notifications and direct screens, marking notifications as seen (mark seen),
and registering/removing push tokens

Note: this is a mixin, so it has no __init__ — state/request methods come from the
main class (InstagramAPI) via multiple inheritance
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError

# Prevent infinite pagination loops (maximum number of pages to iterate)
_MAX_PAGES = 50


class NotificationMixin:
    """Collection of methods related to notifications/activity (activity feed + badges)"""

    # Attributes the main class already provides (declared for type hints only)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _action_fields(self) -> Dict[str, Any]:
        """Standard fields that IG action POSTs must attach (_uuid / _uid / device_id)"""
        return {
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id) if self.user_id else "",
            "device_id": self.device.device_id,
        }

    # ==================================================================
    # news inbox — our own activity (like / comment / follow / mention)
    # ==================================================================
    def news_inbox_raw(
        self,
        *,
        max_id: str = "",
        mark_as_seen: bool = False,
    ) -> Dict[str, Any]:
        """
        Fetch one page of our activity notification inbox (GET news/inbox/) — returns a raw dict
        Main structure: 'new_stories', 'old_stories', 'continuation_token',
        'last_checked', 'counts'
        """
        params: Dict[str, Any] = {
            "mark_as_seen": "true" if mark_as_seen else "false",
            "timezone_offset": str(
                getattr(self, "timezone_offset", config.TIMEZONE_OFFSET)
            ),
        }
        if max_id:
            params["max_id"] = max_id
        return self.private_request("news/inbox/", params=params)

    def news_inbox(self, *, mark_as_seen: bool = False) -> Dict[str, Any]:
        """
        Fetch our activity notification inbox (like/comment/follow), returns the raw last_json
        Use mark_as_seen=True to mark them as read at the same time
        """
        return self.news_inbox_raw(mark_as_seen=mark_as_seen)

    def news_inbox_stories(
        self, amount: int = 0, *, mark_as_seen: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch our notification list (stories) with pagination, returns a list of story dicts
        Includes both new_stories + old_stories — amount=0 = all (capped at ~50 pages)
        """
        stories: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            result = self.news_inbox_raw(max_id=max_id, mark_as_seen=mark_as_seen)
            page = list(result.get("new_stories") or [])
            page.extend(result.get("old_stories") or [])
            stories.extend(page)
            if amount and len(stories) >= amount:
                return stories[:amount]
            max_id = result.get("continuation_token") or result.get("next_max_id") or ""
            if not max_id or not page:
                break
        return stories[:amount] if amount else stories

    def news_inbox_counts(self) -> Dict[str, Any]:
        """Fetch only the counts section of news/inbox/, e.g. comment_likes, relationships"""
        result = self.news_inbox_raw()
        return result.get("counts", {}) or {}

    # ==================================================================
    # news following — activity of accounts we follow (possibly deprecated)
    # ==================================================================
    def news_following_raw(self, *, max_id: str = "") -> Dict[str, Any]:
        """
        Fetch one page of activity from accounts we follow (GET news/) — returns a raw dict
        This endpoint may be disabled (deprecated) by IG in some versions
        """
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        return self.private_request("news/", params=params or None)

    def news_following(self) -> Dict[str, Any]:
        """Fetch activity of accounts we follow (news/), returns the raw last_json (possibly deprecated)"""
        try:
            return self.news_following_raw()
        except ClientNotFoundError:
            # endpoint is disabled in this version — return an empty dict instead of raising
            return {}

    def news_following_stories(self, amount: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch the activity list of accounts we follow with pagination, returns a list of story dicts
        amount=0 = all (capped at ~50 pages)
        """
        stories: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            try:
                result = self.news_following_raw(max_id=max_id)
            except ClientNotFoundError:
                break
            page = list(result.get("stories") or result.get("new_stories") or [])
            page.extend(result.get("old_stories") or [])
            stories.extend(page)
            if amount and len(stories) >= amount:
                return stories[:amount]
            max_id = result.get("next_max_id") or result.get("continuation_token") or ""
            if not max_id or not page:
                break
        return stories[:amount] if amount else stories

    # ==================================================================
    # badges — notification numbers on icons
    # ==================================================================
    def notification_badge(self) -> Dict[str, Any]:
        """
        Fetch/update the notifications screen badge (POST notifications/badge/), returns badge counts
        Mimics the real app polling the badge periodically
        """
        data: Dict[str, Any] = {
            "phone_id": self.device.phone_id,
            "user_ids": str(self.user_id) if self.user_id else "",
            "device_id": self.device.device_id,
            "_uuid": self.device.uuid,
        }
        return self.private_request("notifications/badge/", data)

    def direct_badge_count(self) -> Dict[str, Any]:
        """Fetch the number of unread direct messages (GET direct_v2/get_badge_count/), returns a raw dict"""
        return self.private_request("direct_v2/get_badge_count/")

    def direct_unread_count(self) -> int:
        """convenience: return the unread direct count as an int (read from badge_count)"""
        result = self.direct_badge_count()
        for key in ("badge_count", "unseen_count", "num_items"):
            value = result.get(key)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0

    def activity_count(self) -> Dict[str, Any]:
        """
        Fetch combined activity counts (GET notifications/badge/ via news/inbox counts)
        Returns the counts dict from news/inbox/ (relationships, comments, likes, etc.)
        """
        return self.news_inbox_counts()

    # ==================================================================
    # mark seen — mark notifications as viewed
    # ==================================================================
    def mark_news_seen(self) -> Dict[str, Any]:
        """
        Mark all notifications as viewed (best-effort)
        Tries GET news/inbox/seen/ first; if that fails, POST news/inbox/seen/
        """
        try:
            return self.private_request("news/inbox/seen/")
        except (ClientNotFoundError, ClientError):
            data = self._action_fields()
            try:
                return self.private_request("news/inbox/seen/", data)
            except ClientError:
                # final fallback: fetch news/inbox/ with mark_as_seen=true
                return self.news_inbox_raw(mark_as_seen=True)

    def mark_story_seen(self, story_id: str) -> Dict[str, Any]:
        """
        Mark a single notification as viewed (POST news/inbox/seen/)
        story_id = the id of the story in the news inbox
        """
        data = self._action_fields()
        data["story_id"] = str(story_id)
        try:
            return self.private_request("news/inbox/seen/", data)
        except ClientError:
            return self.news_inbox_raw(mark_as_seen=True)

    # ==================================================================
    # push token (FCM) — register/remove a token to receive push
    # ==================================================================
    def push_register(
        self,
        device_token: str,
        *,
        device_type: str = "android_mqtt",
    ) -> Dict[str, Any]:
        """
        Register a push token (FCM) to receive push notifications
        (POST push/register/) — returns a raw dict
        """
        data: Dict[str, Any] = {
            "device_type": device_type,
            "is_main_push_channel": "true",
            "device_sub_type": "2",
            "device_token": device_token,
            "_uuid": self.device.uuid,
            "guid": self.device.uuid,
            "phone_id": self.device.phone_id,
            "device_id": self.device.device_id,
            "users": str(self.user_id) if self.user_id else "",
            "family_device_id": self.device.family_device_id,
        }
        return self.private_request("push/register/", data)

    def push_unregister(self, device_token: str) -> Dict[str, Any]:
        """Remove a push token to stop receiving push notifications (POST push/unregister/)"""
        data: Dict[str, Any] = {
            "device_type": "android_mqtt",
            "is_main_push_channel": "true",
            "device_token": device_token,
            "_uuid": self.device.uuid,
            "guid": self.device.uuid,
            "device_id": self.device.device_id,
        }
        return self.private_request("push/unregister/", data)

    # ==================================================================
    # notification settings — per-user notification configuration
    # ==================================================================
    def notification_settings(self) -> Dict[str, Any]:
        """Fetch current notification settings (GET users/notification_preference/), returns a raw dict"""
        try:
            return self.private_request("users/notification_preference/")
        except ClientNotFoundError:
            return {}

    def set_user_notification(
        self, user_id: str, *, enable: bool = True
    ) -> Dict[str, Any]:
        """
        Enable/disable post notifications for a specific user (favorite/notification)
        enable=True = enable notifications, False = disable — returns a raw dict
        """
        action = "favorite" if enable else "unfavorite"
        data = self._action_fields()
        data["user_id"] = str(user_id)
        data["radio_type"] = "wifi-none"
        return self.private_request(f"friendships/{action}/{user_id}/", data)
