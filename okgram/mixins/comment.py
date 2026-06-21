"""
CommentMixin — manage comments on media (posts/reels)

Covers: writing/replying to comments, fetching comment lists + replies (with pagination),
liking/unliking comments, deleting comments (single/bulk), pinning/unpinning comments
and viewing who liked a comment
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientNotFoundError


class CommentMixin:
    """Contains methods related to comments on media (i.instagram.com/api/v1)"""

    # attributes already present on the main client (declared for type hinting)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _media_id_full(self, media_id: Union[str, int]) -> str:
        """Normalize media_id into the full form '<pk>_<userid>' if it lacks a user id"""
        mid = str(media_id)
        if "_" in mid:
            return mid
        if self.user_id:
            return utils.pk_with_user_id(mid, self.user_id)
        return mid

    # ------------------------------------------------------------------
    # Write / reply to a comment
    # ------------------------------------------------------------------
    def media_comment(
        self,
        media_id: str,
        text: str,
        replied_to_comment_id: str = "",
    ) -> Dict[str, Any]:
        """Write a comment on a media (pass replied_to_comment_id to make it a reply)"""
        media_id = self._media_id_full(media_id)
        data: Dict[str, Any] = {
            "comment_text": text,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "idempotence_token": utils.generate_uuid(),
            "containermodule": "comments_v2",
            "radio_type": "wifi-none",
        }
        if replied_to_comment_id:
            data["replied_to_comment_id"] = str(replied_to_comment_id)
        result = self.private_request(
            f"media/{media_id}/comment/", data=data
        )
        return result.get("comment", {})

    def reply_to_comment(
        self, media_id: str, text: str, comment_id: str
    ) -> Dict[str, Any]:
        """Reply to the specified comment (convenience over media_comment)"""
        return self.media_comment(
            media_id, text, replied_to_comment_id=comment_id
        )

    def media_comment_by_pk(
        self,
        media_pk: Union[str, int],
        text: str,
        replied_to_comment_id: str = "",
    ) -> Dict[str, Any]:
        """Write a comment given a media pk (the user id is appended automatically)"""
        return self.media_comment(
            str(media_pk), text, replied_to_comment_id=replied_to_comment_id
        )

    # ------------------------------------------------------------------
    # Fetch comment list (pagination)
    # ------------------------------------------------------------------
    def media_comments_page(
        self,
        media_id: str,
        max_id: str = "",
        min_id: str = "",
    ) -> Dict[str, Any]:
        """Fetch one page of comments (raw); returns the whole response dict"""
        media_id = self._media_id_full(media_id)
        params: Dict[str, Any] = {
            "can_support_threading": "true",
            "permalink_enabled": "false",
        }
        if max_id:
            params["max_id"] = max_id
        if min_id:
            params["min_id"] = min_id
        return self.private_request(
            f"media/{media_id}/comments/", params=params
        )

    def media_comments(
        self, media_id: str, amount: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch all comments on a media (iterating pagination by next_max_id/next_min_id)
        amount=0 = fetch all (loop capped at ~50 pages)
        """
        comments: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            page = self.media_comments_page(media_id, max_id=max_id)
            batch = page.get("comments") or []
            comments.extend(batch)
            if amount and len(comments) >= amount:
                break
            # IG uses next_max_id (going older) to page forward
            next_max_id = page.get("next_max_id") or page.get("next_min_id")
            has_more = page.get("has_more_comments") or page.get(
                "has_more_headload_comments"
            )
            if not next_max_id or (has_more is False and not next_max_id):
                break
            if not next_max_id:
                break
            max_id = str(next_max_id)
        if amount:
            return comments[:amount]
        return comments

    # ------------------------------------------------------------------
    # replies (child comments) of a comment
    # ------------------------------------------------------------------
    def comment_replies_page(
        self,
        media_id: str,
        comment_id: str,
        max_id: str = "",
    ) -> Dict[str, Any]:
        """Fetch one page of replies (child comments) (raw)"""
        media_id = self._media_id_full(media_id)
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        return self.private_request(
            f"media/{media_id}/comments/{comment_id}/child_comments/",
            params=params,
        )

    def comment_replies(
        self,
        media_id: str,
        comment_id: str,
        amount: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch all replies of a comment (iterating pagination by next_max_child_cursor)"""
        replies: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            page = self.comment_replies_page(media_id, comment_id, max_id=max_id)
            batch = page.get("child_comments") or page.get("comments") or []
            replies.extend(batch)
            if amount and len(replies) >= amount:
                break
            next_max_id = (
                page.get("next_max_child_cursor")
                or page.get("next_max_id")
                or page.get("next_min_child_cursor")
            )
            if not next_max_id:
                break
            max_id = str(next_max_id)
        if amount:
            return replies[:amount]
        return replies

    # ------------------------------------------------------------------
    # Like / unlike a comment
    # ------------------------------------------------------------------
    def comment_like(self, comment_id: str) -> bool:
        """Like a comment (comment_id = the pk of the comment)"""
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "radio_type": "wifi-none",
            "container_module": "comments_v2",
        }
        result = self.private_request(
            f"media/{comment_id}/comment_like/", data=data
        )
        return result.get("status") == "ok"

    def comment_unlike(self, comment_id: str) -> bool:
        """Unlike a comment"""
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "radio_type": "wifi-none",
            "container_module": "comments_v2",
        }
        result = self.private_request(
            f"media/{comment_id}/comment_unlike/", data=data
        )
        return result.get("status") == "ok"

    def comment_likers(self, comment_id: str) -> List[Dict[str, Any]]:
        """Fetch the list of users who liked a comment (returns a list of user dicts)"""
        result = self.private_request(f"media/{comment_id}/comment_likers/")
        return result.get("users") or []

    # ------------------------------------------------------------------
    # Delete a comment
    # ------------------------------------------------------------------
    def comment_delete(self, media_id: str, comment_id: str) -> bool:
        """Delete a single comment from a media"""
        media_id = self._media_id_full(media_id)
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request(
            f"media/{media_id}/comment/{comment_id}/delete/", data=data
        )
        return result.get("status") == "ok"

    def comment_bulk_delete(
        self, media_id: str, comment_ids: List[Union[str, int]]
    ) -> bool:
        """Delete multiple comments at once (comment_ids = a list of comment pks)"""
        media_id = self._media_id_full(media_id)
        csv = ",".join(str(cid) for cid in comment_ids)
        data: Dict[str, Any] = {
            "comment_ids_to_delete": csv,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request(
            f"media/{media_id}/comment/bulk_delete/", data=data
        )
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # Pin / unpin a comment (best-effort)
    # ------------------------------------------------------------------
    def comment_pin(self, media_id: str, comment_id: str) -> bool:
        """Pin a comment to the top (post owner only)"""
        media_id = self._media_id_full(media_id)
        data: Dict[str, Any] = {
            "comment_id": str(comment_id),
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "container_module": "comments_v2",
        }
        result = self.private_request(
            f"media/{media_id}/comments/{comment_id}/bulk_pin/", data=data
        )
        return result.get("status") == "ok"

    def comment_unpin(self, media_id: str, comment_id: str) -> bool:
        """Unpin a comment"""
        media_id = self._media_id_full(media_id)
        data: Dict[str, Any] = {
            "comment_id": str(comment_id),
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "container_module": "comments_v2",
        }
        result = self.private_request(
            f"media/{media_id}/comments/{comment_id}/bulk_unpin/", data=data
        )
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # Enable/disable comments on a media
    # ------------------------------------------------------------------
    def enable_comments(self, media_id: str) -> bool:
        """Enable commenting on a media"""
        media_id = self._media_id_full(media_id)
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request(
            f"media/{media_id}/enable_comments/", data=data
        )
        return result.get("status") == "ok"

    def disable_comments(self, media_id: str) -> bool:
        """Disable commenting on a media"""
        media_id = self._media_id_full(media_id)
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request(
            f"media/{media_id}/disable_comments/", data=data
        )
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # Single comment info
    # ------------------------------------------------------------------
    def comment_info(
        self, media_id: str, comment_id: str
    ) -> Dict[str, Any]:
        """
        Fetch a single comment from a media's comment list
        (IG has no direct endpoint, so it is searched within the comment pages)
        """
        for comment in self.media_comments(media_id):
            if str(comment.get("pk")) == str(comment_id):
                return comment
        raise ClientNotFoundError(f"Comment not found {comment_id}")
