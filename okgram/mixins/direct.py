"""
DirectMixin — all Direct Messages functionality

Covers:
    - Mailbox (inbox / pending inbox) + pagination
    - Reading messages in a thread + pagination
    - Sending messages (text / link / media share / photo) via broadcast
    - Thread management (approve / hide / mute / unmute / add user / mark seen)
    - Recipient search (ranked recipients) and presence status
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Union

from .. import config, utils
from ..exceptions import ClientError, DirectThreadNotFound


class DirectMixin:
    """Collection of methods related to Direct Messages — a mixin with no __init__"""

    # attributes the main client provides (declared for type hints only)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ==================================================================
    # Inbox
    # ==================================================================
    def direct_inbox_page(self, cursor: str = "") -> Dict[str, Any]:
        """
        Fetch one page of the inbox (raw); returns the full dict IG responds with.
        Use cursor (oldest_cursor) to page to the next page.
        """
        params: Dict[str, Any] = {
            "visual_message_return_type": "unseen",
            "persistentBadging": "true",
            "is_prefetching": "false",
            "thread_message_limit": 10,
            "limit": 20,
        }
        if cursor:
            params["cursor"] = cursor
        return self.private_request("direct_v2/inbox/", params=params)

    def direct_threads(
        self, amount: int = 20, thread_message_limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Return a list of threads in the inbox (loops via oldest_cursor until amount is reached).
        amount=0 means fetch all available (loop capped at ~50 pages).
        """
        threads: List[Dict[str, Any]] = []
        cursor = ""
        for _ in range(50):
            result = self.direct_inbox_page(cursor=cursor)
            inbox = result.get("inbox", {}) or {}
            page_threads = inbox.get("threads", []) or []
            threads.extend(page_threads)
            if amount and len(threads) >= amount:
                break
            cursor = inbox.get("oldest_cursor") or ""
            has_older = inbox.get("has_older")
            if not cursor or has_older is False:
                break
        if amount:
            return threads[:amount]
        return threads

    def direct_pending_inbox(self, cursor: str = "") -> Dict[str, Any]:
        """Fetch the pending (request) inbox; returns the raw dict."""
        params: Dict[str, Any] = {
            "visual_message_return_type": "unseen",
            "persistentBadging": "true",
            "is_prefetching": "false",
        }
        if cursor:
            params["cursor"] = cursor
        return self.private_request("direct_v2/pending_inbox/", params=params)

    def direct_pending_threads(self, amount: int = 20) -> List[Dict[str, Any]]:
        """Return a list of pending threads (loops via oldest_cursor)."""
        threads: List[Dict[str, Any]] = []
        cursor = ""
        for _ in range(50):
            result = self.direct_pending_inbox(cursor=cursor)
            inbox = result.get("inbox", {}) or {}
            page_threads = inbox.get("threads", []) or []
            threads.extend(page_threads)
            if amount and len(threads) >= amount:
                break
            cursor = inbox.get("oldest_cursor") or ""
            if not cursor or inbox.get("has_older") is False:
                break
        if amount:
            return threads[:amount]
        return threads

    def direct_pending_count(self) -> int:
        """Number of pending message requests (badge count); returns int."""
        result = self.direct_pending_inbox()
        inbox = result.get("inbox", {}) or {}
        try:
            return int(inbox.get("unseen_count") or 0)
        except (TypeError, ValueError):
            return 0

    # ==================================================================
    # Messages in a thread
    # ==================================================================
    def direct_thread(self, thread_id: str, cursor: str = "") -> Dict[str, Any]:
        """
        Fetch details of one thread (raw); returns the dict ["thread"] section.
        Use cursor (the thread's oldest_cursor) to load older messages.
        """
        params: Dict[str, Any] = {
            "visual_message_return_type": "unseen",
            "direction": "older",
            "limit": 20,
        }
        if cursor:
            params["cursor"] = cursor
        result = self.private_request(
            f"direct_v2/threads/{thread_id}/", params=params
        )
        thread = result.get("thread")
        if thread is None:
            raise DirectThreadNotFound(f"Thread {thread_id} not found")
        return thread

    def direct_messages(
        self, thread_id: str, amount: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Return a list of messages (items) in a thread (loops via oldest_cursor).
        amount=0 = fetch all available (loop capped at ~50 pages).
        """
        items: List[Dict[str, Any]] = []
        cursor = ""
        for _ in range(50):
            thread = self.direct_thread(thread_id, cursor=cursor)
            page_items = thread.get("items", []) or []
            items.extend(page_items)
            if amount and len(items) >= amount:
                break
            cursor = thread.get("oldest_cursor") or ""
            if not cursor or thread.get("has_older") is False:
                break
        if amount:
            return items[:amount]
        return items

    def direct_thread_by_participants(
        self, user_ids: Sequence[Union[int, str]]
    ) -> Dict[str, Any]:
        """
        Find a thread whose participants match the given user_ids (use before sending a message).
        Returns the raw dict (contains keys thread / thread_exists).
        """
        recipient = utils.json_dumps([int(u) for u in user_ids])
        params = {"recipient_users": recipient}
        return self.private_request(
            "direct_v2/threads/get_by_participants/", params=params
        )

    # ==================================================================
    # Sending messages (broadcast)
    # ==================================================================
    def _broadcast(
        self,
        api: str,
        data: Dict[str, Any],
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Central helper for sending every kind of message via broadcast/{api}/.
        Exactly one destination must be provided: thread_ids or user_ids.
        """
        if not thread_ids and not user_ids:
            raise ClientError("Must provide at least one of thread_ids or user_ids")

        token = utils.generate_mutation_token()
        payload: Dict[str, Any] = {
            "action": "send_item",
            "is_shh_mode": "0",
            "send_attribution": "inbox",
            "client_context": token,
            "device_id": self.device.device_id,
            "mutation_token": token,
            "_uuid": self.device.uuid,
            "offline_threading_id": token,
        }
        # destination: if thread_ids is given use thread_ids, otherwise use recipient_users
        if thread_ids:
            payload["thread_ids"] = utils.json_dumps(
                [str(t) for t in thread_ids]
            )
        else:
            payload["recipient_users"] = utils.json_dumps(
                [[int(u) for u in (user_ids or [])]]
            )
        # message-type-specific fields
        payload.update(data)
        return self.private_request(
            f"direct_v2/threads/broadcast/{api}/", data=payload
        )

    def direct_send_text(
        self,
        text: str,
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """Send a text message to a thread or users; returns the result dict."""
        return self._broadcast(
            "text", {"text": text}, thread_ids=thread_ids, user_ids=user_ids
        )

    def direct_send_link(
        self,
        text: str,
        link: str,
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """Send a message containing a link (shows a preview); returns the result dict."""
        data = {
            "link_text": text,
            "link_urls": utils.json_dumps([link]),
        }
        return self._broadcast(
            "link", data, thread_ids=thread_ids, user_ids=user_ids
        )

    def direct_send_media_share(
        self,
        media_id: str,
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
        media_type: str = "1",
    ) -> Dict[str, Any]:
        """Share a post (media) into direct; returns the result dict (media_type 1=photo, 2=video)."""
        data = {
            "media_id": media_id,
            "media_type": media_type,
        }
        return self._broadcast(
            "media_share", data, thread_ids=thread_ids, user_ids=user_ids
        )

    def direct_send_media_share_by_pk(
        self,
        media_pk: Union[int, str],
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
        media_type: str = "1",
    ) -> Dict[str, Any]:
        """convenience: share a post by pk (cannot build the full media_id with the owner's user_id,
        so the pk is sent directly, which IG supports for media_share)."""
        return self.direct_send_media_share(
            str(media_pk),
            thread_ids=thread_ids,
            user_ids=user_ids,
            media_type=media_type,
        )

    def direct_send_photo(
        self,
        path: str,
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Send a photo into direct: rupload first via self.photo_rupload (from UploadMixin),
        then broadcast configure_photo with the resulting upload_id.
        """
        rupload = getattr(self, "photo_rupload", None)
        if rupload is None:
            raise ClientError(
                "UploadMixin.photo_rupload is required to send a photo into direct"
            )
        upload = rupload(path)
        # photo_rupload may return an upload_id (str) or a dict containing upload_id
        if isinstance(upload, dict):
            upload_id = upload.get("upload_id") or upload.get("upload_id_str")
        else:
            upload_id = upload
        if not upload_id:
            raise ClientError("rupload did not return an upload_id")
        data = {
            "allow_full_aspect_ratio": "true",
            "upload_id": str(upload_id),
        }
        return self._broadcast(
            "configure_photo", data, thread_ids=thread_ids, user_ids=user_ids
        )

    def direct_send_hashtag(
        self,
        hashtag: str,
        text: str = "",
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """Share a hashtag into direct; returns the result dict."""
        data = {
            "hashtag": hashtag.lstrip("#"),
            "text": text,
        }
        return self._broadcast(
            "hashtag", data, thread_ids=thread_ids, user_ids=user_ids
        )

    def direct_send_profile(
        self,
        user_id: Union[int, str],
        text: str = "",
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """Share a user profile (profile card) into direct; returns the result dict."""
        data = {
            "profile_user_id": str(user_id),
            "text": text,
        }
        return self._broadcast(
            "profile", data, thread_ids=thread_ids, user_ids=user_ids
        )

    def direct_send_like(
        self,
        thread_ids: Optional[Sequence[Union[int, str]]] = None,
        user_ids: Optional[Sequence[Union[int, str]]] = None,
    ) -> Dict[str, Any]:
        """Send a heart/like (sticker) into direct; returns the result dict."""
        return self._broadcast(
            "like", {}, thread_ids=thread_ids, user_ids=user_ids
        )

    # ==================================================================
    # Message / thread management
    # ==================================================================
    def direct_mark_seen(self, thread_id: str, item_id: str) -> Dict[str, Any]:
        """Mark message item_id in a thread as seen; returns the result dict."""
        data = {
            "thread_id": str(thread_id),
            "action": "mark_seen",
            "item_id": str(item_id),
            "_uuid": self.device.uuid,
        }
        return self.private_request(
            f"direct_v2/threads/{thread_id}/items/{item_id}/seen/", data=data
        )

    def direct_message_delete(
        self, thread_id: str, item_id: str
    ) -> Dict[str, Any]:
        """Delete (unsend) message item_id in a thread; returns the result dict."""
        data = {
            "_uuid": self.device.uuid,
            "is_shh_mode": "0",
        }
        return self.private_request(
            f"direct_v2/threads/{thread_id}/items/{item_id}/delete/", data=data
        )

    def _direct_thread_action(
        self, thread_id: str, action: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """helper: POST a generic action to a thread, e.g. approve/hide/mute/unmute"""
        payload: Dict[str, Any] = {
            "_uuid": self.device.uuid,
        }
        if self.user_id:
            payload["_uid"] = self.user_id
        if data:
            payload.update(data)
        return self.private_request(
            f"direct_v2/threads/{thread_id}/{action}/", data=payload
        )

    def direct_thread_approve(self, thread_id: str) -> Dict[str, Any]:
        """Approve a message request (move from pending into inbox); returns the result dict."""
        return self._direct_thread_action(thread_id, "approve")

    def direct_thread_decline(self, thread_id: str) -> Dict[str, Any]:
        """Decline a message request; returns the result dict."""
        return self._direct_thread_action(thread_id, "decline")

    def direct_thread_hide(self, thread_id: str) -> Dict[str, Any]:
        """Hide/remove a thread from the inbox; returns the result dict."""
        return self._direct_thread_action(thread_id, "hide")

    def direct_thread_mute(self, thread_id: str) -> Dict[str, Any]:
        """Mute notifications for a thread; returns the result dict."""
        return self._direct_thread_action(thread_id, "mute")

    def direct_thread_unmute(self, thread_id: str) -> Dict[str, Any]:
        """Unmute notifications for a thread again; returns the result dict."""
        return self._direct_thread_action(thread_id, "unmute")

    def direct_thread_mute_video_call(self, thread_id: str) -> Dict[str, Any]:
        """Mute video call notifications for a thread; returns the result dict."""
        return self._direct_thread_action(thread_id, "mute_video_call")

    def direct_thread_unmute_video_call(self, thread_id: str) -> Dict[str, Any]:
        """Unmute video call notifications for a thread; returns the result dict."""
        return self._direct_thread_action(thread_id, "unmute_video_call")

    def direct_thread_mark_unread(self, thread_id: str) -> Dict[str, Any]:
        """Mark a thread as unread; returns the result dict."""
        return self._direct_thread_action(thread_id, "mark_unread")

    def direct_thread_add_users(
        self, thread_id: str, user_ids: Sequence[Union[int, str]]
    ) -> Dict[str, Any]:
        """Add members to a group thread; returns the result dict."""
        data = {
            "user_ids": utils.json_dumps([int(u) for u in user_ids]),
        }
        return self._direct_thread_action(thread_id, "add_user", data=data)

    def direct_thread_remove_users(
        self, thread_id: str, user_ids: Sequence[Union[int, str]]
    ) -> Dict[str, Any]:
        """Remove members from a group thread; returns the result dict."""
        data = {
            "user_ids": utils.json_dumps([int(u) for u in user_ids]),
        }
        return self._direct_thread_action(thread_id, "remove_users", data=data)

    def direct_thread_update_title(
        self, thread_id: str, title: str
    ) -> Dict[str, Any]:
        """Rename a group thread; returns the result dict."""
        data = {"title": title}
        return self._direct_thread_action(thread_id, "update_title", data=data)

    def direct_thread_leave(self, thread_id: str) -> Dict[str, Any]:
        """Leave a group thread; returns the result dict."""
        return self._direct_thread_action(thread_id, "leave")

    # ==================================================================
    # Recipient search / status
    # ==================================================================
    def direct_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search recipients (ranked recipients) by query.
        Returns a list of recipients (containing key user or thread).
        """
        params = {
            "mode": "raven",
            "show_threads": "true",
            "query": query,
        }
        result = self.private_request(
            "direct_v2/ranked_recipients/", params=params
        )
        return result.get("ranked_recipients", []) or []

    def direct_ranked_recipients(
        self, mode: str = "raven", show_threads: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch suggested recipients (without a query); returns a list of recipients."""
        params = {
            "mode": mode,
            "show_threads": "true" if show_threads else "false",
        }
        result = self.private_request(
            "direct_v2/ranked_recipients/", params=params
        )
        return result.get("ranked_recipients", []) or []

    def direct_presence(self) -> Dict[str, Any]:
        """Fetch the online status (presence) of people you've talked to; returns a dict."""
        return self.private_request("direct_v2/get_presence/")

    def direct_active_presence(self) -> Dict[str, Any]:
        """Fetch active presence status (a more detailed version); returns a dict."""
        return self.private_request("direct_v2/get_active_presence/")

    def direct_send_typing_indicator(
        self, thread_id: str, activity: int = 1
    ) -> Dict[str, Any]:
        """
        Send a 'typing' status to a thread (activity 1=typing, 0=stop).
        Returns the result dict.
        """
        data = {
            "_uuid": self.device.uuid,
            "activity_status": str(activity),
            "client_context": utils.generate_mutation_token(),
        }
        return self.private_request(
            f"direct_v2/threads/{thread_id}/indicate_activity/", data=data
        )
