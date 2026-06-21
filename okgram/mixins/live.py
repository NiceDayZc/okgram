"""
LiveMixin — Instagram live broadcast

Covers:
    - create/start/end a live (create / start / end)
    - view live info, heartbeat + viewer count, viewer list (viewers)
    - live comments: fetch/post/pin/delete, enable/disable comments
    - live likes (heart)
    - fetch info/comments of an ended live (post-live), fetch comments in chunks
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError


class LiveMixin:
    """Collection of methods related to live broadcasts — used as a mixin of InstagramAPI"""

    # Attributes provided by the main client (declared for type hints only)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ==================================================================
    # internal helpers
    # ==================================================================
    def _action_fields(self) -> Dict[str, str]:
        """Standard fields that IG action POSTs must attach (_uuid/_uid)"""
        return {
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id) if self.user_id else "",
        }

    def _user_breadcrumb(self, text: str) -> str:
        """
        Build the user_breadcrumb value for a live comment
        (mimics the real app's typing behavior — IG uses it for bot detection)
        """
        import base64
        import hashlib
        import hmac

        text = text or ""
        dt = len(text) * 1000  # typing time (simulated)
        ts = utils.now_ms()
        body = f"{len(text)} {dt} {ts} {ts}"
        key = "iN4$aGr0m".encode("utf-8")
        digest = hmac.new(key, body.encode("utf-8"), hashlib.sha256).digest()
        encoded_digest = base64.b64encode(digest).decode("ascii")
        encoded_body = base64.b64encode(body.encode("utf-8")).decode("ascii")
        return f"{encoded_digest}\n{encoded_body}\n"

    # ==================================================================
    # create / start / end a live
    # ==================================================================
    def live_create(
        self,
        preview_width: int = 1080,
        preview_height: int = 1920,
        message: str = "",
    ) -> Dict[str, Any]:
        """
        Create a new live (reserve a channel) — returns the full last_json
        (with broadcast_id and upload_url for the RTMP stream)
        """
        data: Dict[str, Any] = {
            "preview_height": preview_height,
            "preview_width": preview_width,
            "broadcast_message": message,
            "broadcast_type": "RTMP_SWAP_ENABLED",
            "internal_only": "0",
            **self._action_fields(),
        }
        self.private_request("live/create/", data=data)
        return self.last_json

    def live_start(
        self, broadcast_id: Union[str, int], send_notifications: bool = True
    ) -> bool:
        """Start a previously created live (begin pushing the stream, then call this)"""
        data: Dict[str, Any] = {
            "should_send_notifications": int(send_notifications),
            **self._action_fields(),
        }
        result = self.private_request(
            f"live/{broadcast_id}/start/", data=data
        )
        return result.get("status") == "ok"

    def live_end(self, broadcast_id: Union[str, int]) -> bool:
        """End a live (end broadcast)"""
        data: Dict[str, Any] = {
            "end_after_copyright_warning": "false",
            **self._action_fields(),
        }
        result = self.private_request(
            f"live/{broadcast_id}/end_broadcast/", data=data
        )
        return result.get("status") == "ok"

    def live_stop(self, broadcast_id: Union[str, int]) -> bool:
        """Alias for live_end (end a live)"""
        return self.live_end(broadcast_id)

    # ==================================================================
    # live info / heartbeat
    # ==================================================================
    def live_info(self, broadcast_id: Union[str, int]) -> Dict[str, Any]:
        """Fetch current live info (status, broadcaster, viewer count, etc.)"""
        return self.private_request(f"live/{broadcast_id}/info/")

    def live_heartbeat(self, broadcast_id: Union[str, int]) -> Dict[str, Any]:
        """Send a heartbeat + fetch the current viewer count (call periodically during a live)"""
        data: Dict[str, Any] = {
            **self._action_fields(),
            "offset_to_video_start": "0",
        }
        return self.private_request(
            f"live/{broadcast_id}/heartbeat_and_get_viewer_count/", data=data
        )

    def live_viewer_count(self, broadcast_id: Union[str, int]) -> int:
        """Fetch the current viewer count (convenience over live_heartbeat)"""
        result = self.live_heartbeat(broadcast_id)
        count = result.get("viewer_count")
        try:
            return int(count) if count is not None else 0
        except (TypeError, ValueError):
            return 0

    # ==================================================================
    # viewer list
    # ==================================================================
    def live_viewers(
        self, broadcast_id: Union[str, int]
    ) -> List[Dict[str, Any]]:
        """Fetch the current live's viewer list (returns a list of user dicts)"""
        result = self.private_request(
            f"live/{broadcast_id}/get_viewer_list/"
        )
        return result.get("users") or []

    def live_join_requests(
        self, broadcast_id: Union[str, int]
    ) -> List[Dict[str, Any]]:
        """Fetch the list of people requesting to join the live (live with) — returns a list of user dicts"""
        result = self.private_request(
            f"live/{broadcast_id}/get_join_request_counts/"
        )
        return result.get("users") or []

    # ==================================================================
    # live comments
    # ==================================================================
    def live_comments_page(
        self,
        broadcast_id: Union[str, int],
        last_comment_ts: int = 0,
    ) -> Dict[str, Any]:
        """Fetch one page of live comments (raw) — last_comment_ts fetches only new comments"""
        params: Dict[str, Any] = {}
        if last_comment_ts:
            params["last_comment_ts"] = int(last_comment_ts)
        return self.private_request(
            f"live/{broadcast_id}/get_comment/", params=params or None
        )

    def live_comments(
        self,
        broadcast_id: Union[str, int],
        last_comment_ts: int = 0,
    ) -> List[Dict[str, Any]]:
        """Fetch the live's comments (returns a list of comment dicts)"""
        page = self.live_comments_page(broadcast_id, last_comment_ts=last_comment_ts)
        return page.get("comments") or []

    def live_comment(
        self, broadcast_id: Union[str, int], text: str
    ) -> Dict[str, Any]:
        """Post a comment to the live — returns the created comment dict"""
        data: Dict[str, Any] = {
            "user_breadcrumb": self._user_breadcrumb(text),
            "idempotence_token": utils.generate_uuid(),
            "comment_text": text,
            "live_or_vod": "1",
            "offset_to_video_start": "0",
            **self._action_fields(),
        }
        result = self.private_request(
            f"live/{broadcast_id}/comment/", data=data
        )
        return result.get("comment", {})

    def live_pin_comment(
        self, broadcast_id: Union[str, int], comment_id: Union[str, int]
    ) -> bool:
        """Pin a comment to the top of the live (live owner only)"""
        data: Dict[str, Any] = {
            "offset_to_video_start": "0",
            "comment_id": str(comment_id),
            **self._action_fields(),
        }
        result = self.private_request(
            f"live/{broadcast_id}/pin_comment/{comment_id}/", data=data
        )
        return result.get("status") == "ok"

    def live_unpin_comment(
        self, broadcast_id: Union[str, int], comment_id: Union[str, int]
    ) -> bool:
        """Unpin a comment in the live"""
        data: Dict[str, Any] = {
            "offset_to_video_start": "0",
            "comment_id": str(comment_id),
            **self._action_fields(),
        }
        result = self.private_request(
            f"live/{broadcast_id}/unpin_comment/{comment_id}/", data=data
        )
        return result.get("status") == "ok"

    def live_enable_comments(self, broadcast_id: Union[str, int]) -> bool:
        """Enable comments in the live"""
        data: Dict[str, Any] = {**self._action_fields()}
        result = self.private_request(
            f"live/{broadcast_id}/unmute_comment/", data=data
        )
        return result.get("status") == "ok"

    def live_disable_comments(self, broadcast_id: Union[str, int]) -> bool:
        """Disable comments in the live"""
        data: Dict[str, Any] = {**self._action_fields()}
        result = self.private_request(
            f"live/{broadcast_id}/mute_comment/", data=data
        )
        return result.get("status") == "ok"

    # ==================================================================
    # likes (heart) in the live
    # ==================================================================
    def live_like(
        self, broadcast_id: Union[str, int], count: int = 1
    ) -> Dict[str, Any]:
        """Send a like (heart) in the live — count = number of hearts sent"""
        data: Dict[str, Any] = {
            "user_like_count": int(count),
            **self._action_fields(),
        }
        return self.private_request(
            f"live/{broadcast_id}/like/", data=data
        )

    def live_like_count(self, broadcast_id: Union[str, int]) -> Dict[str, Any]:
        """Fetch the live's current like count"""
        return self.private_request(f"live/{broadcast_id}/get_like_count/")

    # ==================================================================
    # ended live info (post-live / replay)
    # ==================================================================
    def live_post_info(
        self, broadcast_id: Union[str, int]
    ) -> Dict[str, Any]:
        """Fetch info for an ended live (post-live broadcast info)"""
        return self.private_request(
            f"live/{broadcast_id}/post_live/info/"
        )

    def live_post_comments_page(
        self,
        broadcast_id: Union[str, int],
        starting_offset: int = 0,
        encoding_tag: str = "instagram_dash_remuxed",
    ) -> Dict[str, Any]:
        """Fetch one page of an ended live's comments (raw) by second offset"""
        params: Dict[str, Any] = {
            "starting_offset": int(starting_offset),
            "encoding_tag": encoding_tag,
        }
        return self.private_request(
            f"live/{broadcast_id}/get_post_live_comments/", params=params
        )

    def live_post_comments(
        self,
        broadcast_id: Union[str, int],
        amount: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all comments of an ended live (paginates by ending_offset)
        amount=0 = fetch all (capped at ~50 pages)
        """
        comments: List[Dict[str, Any]] = []
        offset = 0
        for _ in range(50):
            page = self.live_post_comments_page(
                broadcast_id, starting_offset=offset
            )
            muscle = page.get("comment_muck") or {}
            batch = muscle.get("comments") or page.get("comments") or []
            comments.extend(batch)
            if amount and len(comments) >= amount:
                break
            next_offset = (
                page.get("ending_offset")
                or muscle.get("ending_offset")
            )
            if not next_offset or int(next_offset) <= offset:
                break
            offset = int(next_offset)
        if amount:
            return comments[:amount]
        return comments

    # ==================================================================
    # miscellaneous
    # ==================================================================
    def live_get_final_viewer_list(
        self, broadcast_id: Union[str, int]
    ) -> List[Dict[str, Any]]:
        """Fetch the final viewer list (after the live ends) — returns a list of user dicts"""
        result = self.private_request(
            f"live/{broadcast_id}/get_final_viewer_list/"
        )
        return result.get("users") or []

    def live_wave(
        self, broadcast_id: Union[str, int], viewer_id: Union[str, int]
    ) -> bool:
        """Wave to a viewer in the live"""
        data: Dict[str, Any] = {
            "viewer_id": str(viewer_id),
            **self._action_fields(),
        }
        result = self.private_request(
            f"live/{broadcast_id}/wave/", data=data
        )
        return result.get("status") == "ok"
