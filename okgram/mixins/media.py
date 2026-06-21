"""
MediaMixin — manage posts (media) on Instagram's private API

Covers: reading post info (info / oembed), converting url<->pk<->code,
like/unlike, save/unsave, archive/unarchive, edit caption, delete,
viewing likers, sending seen, and blocked media

Excludes: comment (in comment.py) and upload/configure (in upload.py)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError, MediaNotFound


class MediaMixin:
    """Contains methods related to posts (media) — a mixin with no __init__"""

    # attributes already present on the main client (declared for type hinting)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _media_id(self, media_id_or_pk: Union[int, str]) -> str:
        """
        Normalize the input into a media_id accepted by IG
        Accepts either a full id ('<pk>_<uid>') or a bare pk (IG accepts a bare pk in info)
        """
        return str(media_id_or_pk)

    @staticmethod
    def media_pk(media_id: Union[int, str]) -> str:
        """Extract the pk from a full media_id '<pk>_<uid>' -> '<pk>'"""
        return utils.media_id_to_pk(media_id)

    # ------------------------------------------------------------------
    # Convert url / code / pk
    # ------------------------------------------------------------------
    def media_pk_from_url(self, url: str) -> str:
        """
        Extract the shortcode from a post url (/p/, /reel/, /tv/) and return the media pk (numeric)
        e.g. 'https://instagram.com/p/CXY.../' -> '2789...'
        """
        code = self.media_code_from_url(url)
        if not code:
            raise ClientError(f"Could not extract code from url: {url}")
        return str(utils.media_code_to_pk(code))

    @staticmethod
    def media_code_from_url(url: str) -> Optional[str]:
        """Extract the shortcode from a post/reel/igtv url; returns None if not found"""
        match = re.search(
            r"(?:instagram\.com|instagr\.am)/(?:p|reel|reels|tv)/([^/?#&]+)",
            str(url),
        )
        if match:
            return match.group(1)
        # in case a code is passed directly (not a full url)
        bare = re.fullmatch(r"[A-Za-z0-9_-]+", str(url).strip("/ "))
        return bare.group(0) if bare else None

    def media_pk_from_code(self, code: str) -> str:
        """Convert shortcode -> media pk (numeric) as a string"""
        return str(utils.media_code_to_pk(code))

    def media_code_from_pk(self, pk: Union[int, str]) -> str:
        """Convert media pk (numeric) -> shortcode"""
        return utils.media_pk_to_code(utils.media_id_to_pk(pk))

    # ------------------------------------------------------------------
    # Read post info
    # ------------------------------------------------------------------
    def media_info(self, media_id: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch the full post info (GET)
        Accepts a full media_id '<pk>_<uid>' or a bare pk -> returns the media dict
        """
        mid = self._media_id(media_id)
        try:
            self.private_request(f"media/{mid}/info/")
        except ClientNotFoundError as exc:
            raise MediaNotFound(
                f"Media not found {mid}", response=getattr(exc, "response", None)
            ) from exc
        items = self.last_json.get("items") or []
        if not items:
            raise MediaNotFound(f"Media not found {mid}")
        return items[0]

    def media_info_by_code(self, code: str) -> Dict[str, Any]:
        """Fetch post info from a shortcode (e.g. in url /p/<code>/)"""
        pk = utils.media_code_to_pk(code)
        return self.media_info(pk)

    def media_info_by_url(self, url: str) -> Dict[str, Any]:
        """Fetch post info from a full post url"""
        pk = self.media_pk_from_url(url)
        return self.media_info(pk)

    def media_oembed(self, url: str) -> Dict[str, Any]:
        """Fetch the oembed of a post from a url (GET) — returns condensed metadata"""
        return self.private_request("oembed/", params={"url": url})

    def media_user(self, media_id: Union[int, str]) -> Dict[str, Any]:
        """Fetch the user (post owner) from the media info"""
        return self.media_info(media_id).get("user", {})

    def media_comment_count(self, media_id: Union[int, str]) -> int:
        """Number of comments on a post (read from media_info)"""
        return int(self.media_info(media_id).get("comment_count", 0) or 0)

    def media_like_count(self, media_id: Union[int, str]) -> int:
        """Number of likes on a post (read from media_info)"""
        return int(self.media_info(media_id).get("like_count", 0) or 0)

    # ------------------------------------------------------------------
    # like / unlike
    # ------------------------------------------------------------------
    def media_like(
        self,
        media_id: Union[int, str],
        *,
        container_module: str = "feed_short_url",
    ) -> bool:
        """Like a post (POST) — returns True if successful"""
        mid = self._media_id(media_id)
        data = {
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "radio_type": "wifi-none",
            "container_module": container_module,
            "device_id": self.device.device_id,
        }
        result = self.private_request(f"media/{mid}/like/", data=data)
        return result.get("status") == "ok"

    def media_unlike(
        self,
        media_id: Union[int, str],
        *,
        container_module: str = "feed_short_url",
    ) -> bool:
        """Unlike a post (POST) — returns True if successful"""
        mid = self._media_id(media_id)
        data = {
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "radio_type": "wifi-none",
            "container_module": container_module,
            "device_id": self.device.device_id,
        }
        result = self.private_request(f"media/{mid}/unlike/", data=data)
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # save / unsave
    # ------------------------------------------------------------------
    def media_save(
        self,
        media_id: Union[int, str],
        collection_ids: Union[str, List[Union[int, str]]] = "",
    ) -> bool:
        """
        Save a post (POST) to saved or the specified collection
        collection_ids: a list of ids or a comma-separated string — returns True if successful
        """
        mid = self._media_id(media_id)
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "radio_type": "wifi-none",
            "device_id": self.device.device_id,
        }
        if collection_ids:
            if isinstance(collection_ids, (list, tuple)):
                ids = ",".join(str(c) for c in collection_ids)
            else:
                ids = str(collection_ids)
            data["added_collection_ids"] = f"[{ids}]" if "[" not in ids else ids
        result = self.private_request(f"media/{mid}/save/", data=data)
        return result.get("status") == "ok"

    def media_unsave(
        self,
        media_id: Union[int, str],
        collection_ids: Union[str, List[Union[int, str]]] = "",
    ) -> bool:
        """Unsave a post (POST) — returns True if successful"""
        mid = self._media_id(media_id)
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "radio_type": "wifi-none",
            "device_id": self.device.device_id,
        }
        if collection_ids:
            if isinstance(collection_ids, (list, tuple)):
                ids = ",".join(str(c) for c in collection_ids)
            else:
                ids = str(collection_ids)
            data["removed_collection_ids"] = f"[{ids}]" if "[" not in ids else ids
        result = self.private_request(f"media/{mid}/unsave/", data=data)
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # archive / unarchive (only_me)
    # ------------------------------------------------------------------
    def media_archive(
        self, media_id: Union[int, str], media_type: int = 1
    ) -> bool:
        """Archive a post (only_me) (POST) — returns True if successful"""
        mid = self._media_id(media_id)
        data = {
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        result = self.private_request(
            f"media/{mid}/only_me/", data=data, params={"media_type": media_type}
        )
        return result.get("status") == "ok"

    def media_unarchive(
        self, media_id: Union[int, str], media_type: int = 1
    ) -> bool:
        """Unarchive a post (undo only_me) (POST) — returns True if successful"""
        mid = self._media_id(media_id)
        data = {
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        result = self.private_request(
            f"media/{mid}/undo_only_me/",
            data=data,
            params={"media_type": media_type},
        )
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # edit / delete
    # ------------------------------------------------------------------
    def media_edit(
        self,
        media_id: Union[int, str],
        caption: str,
        *,
        usertags: Optional[List[Dict[str, Any]]] = None,
        location: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Edit the caption (and usertags/location if specified) of a post (POST)
        Returns the updated media dict
        """
        mid = self._media_id(media_id)
        data: Dict[str, Any] = {
            "caption_text": caption,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        if usertags is not None:
            data["usertags"] = utils.json_dumps({"in": usertags})
        if location is not None:
            data["location"] = utils.json_dumps(location)
        self.private_request(f"media/{mid}/edit_media/", data=data)
        items = self.last_json.get("media") or self.last_json.get("items")
        if isinstance(items, list) and items:
            return items[0]
        return self.last_json.get("media", self.last_json)

    def media_delete(
        self, media_id: Union[int, str], media_type: int = 1
    ) -> bool:
        """Delete a post (POST) — media_type: 1=photo, 2=video — returns True if successful"""
        mid = self._media_id(media_id)
        data = {
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        result = self.private_request(
            f"media/{mid}/delete/", data=data, params={"media_type": media_type}
        )
        return result.get("did_delete", result.get("status") == "ok")

    # ------------------------------------------------------------------
    # likers
    # ------------------------------------------------------------------
    def media_likers(self, media_id: Union[int, str]) -> List[Dict[str, Any]]:
        """Fetch the list of users who liked a post (GET) — returns a list of user dicts"""
        mid = self._media_id(media_id)
        result = self.private_request(f"media/{mid}/likers/")
        return result.get("users", [])

    def media_comment_likers(
        self, comment_id: Union[int, str]
    ) -> List[Dict[str, Any]]:
        """Fetch the list of users who liked a comment (GET) — returns a list of user dicts"""
        cid = str(comment_id)
        result = self.private_request(f"media/{cid}/comment_likers/")
        return result.get("users", [])

    # ------------------------------------------------------------------
    # seen (best-effort)
    # ------------------------------------------------------------------
    def media_seen(
        self,
        media_ids: List[Union[int, str]],
        *,
        skipped: bool = False,
    ) -> bool:
        """
        Send the 'seen' status for a list of media (POST, best-effort)
        media_ids: a list of full media_ids — returns True if successful
        """
        reels: Dict[str, List[str]] = {}
        now = str(utils.now_s())
        for mid in media_ids:
            mid_s = self._media_id(mid)
            pk = utils.media_id_to_pk(mid_s)
            # value format: ["<media_id>_<author_id>", "<seen_ts>_<seen_ts>"]
            reels[str(pk)] = [f"{mid_s}", f"{now}_{now}"]
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "container_module": "feed_timeline",
            "reels": reels,
            "live_vods": {},
            "nuxes": {},
        }
        if skipped:
            data["reel_media_skipped"] = reels
        result = self.private_request("media/seen/", data=data)
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # blocked
    # ------------------------------------------------------------------
    def media_blocked(self) -> Dict[str, Any]:
        """Fetch the list of blocked/restricted media (GET)"""
        return self.private_request("media/blocked/")

    # ------------------------------------------------------------------
    # permalink
    # ------------------------------------------------------------------
    def media_permalink(self, media_id: Union[int, str]) -> str:
        """Fetch the permalink (url) of a post (GET)"""
        mid = self._media_id(media_id)
        result = self.private_request(f"media/{mid}/permalink/")
        return result.get("permalink", "")

    # ------------------------------------------------------------------
    # n_likes (toggle based on the current status)
    # ------------------------------------------------------------------
    def media_like_toggle(self, media_id: Union[int, str]) -> bool:
        """
        Toggle the like status: if not liked -> like, if liked -> unlike
        Returns True = the status after toggling is 'liked'
        """
        info = self.media_info(media_id)
        if info.get("has_liked"):
            self.media_unlike(media_id)
            return False
        self.media_like(media_id)
        return True
