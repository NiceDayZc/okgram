"""
StoryMixin — stories (stories/reels) + highlights

Covers:
    - reels_tray (the story bar on the feed)
    - fetching a user's stories (via user_id / username)
    - marking stories as seen (media/seen)
    - viewing the list of story viewers + reactions
    - highlights: view tray, info, create, delete, edit media
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import (
    ClientError,
    ClientNotFoundError,
    MediaNotFound,
    UserNotFound,
)


class StoryMixin:
    """Collection of methods for stories and highlights (used as a mixin of InstagramAPI)"""

    # attributes provided by the main client (declared only for type hints)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ==================================================================
    # internal helpers
    # ==================================================================
    def _action_fields(self) -> Dict[str, str]:
        """Standard fields that an IG POST action must include (_uuid/_uid/device_id)"""
        return {
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id) if self.user_id else "",
            "device_id": self.device.device_id,
        }

    @staticmethod
    def _supported_capabilities_param() -> Dict[str, str]:
        """The supported_capabilities_new (json) param required by the viewer endpoint"""
        return {"supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES)}

    # ==================================================================
    # reels tray (the story bar on the feed)
    # ==================================================================
    def reels_tray(self) -> Dict[str, Any]:
        """
        Fetch the reels tray (the story bar at the very top of the feed) — POST like the real app
        Returns the whole dict (has the key 'tray' as a list of reels)
        """
        data = {
            "supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES),
            "reason": "cold_start",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "tray_session_id": utils.generate_uuid(),
            "request_id": utils.generate_uuid(),
            "_uuid": self.device.uuid,
            "page_size": "50",
        }
        result = self.private_request("feed/reels_tray/", data=data)
        return result

    def reels_tray_items(self) -> List[Dict[str, Any]]:
        """Return only the list of items in the reels tray (key 'tray')"""
        tray = self.reels_tray()
        return tray.get("tray", []) or []

    # ==================================================================
    # fetch a user's stories
    # ==================================================================
    def user_stories(self, user_id: Union[int, str]) -> List[Dict[str, Any]]:
        """
        Fetch a single user's stories (items) via feed/reels_media/
        Returns a list of media items (empty if there are no stories)
        """
        uid = str(user_id)
        data = {
            "supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES),
            "user_ids": [uid],
            "source": "reel_feed_timeline",
            "_uuid": self.device.uuid,
        }
        result = self.private_request("feed/reels_media/", data=data)
        reels = result.get("reels", {}) or {}
        reel = reels.get(uid)
        if reel is None:
            # in some cases IG responds with the key as an int
            reel = reels.get(int(uid)) if uid.isdigit() else None
        if not reel:
            return []
        return reel.get("items", []) or []

    def user_stories_reel(self, user_id: Union[int, str]) -> Dict[str, Any]:
        """
        Same as user_stories but returns the user's whole reel dict
        (has items, expiring_at, latest_reel_media, etc.)
        """
        uid = str(user_id)
        data = {
            "supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES),
            "user_ids": [uid],
            "source": "reel_feed_timeline",
            "_uuid": self.device.uuid,
        }
        result = self.private_request("feed/reels_media/", data=data)
        reels = result.get("reels", {}) or {}
        return reels.get(uid) or (reels.get(int(uid)) if uid.isdigit() else {}) or {}

    def users_stories(
        self, user_ids: List[Union[int, str]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetch the stories of multiple users at once
        Returns a dict {user_id(str): [items...]}
        """
        ids = [str(u) for u in user_ids]
        data = {
            "supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES),
            "user_ids": ids,
            "source": "reel_feed_timeline",
            "_uuid": self.device.uuid,
        }
        result = self.private_request("feed/reels_media/", data=data)
        reels = result.get("reels", {}) or {}
        out: Dict[str, List[Dict[str, Any]]] = {}
        for key, reel in reels.items():
            out[str(key)] = (reel or {}).get("items", []) or []
        return out

    def user_story_by_username(self, username: str) -> List[Dict[str, Any]]:
        """
        Fetch a user's stories from a username (resolve to a user_id first)
        Uses self.username_to_user_id if available (from UserMixin), otherwise tries the web api
        """
        uid = self._resolve_user_id(username)
        if not uid:
            raise UserNotFound(f"user '{username}' not found")
        return self.user_stories(uid)

    def _resolve_user_id(self, username: str) -> Optional[str]:
        """Convert username -> user_id, trying methods from other mixins first"""
        username = str(username).lstrip("@")
        # 1) ready-made method from UserMixin
        resolver = getattr(self, "username_to_user_id", None)
        if callable(resolver):
            try:
                uid = resolver(username)
                if uid:
                    return str(uid)
            except ClientError:
                pass
        # 2) the user_info_by_username method
        info_fn = getattr(self, "user_info_by_username", None)
        if callable(info_fn):
            try:
                info = info_fn(username)
                if isinstance(info, dict) and info.get("pk"):
                    return str(info["pk"])
            except ClientError:
                pass
        # 3) fallback: web api
        try:
            result = self.public_request(
                "users/web_profile_info/", params={"username": username}
            )
            user = utils.safe_get(result, "data", "user") or {}
            uid = user.get("id") or user.get("pk")
            if uid:
                return str(uid)
        except ClientError:
            pass
        return None

    # ==================================================================
    # mark stories as seen
    # ==================================================================
    def story_seen(
        self,
        story_items: List[Dict[str, Any]],
        *,
        container_module: str = "feed_timeline",
    ) -> Dict[str, Any]:
        """
        Mark multiple stories as "seen"
        story_items: list of dicts with keys {pk, user_id, taken_at}
        Returns the response dict
        """
        now = utils.now_s()
        reels: Dict[str, List[str]] = {}
        seen_at = now
        for item in story_items:
            # accept input as a str (pk or media_id '<pk>_<uid>'), not just a dict
            if isinstance(item, str):
                item = {"id": item}
            elif not isinstance(item, dict):
                continue
            pk = item.get("pk") or item.get("id")
            uid = item.get("user_id") or item.get("uid")
            taken_at = item.get("taken_at") or now
            if pk is None:
                continue
            # if pk comes in as a full media_id '<pk>_<uid>', extract uid from the suffix when still unknown
            pk_str = str(pk)
            if uid is None and "_" in pk_str:
                uid = pk_str.split("_")[1]
            if uid is None:
                continue
            # strip the user id suffix if pk came in as a full media_id
            pk = pk_str.split("_")[0]
            key = f"{pk}_{uid}"
            reels[key] = [f"{taken_at}_{seen_at}"]
            seen_at += 1
        data = {
            **self._action_fields(),
            "container_module": container_module,
            "live_vods_skipped": {},
            "nuxes_skipped": {},
            "nuxes": {},
            "reels": reels,
            "live_vods": {},
            "reel_media_skipped": {},
        }
        return self.private_request("media/seen/", data=data, params={"reel": "1"})

    def story_seen_one(
        self,
        story_pk: Union[int, str],
        user_id: Union[int, str],
        taken_at: Optional[int] = None,
        *,
        container_module: str = "feed_timeline",
    ) -> Dict[str, Any]:
        """convenience: mark a single story as seen from pk + user_id + taken_at"""
        item = {
            "pk": str(story_pk).split("_")[0],
            "user_id": str(user_id),
            "taken_at": taken_at if taken_at is not None else utils.now_s(),
        }
        return self.story_seen([item], container_module=container_module)

    # ==================================================================
    # viewers / reactions of our own stories
    # ==================================================================
    def story_viewers_page(
        self, story_pk: Union[int, str], max_id: str = ""
    ) -> Dict[str, Any]:
        """
        Fetch the list of story viewers (one page) — GET list_reel_media_viewer
        Returns the whole dict (has keys 'users', 'next_max_id')
        """
        pk = str(story_pk).split("_")[0]
        params: Dict[str, Any] = dict(self._supported_capabilities_param())
        if max_id:
            params["max_id"] = max_id
        return self.private_request(
            f"media/{pk}/list_reel_media_viewer/", params=params
        )

    def story_viewers(
        self, story_pk: Union[int, str], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch the full list of story viewers (paginate via next_max_id)
        amount=0 = fetch everything (loop guarded to ~50 pages)
        """
        users: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            page = self.story_viewers_page(story_pk, max_id=max_id)
            batch = page.get("users", []) or []
            users.extend(batch)
            if amount and len(users) >= amount:
                return users[:amount]
            max_id = page.get("next_max_id") or ""
            if not max_id or not batch:
                break
        return users[:amount] if amount else users

    def story_likers(self, story_pk: Union[int, str]) -> List[Dict[str, Any]]:
        """Fetch the list of people who liked our story (story_likers)"""
        pk = str(story_pk).split("_")[0]
        result = self.private_request(f"media/{pk}/story_likers/")
        return result.get("users", []) or []

    # ==================================================================
    # actions on a story (like / reaction / poll / quiz / slider)
    # ==================================================================
    def story_like(
        self,
        media_id: str,
        *,
        revoke: bool = False,
        container_module: str = "reel_feed_timeline",
    ) -> Dict[str, Any]:
        """Like (or unlike, if revoke=True) a story by its full media_id"""
        media_id = self._full_media_id(media_id)
        pk = utils.media_id_to_pk(media_id)
        data = {
            **self._action_fields(),
            "media_id": media_id,
            "container_module": container_module,
            "radio_type": "wifi-none",
            "tray_session_id": utils.generate_uuid(),
            "viewer_session_id": utils.generate_uuid(),
        }
        endpoint = f"story_interactions/{'unsend' if revoke else 'send'}_story_like/"
        # in case the endpoint is unsupported, fall back to the generic media/{pk}/like/
        try:
            return self.private_request(endpoint, data=data)
        except ClientNotFoundError:
            data["media_id"] = media_id
            verb = "unlike" if revoke else "like"
            return self.private_request(f"media/{pk}/{verb}/", data=data)

    def story_unlike(
        self, media_id: str, *, container_module: str = "reel_feed_timeline"
    ) -> Dict[str, Any]:
        """Unlike a story"""
        return self.story_like(media_id, revoke=True, container_module=container_module)

    def story_vote_poll(
        self, media_id: str, poll_id: Union[int, str], vote: int
    ) -> Dict[str, Any]:
        """Vote on a poll sticker in a story (vote = 0 or 1)"""
        media_id = self._full_media_id(media_id)
        data = {
            **self._action_fields(),
            "container_module": "reel_feed_timeline",
            "radio_type": "wifi-none",
            "vote": str(vote),
        }
        return self.private_request(
            f"media/{media_id}/{poll_id}/story_poll_vote/", data=data
        )

    def story_answer_quiz(
        self, media_id: str, quiz_id: Union[int, str], answer: int
    ) -> Dict[str, Any]:
        """Answer a quiz sticker in a story (answer = index of the choice)"""
        media_id = self._full_media_id(media_id)
        data = {
            **self._action_fields(),
            "container_module": "reel_feed_timeline",
            "radio_type": "wifi-none",
            "answer": str(answer),
        }
        return self.private_request(
            f"media/{media_id}/{quiz_id}/story_quiz_answer/", data=data
        )

    def story_vote_slider(
        self, media_id: str, slider_id: Union[int, str], vote: float
    ) -> Dict[str, Any]:
        """Respond to an emoji slider sticker in a story (vote = 0.0 to 1.0)"""
        media_id = self._full_media_id(media_id)
        data = {
            **self._action_fields(),
            "container_module": "reel_feed_timeline",
            "radio_type": "wifi-none",
            "vote": str(vote),
        }
        return self.private_request(
            f"media/{media_id}/{slider_id}/story_slider_vote/", data=data
        )

    # ==================================================================
    # highlights
    # ==================================================================
    def user_highlights(
        self, user_id: Union[int, str]
    ) -> List[Dict[str, Any]]:
        """
        Fetch a user's highlights tray — GET highlights/<uid>/highlights_tray/
        Returns a list of highlights (key 'tray')
        """
        uid = str(user_id)
        params = self._supported_capabilities_param()
        result = self.private_request(
            f"highlights/{uid}/highlights_tray/", params=params
        )
        return result.get("tray", []) or []

    def user_highlights_by_username(self, username: str) -> List[Dict[str, Any]]:
        """Fetch a user's highlights tray from a username"""
        uid = self._resolve_user_id(username)
        if not uid:
            raise UserNotFound(f"user '{username}' not found")
        return self.user_highlights(uid)

    def highlight_info(
        self, highlight_id: Union[int, str]
    ) -> Dict[str, Any]:
        """
        Fetch the details of a highlight (all items) — POST feed/reels_media/
        highlight_id accepts either '17xxxxx' or 'highlight:17xxxxx'
        Returns the reel dict of that highlight
        """
        hid = self._highlight_pk(highlight_id)
        key = f"highlight:{hid}"
        data = {
            "supported_capabilities_new": utils.json_dumps(config.SUPPORTED_CAPABILITIES),
            "user_ids": [key],
            "source": "reel_feed_timeline",
            "_uuid": self.device.uuid,
        }
        result = self.private_request("feed/reels_media/", data=data)
        reels = result.get("reels", {}) or {}
        reel = reels.get(key) or reels.get(str(hid))
        if not reel:
            raise MediaNotFound(f"highlight {highlight_id} not found")
        return reel

    def highlight_items(
        self, highlight_id: Union[int, str]
    ) -> List[Dict[str, Any]]:
        """Return only the list of media items in a highlight"""
        reel = self.highlight_info(highlight_id)
        return reel.get("items", []) or []

    def highlight_create(
        self,
        title: str,
        media_ids: List[str],
        cover_media_id: str = "",
    ) -> Dict[str, Any]:
        """
        Create a new highlight from existing media (stories) — POST highlights/create_reel/
        title: highlight name (max ~16 characters)
        media_ids: list of full media_ids to put in the highlight
        cover_media_id: media_id to use as the cover (empty = use the first one)
        Returns the response dict (has the 'reel' of the created highlight)
        """
        full_ids = [self._full_media_id(m) for m in media_ids]
        cover_id = self._full_media_id(cover_media_id) if cover_media_id else (
            full_ids[0] if full_ids else ""
        )
        cover = {"media_id": cover_id} if cover_id else {}
        data = {
            "source": "story_viewer_default",
            "creation_id": str(utils.now_ms()),
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id) if self.user_id else "",
            "cover": utils.json_dumps(cover),
            "title": title[:16],
            "media_ids": utils.json_dumps(full_ids),
        }
        return self.private_request("highlights/create_reel/", data=data)

    def highlight_delete(self, highlight_id: Union[int, str]) -> Dict[str, Any]:
        """Delete a highlight — POST highlights/highlight:<id>/delete_reel/"""
        hid = self._highlight_pk(highlight_id)
        data = {
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id) if self.user_id else "",
        }
        return self.private_request(
            f"highlights/highlight:{hid}/delete_reel/", data=data
        )

    def highlight_edit(
        self,
        highlight_id: Union[int, str],
        *,
        title: Optional[str] = None,
        cover_media_id: str = "",
        added_media_ids: Optional[List[str]] = None,
        removed_media_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Edit a highlight (change title/cover/add/remove media) — POST .../edit_reel/
        Provide only the fields you want to change
        """
        hid = self._highlight_pk(highlight_id)
        data: Dict[str, Any] = {
            "source": "story_viewer_default",
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id) if self.user_id else "",
        }
        if title is not None:
            data["title"] = title[:16]
        if cover_media_id:
            data["cover"] = utils.json_dumps(
                {"media_id": self._full_media_id(cover_media_id)}
            )
        if added_media_ids:
            data["added_media_ids"] = utils.json_dumps(
                [self._full_media_id(m) for m in added_media_ids]
            )
        if removed_media_ids:
            data["removed_media_ids"] = utils.json_dumps(
                [self._full_media_id(m) for m in removed_media_ids]
            )
        return self.private_request(
            f"highlights/highlight:{hid}/edit_reel/", data=data
        )

    # ==================================================================
    # id helpers (media_id / highlight id)
    # ==================================================================
    def _full_media_id(self, media_id: Union[int, str]) -> str:
        """
        Return the full media_id form '<pk>_<user_id>'
        If given a bare pk, append the logged-in account's user_id
        """
        s = str(media_id)
        if "_" in s:
            return s
        if self.user_id:
            return utils.pk_with_user_id(s, self.user_id)
        return s

    @staticmethod
    def _highlight_pk(highlight_id: Union[int, str]) -> str:
        """Extract just the highlight's pk number ('highlight:17x' -> '17x')"""
        s = str(highlight_id)
        if s.startswith("highlight:"):
            s = s.split(":", 1)[1]
        return s
