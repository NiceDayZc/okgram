"""
ClipsMixin — collection of Reels (clips) and IGTV methods for the Instagram Private API

Covers:
    - fetching a user's Reels (clips/user/) one page at a time and via paging loops
    - the suggested Reels feed (clips/discover/) and clips feeds by user/audio/hashtag
    - liking/viewing/sharing a reel and configuring a reel upload (media/configure_to_clips/)
    - searching for audio/music (music/search/) to use in a reel
    - IGTV: fetching channels (igtv) and configuring IGTV uploads (alias of the video flow)

Note: uploading the actual video bytes is done in UploadMixin (upload.py); methods here
take an already-uploaded upload_id to configure further, or call the video flow via getattr
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError, MediaNotFound


class ClipsMixin:
    """Collection of methods for Reels (clips) and IGTV (no __init__ because it is a mixin)"""

    # attributes already fully provided by the main client (declared only for type hints)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _media_id(self, media_id: Union[str, int]) -> str:
        """Return the full media_id form '<pk>_<userid>'; if given a bare pk, append the user id"""
        media_id = str(media_id)
        if "_" in media_id:
            return media_id
        # only got a pk -> bind to the current user if known (guards against '<pk>_None')
        if self.user_id:
            return utils.pk_with_user_id(media_id, self.user_id)
        return media_id

    @staticmethod
    def _extract_upload_id(result: Any) -> str:
        """Extract upload_id from any form of rupload result:
        video_rupload -> tuple (upload_id, w, h, dur) ; photo_rupload -> str ; possibly a dict"""
        if isinstance(result, (tuple, list)):
            return str(result[0]) if result else ""
        if isinstance(result, dict):
            return str(
                result.get("upload_id")
                or (result.get("media") or {}).get("upload_id")
                or ""
            )
        return str(result) if result else ""

    def _upload_cover(self, thumbnail: Optional[str], upload_id: str) -> None:
        """Upload the video's cover image using the same upload_id, best-effort"""
        if not thumbnail:
            return
        pr = getattr(self, "photo_rupload", None)
        if pr is None:
            return
        try:
            pr(thumbnail, upload_id=upload_id)
        except Exception:  # noqa - a failed cover should not fail the video upload
            pass

    @staticmethod
    def _extract_clip_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract the list of media dicts from the various clips endpoint response shapes"""
        items: List[Dict[str, Any]] = []
        # clips/user/ shape: items = [{media: {...}}, ...]
        for entry in data.get("items") or []:
            if isinstance(entry, dict) and "media" in entry:
                items.append(entry["media"])
            elif isinstance(entry, dict):
                items.append(entry)
        # clips/discover/ shape: reels_media / clips, etc.
        if not items:
            for entry in data.get("clips") or []:
                if isinstance(entry, dict) and "media" in entry:
                    items.append(entry["media"])
                elif isinstance(entry, dict):
                    items.append(entry)
        return items

    @staticmethod
    def _next_max_id(data: Dict[str, Any]) -> str:
        """Extract the next-page cursor from the response (supports several field names)"""
        paging = data.get("paging_info") or {}
        return (
            paging.get("max_id")
            or data.get("next_max_id")
            or data.get("max_id")
            or data.get("next_cursor")
            or ""
        )

    @staticmethod
    def _has_more(data: Dict[str, Any]) -> bool:
        """Check whether there is a next page"""
        paging = data.get("paging_info") or {}
        if "more_available" in paging:
            return bool(paging.get("more_available"))
        if "more_available" in data:
            return bool(data.get("more_available"))
        return True

    # ------------------------------------------------------------------
    # a user's Reels (clips/user/)
    # ------------------------------------------------------------------
    def user_clips_page(
        self, user_id: Union[str, int], max_id: str = ""
    ) -> Dict[str, Any]:
        """Fetch one page of a user's Reels (POST clips/user/); returns the raw dict from IG"""
        data: Dict[str, Any] = {
            "target_user_id": str(user_id),
            "page_size": 12,
            "include_feed_video": "true",
            "_uuid": self.device.uuid,
        }
        if max_id:
            data["max_id"] = max_id
        return self.private_request("clips/user/", data)

    def user_clips(
        self, user_id: Union[str, int], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch all of a user's Reels (paginate via paging_info.max_id); amount=0=all"""
        items: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):  # guard against an endless loop at ~50 pages
            data = self.user_clips_page(user_id, max_id)
            page_items = self._extract_clip_items(data)
            items.extend(page_items)
            if amount and len(items) >= amount:
                return items[:amount]
            next_id = self._next_max_id(data)
            if not next_id or not self._has_more(data) or not page_items:
                break
            max_id = next_id
        return items[:amount] if amount else items

    # ------------------------------------------------------------------
    # suggested Reels (clips/discover/)
    # ------------------------------------------------------------------
    def clips_discover_page(self, max_id: str = "") -> Dict[str, Any]:
        """Fetch one page of the suggested Reels feed (POST clips/discover/); returns the raw dict"""
        data: Dict[str, Any] = {
            "surface": "clips_tab",
            "is_charging": "0",
            "is_dark_mode": "1",
            "container_module": "clips_viewer_clips_tab",
            "_uuid": self.device.uuid,
        }
        if max_id:
            data["max_id"] = max_id
        return self.private_request("clips/discover/", data)

    def clips_discover(self, amount: int = 0) -> List[Dict[str, Any]]:
        """Fetch suggested Reels (best-effort, paginated); amount=0=as many as IG gives in ~50 pages"""
        items: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            data = self.clips_discover_page(max_id)
            page_items = self._extract_clip_items(data)
            items.extend(page_items)
            if amount and len(items) >= amount:
                return items[:amount]
            next_id = self._next_max_id(data)
            if not next_id or not page_items:
                break
            max_id = next_id
        return items[:amount] if amount else items

    # ------------------------------------------------------------------
    # Reels by audio/music (clips/music/)
    # ------------------------------------------------------------------
    def clips_by_music_page(
        self, music_id: Union[str, int], max_id: str = ""
    ) -> Dict[str, Any]:
        """Fetch one page of Reels using the same audio/music (POST clips/music/); returns the raw dict"""
        data: Dict[str, Any] = {
            "audio_cluster_id": str(music_id),
            "music_canonical_id": str(music_id),
            "_uuid": self.device.uuid,
        }
        if max_id:
            data["max_id"] = max_id
        return self.private_request("clips/music/", data)

    def clips_by_music(
        self, music_id: Union[str, int], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch all Reels using the audio/music music_id (paginated); amount=0=all"""
        items: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            data = self.clips_by_music_page(music_id, max_id)
            page_items = self._extract_clip_items(data)
            items.extend(page_items)
            if amount and len(items) >= amount:
                return items[:amount]
            next_id = self._next_max_id(data)
            if not next_id or not page_items:
                break
            max_id = next_id
        return items[:amount] if amount else items

    # ------------------------------------------------------------------
    # reel actions: view / like / share
    # ------------------------------------------------------------------
    def clip_info(self, media_id: Union[str, int]) -> Dict[str, Any]:
        """Fetch a single reel/media's info (GET media/<id>/info/); returns the media dict"""
        mid = self._media_id(media_id)
        result = self.private_request(f"media/{mid}/info/")
        items = result.get("items") or []
        if not items:
            raise MediaNotFound(f"reel {mid} not found", **result)
        return items[0]

    def clip_info_by_pk(self, pk: Union[str, int]) -> Dict[str, Any]:
        """convenience: fetch a reel's info from a bare pk (binds the current user id)"""
        return self.clip_info(self._media_id(pk))

    def clip_like(
        self, media_id: Union[str, int], *, revert: bool = False
    ) -> bool:
        """Like a reel (POST media/<id>/like/); revert=True to unlike"""
        mid = self._media_id(media_id)
        action = "unlike" if revert else "like"
        data: Dict[str, Any] = {
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "radio_type": "wifi-none",
            "container_module": "clips_viewer_clips_tab",
        }
        result = self.private_request(f"media/{mid}/{action}/", data)
        return result.get("status") == "ok"

    def clip_unlike(self, media_id: Union[str, int]) -> bool:
        """Unlike a reel (POST media/<id>/unlike/)"""
        return self.clip_like(media_id, revert=True)

    def clip_like_by_pk(self, pk: Union[str, int]) -> bool:
        """convenience: like a reel from a bare pk"""
        return self.clip_like(self._media_id(pk))

    def clip_seen(
        self, media_id: Union[str, int], *, view_duration: float = 5.0
    ) -> bool:
        """Mark a reel as viewed (POST clips/item/seen/), mimicking app behavior"""
        mid = self._media_id(media_id)
        pk = utils.media_id_to_pk(mid)
        now = utils.now_s()
        impression = {
            mid: {
                "media_id": mid,
                "client_time": now,
                "media_pk": pk,
                "view_duration": view_duration,
            }
        }
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "container_module": "clips_viewer_clips_tab",
            "impressions": utils.json_dumps(impression),
            "nuxes": "{}",
            "client_time": str(now),
        }
        try:
            result = self.private_request("clips/item/seen/", data)
        except ClientNotFoundError:
            # some versions use media/seen/ instead
            result = self.private_request("media/seen/", data)
        return result.get("status") == "ok"

    def clip_comment(
        self, media_id: Union[str, int], text: str
    ) -> Dict[str, Any]:
        """Comment on a reel (POST media/<id>/comment/); returns the comment dict"""
        mid = self._media_id(media_id)
        data: Dict[str, Any] = {
            "comment_text": text,
            "media_id": mid,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "radio_type": "wifi-none",
            "container_module": "clips_viewer_clips_tab",
            "idempotence_token": utils.generate_uuid(),
        }
        result = self.private_request(f"media/{mid}/comment/", data)
        return result.get("comment", result)

    # ------------------------------------------------------------------
    # configure a reel upload
    # ------------------------------------------------------------------
    def clip_configure(
        self,
        upload_id: str,
        caption: str = "",
        *,
        width: int = 720,
        height: int = 1280,
        thumbnail_offset_ms: int = 0,
        usertags: Optional[List[Dict[str, Any]]] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Configure a reel whose bytes are already uploaded (POST media/configure_to_clips/)
        Takes an upload_id from UploadMixin; returns the posted media dict
        """
        data: Dict[str, Any] = {
            "upload_id": str(upload_id),
            "caption": caption,
            "clips_share_preview_to_feed": "1",
            "disable_comments": "0",
            "source_type": "4",
            "device_id": self.device.device_id,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "creation_logger_session_id": utils.generate_uuid(),
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "client_timestamp": str(utils.now_s()),
            "audio_muted": False,
            "poster_frame_index": 0,
            "clips_audio_metadata": {},
            "extra": {"source_width": width, "source_height": height},
            "device": self.device.payload_fields(),
            "length": 0.0,
            "clips": [{"length": 0.0, "source_type": "4"}],
        }
        if thumbnail_offset_ms:
            data["video_subtitles_enabled"] = "0"
            data["poster_frame_index"] = 0
        if usertags:
            data["usertags"] = utils.json_dumps({"in": usertags})
        if extra_data:
            data.update(extra_data)
        return self.private_request("media/configure_to_clips/", data)

    def clip_upload(
        self,
        path: str,
        caption: str = "",
        *,
        thumbnail: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        End-to-end reel upload: call the video upload flow in UploadMixin via getattr
        then configure_to_clips; returns the posted media dict
        """
        rupload = getattr(self, "video_rupload", None) or getattr(
            self, "upload_video", None
        )
        if rupload is None:
            raise ClientError(
                "video upload method (video_rupload/upload_video) not found in UploadMixin"
            )
        # video_rupload returns a tuple (upload_id, w, h, dur) — do not pass thumbnail into rupload
        upload_result = rupload(path)
        upload_id = self._extract_upload_id(upload_result)
        if not upload_id:
            raise ClientError("video upload failed — no upload_id")
        self._upload_cover(thumbnail, upload_id)

        return self.clip_configure(upload_id, caption, extra_data=extra or None)

    # ------------------------------------------------------------------
    # search audio / music for making a reel
    # ------------------------------------------------------------------
    def music_search(
        self, query: str, *, max_id: str = ""
    ) -> List[Dict[str, Any]]:
        """Search audio/music for making a reel (GET music/search/); returns a list of track dicts"""
        params: Dict[str, Any] = {
            "query": query,
            "browse_session_id": utils.generate_uuid(),
            "product": "clips_camera_format",
        }
        if max_id:
            params["max_id"] = max_id
        result = self.private_request("music/search/", params=params)
        # common shapes: items[].track / metadata.dynamic_sections / audio_assets
        tracks: List[Dict[str, Any]] = []
        for item in result.get("items") or []:
            if isinstance(item, dict) and "track" in item:
                tracks.append(item["track"])
            elif isinstance(item, dict):
                tracks.append(item)
        if not tracks:
            meta = result.get("metadata") or {}
            for section in meta.get("dynamic_sections") or []:
                for track in (section.get("layout_content") or {}).get(
                    "tracks", []
                ):
                    tracks.append(track)
        return tracks

    def music_by_id(self, music_id: Union[str, int]) -> Dict[str, Any]:
        """Fetch audio/music details from an id (POST music/audio_by_canonical_id/)"""
        data: Dict[str, Any] = {
            "audio_cluster_ids": utils.json_dumps([str(music_id)]),
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        result = self.private_request("music/audio_by_canonical_id/", data)
        metadata = result.get("metadata") or result.get("audio") or {}
        return metadata if isinstance(metadata, dict) else result

    # ------------------------------------------------------------------
    # IGTV (shares the video flow with feed; not covered in depth)
    # ------------------------------------------------------------------
    def igtv_channel(
        self, user_id: Union[str, int], max_id: str = ""
    ) -> Dict[str, Any]:
        """Fetch one page of a user's IGTV channel (POST igtv/channel/); returns the raw dict"""
        data: Dict[str, Any] = {
            "id": f"user_{user_id}",
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
        }
        if max_id:
            data["max_id"] = max_id
        return self.private_request("igtv/channel/", data)

    def igtv_videos(
        self, user_id: Union[str, int], amount: int = 0
    ) -> List[Dict[str, Any]]:
        """Fetch all of a user's IGTV videos (paginated); amount=0=all"""
        items: List[Dict[str, Any]] = []
        max_id = ""
        for _ in range(50):
            data = self.igtv_channel(user_id, max_id)
            page_items = self._extract_clip_items(data)
            items.extend(page_items)
            if amount and len(items) >= amount:
                return items[:amount]
            next_id = self._next_max_id(data)
            if not next_id or not page_items:
                break
            max_id = next_id
        return items[:amount] if amount else items

    def igtv_configure(
        self,
        upload_id: str,
        title: str = "",
        caption: str = "",
        *,
        width: int = 720,
        height: int = 1280,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Configure an IGTV video whose bytes are already uploaded (POST media/configure_to_igtv/)"""
        data: Dict[str, Any] = {
            "upload_id": str(upload_id),
            "title": title,
            "caption": caption,
            "igtv_share_preview_to_feed": "1",
            "source_type": "4",
            "device_id": self.device.device_id,
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "extra": {"source_width": width, "source_height": height},
            "device": self.device.payload_fields(),
            "length": 0.0,
            "clips": [{"length": 0.0, "source_type": "4"}],
            "poster_frame_index": 0,
            "audio_muted": False,
        }
        if extra_data:
            data.update(extra_data)
        return self.private_request("media/configure_to_igtv/", data)

    def igtv_upload(
        self,
        path: str,
        title: str = "",
        caption: str = "",
        *,
        thumbnail: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """End-to-end IGTV upload (alias of the video flow): upload bytes then configure_to_igtv"""
        rupload = getattr(self, "video_rupload", None) or getattr(
            self, "upload_video", None
        )
        if rupload is None:
            raise ClientError(
                "video upload method (video_rupload/upload_video) not found in UploadMixin"
            )
        upload_result = rupload(path)
        upload_id = self._extract_upload_id(upload_result)
        if not upload_id:
            raise ClientError("IGTV video upload failed — no upload_id")
        self._upload_cover(thumbnail, upload_id)
        return self.igtv_configure(
            upload_id, title, caption, extra_data=extra or None
        )
