"""
UploadMixin — upload media to Instagram (photo / video / album)

This module is the hardest because it must "upload the actual bytes" through the rupload endpoint
(i.instagram.com/rupload_igphoto/... and /rupload_igvideo/...) and then
call media/configure/ to create the real post

Standard steps:
    1) rupload : send the file's bytes to the server and get back an upload_id
    2) configure : bind the upload_id to caption/edits to create the post

Note: reading image size / video duration requires Pillow / ffmpeg-python
If these libraries are missing, pass width/height/duration as parameters yourself
(the methods are best-effort: try to detect first, otherwise use fallback values)
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .. import config, utils
from ..exceptions import (
    ClientError,
    PhotoConfigureError,
    UploadError,
    VideoConfigureError,
)

# Pillow (read image size) — optional
try:
    from PIL import Image  # type: ignore

    HAS_PIL = True
except Exception:  # pragma: no cover
    HAS_PIL = False

# moviepy / ffmpeg (read video metadata) — optional
try:
    from moviepy.editor import VideoFileClip  # type: ignore

    HAS_MOVIEPY = True
except Exception:  # pragma: no cover
    HAS_MOVIEPY = False


PathLike = Union[str, Path]


class UploadMixin:
    """Collection of methods for uploading media (photo / video / album)"""

    # attributes provided by the main client (declared only for type hints)
    user_id: Optional[str]
    last_json: Dict[str, Any]

    # number of retries for video configure (waiting for transcode)
    VIDEO_CONFIGURE_RETRIES: int = 6
    VIDEO_CONFIGURE_DELAY: float = 4.0

    # ==================================================================
    # internal helpers
    # ==================================================================
    def _rupload_headers(self, extra: Dict[str, str]) -> Dict[str, str]:
        """Build the rupload headers using base_headers as the base, then override"""
        headers = dict(self.base_headers)  # type: ignore[attr-defined]
        # rupload does not need these headers (it is octet-stream, not api/v1)
        for key in ("Content-Type", "Accept-Encoding"):
            headers.pop(key, None)
        headers.update(extra)
        return headers

    def _rupload_name(self, upload_id: str) -> str:
        """Build the rupload entity name: '<upload_id>_0_<rand10digits>'"""
        return f"{upload_id}_0_{random.randint(1000000000, 9999999999)}"

    @staticmethod
    def _retry_context() -> str:
        """The standard retry_context required by rupload_params (a json string)"""
        return json.dumps(
            {
                "num_step_auto_retry": 0,
                "num_reupload": 0,
                "num_step_manual_retry": 0,
            }
        )

    @staticmethod
    def _image_size(path: PathLike) -> Tuple[int, int]:
        """Return the image's (width, height) — use Pillow if available, otherwise fall back to 1080x1080"""
        if HAS_PIL:
            try:
                with Image.open(str(path)) as img:
                    return int(img.width), int(img.height)
            except Exception:
                pass
        return 1080, 1080

    @staticmethod
    def _video_meta(path: PathLike) -> Tuple[int, int, int]:
        """
        Return the video's (width, height, duration_ms)
        Use moviepy/ffmpeg if available, otherwise fall back to (720x1280, 0ms)
        """
        if HAS_MOVIEPY:
            try:
                clip = VideoFileClip(str(path))
                try:
                    width, height = int(clip.w), int(clip.h)
                    duration_ms = int((clip.duration or 0) * 1000)
                    return width, height, duration_ms
                finally:
                    clip.close()
            except Exception:
                pass
        return 720, 1280, 0

    def _common_configure_fields(self) -> Dict[str, str]:
        """The standard device fields required by media/configure"""
        return {
            "_uuid": self.device.uuid,  # type: ignore[attr-defined]
            "_uid": str(self.user_id or ""),
            "device_id": self.device.device_id,  # type: ignore[attr-defined]
        }

    def _device_payload(self) -> Dict[str, Any]:
        """The 'device' structure attached by configure (from the device profile)"""
        profile = getattr(self.device, "profile", {})  # type: ignore[attr-defined]
        return {
            "manufacturer": profile.get("manufacturer", "samsung"),
            "model": profile.get("model", "SM-G991B"),
            "android_version": profile.get("android_version", 33),
            "android_release": str(profile.get("android_release", "13")),
        }

    # ==================================================================
    # rupload: photo
    # ==================================================================
    def photo_rupload(
        self,
        path: PathLike,
        upload_id: Optional[str] = None,
        *,
        waterfall_id: Optional[str] = None,
    ) -> str:
        """
        Upload the photo bytes to rupload_igphoto and return the upload_id
        (does not create a post yet — call photo_upload or configure next)
        """
        upload_id = upload_id or str(utils.now_ms())
        name = self._rupload_name(upload_id)

        rupload_params = {
            "retry_context": self._retry_context(),
            "media_type": "1",
            "upload_id": upload_id,
            "xsharing_user_ids": "[]",
            "image_compression": json.dumps(
                {"lib_name": "moz", "lib_version": "3.1.m", "quality": "80"}
            ),
        }

        data = Path(path).read_bytes()
        headers = self._rupload_headers(
            {
                "X-Instagram-Rupload-Params": json.dumps(rupload_params),
                "X-Entity-Type": "image/jpeg",
                "Offset": "0",
                "X-Entity-Name": name,
                "X-Entity-Length": str(len(data)),
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
                "X-Instagram-Rupload-Waterfall-Id": waterfall_id
                or utils.generate_uuid(),
            }
        )
        url = f"https://{config.API_DOMAIN}/rupload_igphoto/{name}"
        try:
            resp = self.session.post(  # type: ignore[attr-defined]
                url, data=data, headers=headers,
                timeout=self.request_timeout,  # type: ignore[attr-defined]
            )
        except Exception as exc:  # network
            raise UploadError(f"photo_rupload network error: {exc}") from exc

        if resp.status_code != 200:
            raise UploadError(
                f"photo_rupload failed [{resp.status_code}]: {resp.text[:300]}",
                response=resp,
                code=resp.status_code,
            )
        try:
            body = resp.json()
            self.last_json = body
        except Exception:
            body = {}
        # IG returns {'upload_id': ...} on success — use the one the server returns if present
        return str(body.get("upload_id") or upload_id)

    # ==================================================================
    # rupload: video
    # ==================================================================
    def video_rupload(
        self,
        path: PathLike,
        upload_id: Optional[str] = None,
        *,
        duration_ms: int = 0,
        width: int = 0,
        height: int = 0,
        for_album: bool = False,
        waterfall_id: Optional[str] = None,
    ) -> Tuple[str, int, int, int]:
        """
        Upload the video bytes to rupload_igvideo and return (upload_id, width, height, duration_ms)
        If width/height/duration are not passed, try to detect them from the file (best-effort)
        """
        upload_id = upload_id or str(utils.now_ms())
        if not (width and height and duration_ms):
            d_w, d_h, d_dur = self._video_meta(path)
            width = width or d_w
            height = height or d_h
            duration_ms = duration_ms or d_dur

        name = self._rupload_name(upload_id)
        rupload_params = {
            "retry_context": self._retry_context(),
            "media_type": "2",
            "upload_id": upload_id,
            "xsharing_user_ids": "[]",
            "upload_media_duration_ms": str(int(duration_ms)),
            "upload_media_width": str(int(width)),
            "upload_media_height": str(int(height)),
        }
        if for_album:
            rupload_params["is_sidecar"] = "1"

        data = Path(path).read_bytes()
        headers = self._rupload_headers(
            {
                "X-Instagram-Rupload-Params": json.dumps(rupload_params),
                "X-Entity-Type": "video/mp4",
                "Offset": "0",
                "X-Entity-Name": name,
                "X-Entity-Length": str(len(data)),
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(data)),
                "X-Instagram-Rupload-Waterfall-Id": waterfall_id
                or utils.generate_uuid(),
            }
        )
        url = f"https://{config.API_DOMAIN}/rupload_igvideo/{name}"
        try:
            resp = self.session.post(  # type: ignore[attr-defined]
                url, data=data, headers=headers,
                timeout=self.request_timeout,  # type: ignore[attr-defined]
            )
        except Exception as exc:
            raise UploadError(f"video_rupload network error: {exc}") from exc

        if resp.status_code != 200:
            raise UploadError(
                f"video_rupload failed [{resp.status_code}]: {resp.text[:300]}",
                response=resp,
                code=resp.status_code,
            )
        try:
            body = resp.json()
            self.last_json = body
        except Exception:
            body = {}
        upload_id = str(body.get("upload_id") or upload_id)
        return upload_id, int(width), int(height), int(duration_ms)

    # ==================================================================
    # configure: single photo
    # ==================================================================
    def photo_configure(
        self,
        upload_id: str,
        caption: str = "",
        *,
        width: int = 0,
        height: int = 0,
        usertags: Optional[List[Dict[str, Any]]] = None,
        location: Optional[Dict[str, Any]] = None,
        disable_comments: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a photo post from the upload_id obtained from photo_rupload (POST media/configure/)
        Returns the dict of the created media
        """
        if not (width and height):
            width = width or 1080
            height = height or 1080

        data: Dict[str, Any] = {
            "upload_id": upload_id,
            "caption": caption,
            "source_type": "4",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "device": self._device_payload(),
            "edits": {
                "crop_original_size": [int(width), int(height)],
                "crop_center": [0.0, 0.0],
                "crop_zoom": 1.0,
            },
            "extra": {"source_width": int(width), "source_height": int(height)},
        }
        data.update(self._common_configure_fields())

        if usertags:
            data["usertags"] = json.dumps({"in": usertags})
        if location:
            data["location"] = json.dumps(location)
            if location.get("lat") is not None:
                data["geotag_enabled"] = "1"
                data["lat"] = str(location["lat"])
                data["lng"] = str(location.get("lng", ""))
        if disable_comments:
            data["disable_comments"] = "1"
        if extra:
            data.update(extra)

        try:
            result = self.private_request("media/configure/", data)  # type: ignore[attr-defined]
        except ClientError as exc:
            raise PhotoConfigureError(
                f"photo configure failed: {exc}"
            ) from exc

        media = result.get("media")
        if not media:
            raise PhotoConfigureError(
                f"photo configure did not return media: {result.get('message', result)}"
            )
        return media

    def photo_upload(
        self,
        path: PathLike,
        caption: str = "",
        *,
        usertags: Optional[List[Dict[str, Any]]] = None,
        location: Optional[Dict[str, Any]] = None,
        disable_comments: bool = False,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        Upload a single photo (rupload + configure) and return the new post's media dict
        Can set caption / usertags / location
        """
        width, height = self._image_size(path)
        upload_id = self.photo_rupload(path)
        return self.photo_configure(
            upload_id,
            caption,
            width=width,
            height=height,
            usertags=usertags,
            location=location,
            disable_comments=disable_comments,
            extra=extra or None,
        )

    # ==================================================================
    # configure: single video (feed video)
    # ==================================================================
    def video_configure(
        self,
        upload_id: str,
        width: int,
        height: int,
        duration_ms: int,
        caption: str = "",
        *,
        usertags: Optional[List[Dict[str, Any]]] = None,
        location: Optional[Dict[str, Any]] = None,
        disable_comments: bool = False,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a feed video post from the upload_id (POST media/configure/?video=1)
        Retries several times because the server must finish transcoding first
        Returns the dict of the created media
        """
        length = round(int(duration_ms) / 1000.0, 3)
        data: Dict[str, Any] = {
            "upload_id": upload_id,
            "caption": caption,
            "source_type": "4",
            "length": length,
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "device": self._device_payload(),
            "clips": [{"length": length, "source_type": "4"}],
            "extra": {"source_width": int(width), "source_height": int(height)},
            "audio_muted": False,
            "poster_frame_index": 0,
            "filter_type": "0",
            "video_result": "",
        }
        data.update(self._common_configure_fields())

        if usertags:
            data["usertags"] = json.dumps({"in": usertags})
        if location:
            data["location"] = json.dumps(location)
        if disable_comments:
            data["disable_comments"] = "1"
        if extra:
            data.update(extra)

        last_exc: Optional[Exception] = None
        for attempt in range(self.VIDEO_CONFIGURE_RETRIES):
            try:
                result = self.private_request(  # type: ignore[attr-defined]
                    "media/configure/", data, params={"video": "1"}
                )
                media = result.get("media")
                if media:
                    return media
                last_exc = VideoConfigureError(
                    f"configure not ready yet: {result.get('message', result)}"
                )
            except ClientError as exc:
                last_exc = exc
            # not ready -> wait for transcode and try again (private_request already throttles
            # but transcode needs extra waiting)
            time.sleep(self.VIDEO_CONFIGURE_DELAY)

        raise VideoConfigureError(
            f"video configure failed after {self.VIDEO_CONFIGURE_RETRIES} retries: "
            f"{last_exc}"
        )

    def video_upload(
        self,
        path: PathLike,
        caption: str = "",
        *,
        thumbnail: Optional[PathLike] = None,
        width: int = 0,
        height: int = 0,
        duration_ms: int = 0,
        usertags: Optional[List[Dict[str, Any]]] = None,
        location: Optional[Dict[str, Any]] = None,
        disable_comments: bool = False,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        Upload one feed video clip: video_rupload + photo_rupload(thumbnail)
        as the cover, then configure (retry waiting for transcode); returns the media dict
        If no thumbnail is passed, the clip itself is used as the cover (IG extracts a frame)
        """
        upload_id, vw, vh, vdur = self.video_rupload(
            path,
            duration_ms=duration_ms,
            width=width,
            height=height,
        )
        # upload the thumbnail as the cover using the same upload_id
        if thumbnail is not None:
            try:
                self.photo_rupload(thumbnail, upload_id=upload_id)
            except UploadError:
                pass
        return self.video_configure(
            upload_id,
            vw,
            vh,
            vdur,
            caption,
            usertags=usertags,
            location=location,
            disable_comments=disable_comments,
            extra=extra or None,
        )

    # ==================================================================
    # album / sidecar (multiple files in a single post)
    # ==================================================================
    def _album_child_metadata(
        self,
        path: PathLike,
        *,
        is_video: bool = False,
    ) -> Dict[str, Any]:
        """
        rupload a single child file (photo or video) and return metadata for children_metadata
        """
        if is_video:
            upload_id, width, height, duration_ms = self.video_rupload(
                path, for_album=True
            )
            length = round(int(duration_ms) / 1000.0, 3)
            return {
                "upload_id": upload_id,
                "timezone_offset": str(config.TIMEZONE_OFFSET),
                "source_type": "4",
                "length": length,
                "clips": [{"length": length, "source_type": "4"}],
                "extra": {"source_width": width, "source_height": height},
                "audio_muted": False,
                "poster_frame_index": 0,
                "filter_type": "0",
                "video_result": "",
                "_uuid": self.device.uuid,  # type: ignore[attr-defined]
            }
        width, height = self._image_size(path)
        upload_id = self.photo_rupload(path)
        return {
            "upload_id": upload_id,
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "source_type": "4",
            "scene_capture_type": "",
            "edits": {
                "crop_original_size": [width, height],
                "crop_center": [0.0, 0.0],
                "crop_zoom": 1.0,
            },
            "extra": {"source_width": width, "source_height": height},
            "_uuid": self.device.uuid,  # type: ignore[attr-defined]
        }

    def album_upload(
        self,
        paths: Sequence[PathLike],
        caption: str = "",
        *,
        video_flags: Optional[Sequence[bool]] = None,
        location: Optional[Dict[str, Any]] = None,
        disable_comments: bool = False,
        **extra: Any,
    ) -> Dict[str, Any]:
        """
        Upload an album (2-10 files) as a single post (carousel/sidecar)
        rupload every file -> POST media/configure_sidecar/
        video_flags: list indicating whether each index is a video (default all photos)
        Returns the album's media dict
        """
        paths = list(paths)
        if not 2 <= len(paths) <= 10:
            raise UploadError("an album must have 2-10 files")
        flags = list(video_flags) if video_flags else [False] * len(paths)
        if len(flags) != len(paths):
            raise UploadError("the number of video_flags does not match the number of files")

        children: List[Dict[str, Any]] = []
        for path, is_video in zip(paths, flags):
            children.append(self._album_child_metadata(path, is_video=is_video))

        data: Dict[str, Any] = {
            "caption": caption,
            "client_sidecar_id": str(utils.now_ms()),
            "children_metadata": children,
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "source_type": "4",
            "device": self._device_payload(),
        }
        data.update(self._common_configure_fields())
        if location:
            data["location"] = json.dumps(location)
        if disable_comments:
            data["disable_comments"] = "1"
        if extra:
            data.update(extra)

        last_exc: Optional[Exception] = None
        for attempt in range(self.VIDEO_CONFIGURE_RETRIES):
            try:
                result = self.private_request(  # type: ignore[attr-defined]
                    "media/configure_sidecar/", data
                )
                media = result.get("media")
                if media:
                    return media
                last_exc = UploadError(
                    f"sidecar configure did not return media: "
                    f"{result.get('message', result)}"
                )
            except ClientError as exc:
                last_exc = exc
            # if the album contains a video, wait for transcode
            if any(flags):
                time.sleep(self.VIDEO_CONFIGURE_DELAY)
            else:
                break

        raise UploadError(f"album configure failed: {last_exc}")

    # ==================================================================
    # story: configure_to_story
    # ==================================================================
    def story_configure(
        self,
        upload_id: str,
        *,
        is_video: bool = False,
        width: int = 0,
        height: int = 0,
        duration_ms: int = 0,
        caption: str = "",
        mentions: Optional[List[Dict[str, Any]]] = None,
        links: Optional[List[Any]] = None,
        hashtags: Optional[List[Any]] = None,
        locations: Optional[List[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a story from the upload_id (POST media/configure_to_story/)
        Supports stickers: mentions (tag people), links, hashtags, locations
        Each sticker is a dict that can specify x,y coordinates (0-1), e.g.
            mentions=[{"user_id": 123, "x": 0.5, "y": 0.5}]
            links=["https://example.com"]  or  [{"url": "...", "x":..,"y":..}]
        Returns the created story's media dict
        """
        now = utils.now_s()
        width = width or 1080
        height = height or 1920
        data: Dict[str, Any] = {
            "upload_id": upload_id,
            "source_type": "4",
            "configure_mode": "1",  # 1 = story/reel
            "caption": caption,
            "client_shared_at": str(now - 5),
            "client_timestamp": str(now),
            "creation_surface": "camera",
            "camera_entry_point": "12",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "device": self._device_payload(),
            "edits": {
                "crop_original_size": [int(width), int(height)],
                "crop_center": [0.0, 0.0],
                "crop_zoom": 1.0,
            },
            "extra": {"source_width": int(width), "source_height": int(height)},
            "allow_multi_configures": "1",
        }
        data.update(self._common_configure_fields())

        if is_video:
            length = round(int(duration_ms) / 1000.0, 3)
            data["length"] = length
            data["clips"] = [{"length": length, "source_type": "4"}]
            data["audio_muted"] = False
            data["poster_frame_index"] = 0
            data["video_result"] = ""
            data["has_original_sound"] = "1"

        sticker_ids: List[str] = []
        if mentions:
            reel_mentions, tap_models = [], []
            for m in mentions:
                uid = str(m.get("user_id") or m.get("pk"))
                x, y = float(m.get("x", 0.5)), float(m.get("y", 0.5))
                w, h = float(m.get("width", 0.5)), float(m.get("height", 0.12))
                base = {
                    "x": x, "y": y, "width": w, "height": h,
                    "rotation": 0.0, "type": "mention", "user_id": uid,
                }
                reel_mentions.append({**base, "z": 0, "is_sticker": True,
                                      "display_type": "mention_username"})
                tap_models.append(base)
            data["reel_mentions"] = json.dumps(reel_mentions)
            data["tap_models"] = json.dumps(tap_models)
            sticker_ids.append("mention_sticker_vibrant")
        if links:
            norm = []
            for ln in links:
                url = ln.get("url") if isinstance(ln, dict) else ln
                norm.append({"webUri": url})
            data["story_cta"] = json.dumps([{"links": norm}])
            sticker_ids.append("link_sticker_default")
        if hashtags:
            tags = []
            for ht in hashtags:
                if isinstance(ht, dict):
                    name = str(ht.get("name", "")).lstrip("#")
                    x, y = float(ht.get("x", 0.5)), float(ht.get("y", 0.5))
                else:
                    name, x, y = str(ht).lstrip("#"), 0.5, 0.5
                tags.append({
                    "x": x, "y": y, "width": 0.6, "height": 0.08,
                    "rotation": 0.0, "tag_name": name, "is_sticker": True,
                    "z": 0, "use_custom_title": False,
                })
            data["story_hashtags"] = json.dumps(tags)
            sticker_ids.append("hashtag_sticker_gradient")
        if locations:
            data["story_locations"] = json.dumps(locations)
            sticker_ids.append("location_sticker_vibrant")
        if sticker_ids:
            data["story_sticker_ids"] = ",".join(sticker_ids)
        if extra:
            data.update(extra)

        last_exc: Optional[Exception] = None
        retries = self.VIDEO_CONFIGURE_RETRIES if is_video else 1
        for _ in range(retries):
            try:
                result = self.private_request(  # type: ignore[attr-defined]
                    "media/configure_to_story/", data
                )
                media = result.get("media")
                if media:
                    return media
                last_exc = PhotoConfigureError(
                    f"story configure did not return media: {result.get('message', result)}"
                )
            except ClientError as exc:
                last_exc = exc
            if is_video:
                time.sleep(self.VIDEO_CONFIGURE_DELAY)
        raise (
            VideoConfigureError if is_video else PhotoConfigureError
        )(f"story configure failed: {last_exc}")

    def photo_upload_to_story(
        self,
        path: PathLike,
        *,
        mentions: Optional[List[Dict[str, Any]]] = None,
        links: Optional[List[Any]] = None,
        hashtags: Optional[List[Any]] = None,
        locations: Optional[List[Dict[str, Any]]] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Upload a photo to a story (rupload + configure_to_story); returns the media dict"""
        width, height = self._image_size(path)
        upload_id = self.photo_rupload(path)
        return self.story_configure(
            upload_id, is_video=False, width=width, height=height,
            mentions=mentions, links=links, hashtags=hashtags,
            locations=locations, extra=extra or None,
        )

    def video_upload_to_story(
        self,
        path: PathLike,
        *,
        thumbnail: Optional[PathLike] = None,
        width: int = 0,
        height: int = 0,
        duration_ms: int = 0,
        mentions: Optional[List[Dict[str, Any]]] = None,
        links: Optional[List[Any]] = None,
        hashtags: Optional[List[Any]] = None,
        locations: Optional[List[Dict[str, Any]]] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """Upload a video to a story (video_rupload + configure_to_story, retry waiting for transcode)"""
        upload_id, vw, vh, vdur = self.video_rupload(
            path, duration_ms=duration_ms, width=width, height=height
        )
        if thumbnail is not None:
            try:
                self.photo_rupload(thumbnail, upload_id=upload_id)
            except UploadError:
                pass
        return self.story_configure(
            upload_id, is_video=True, width=vw, height=vh, duration_ms=vdur,
            mentions=mentions, links=links, hashtags=hashtags,
            locations=locations, extra=extra or None,
        )

    # ==================================================================
    # convenience: change profile picture
    # ==================================================================
    def change_profile_picture(self, path: PathLike) -> Dict[str, Any]:
        """Upload a new profile picture from an image file (rupload + accounts/change_profile_picture/)"""
        upload_id = self.photo_rupload(path)
        data = {
            "upload_id": upload_id,
            "use_fbuploader": "true",
        }
        data.update(self._common_configure_fields())
        result = self.private_request(  # type: ignore[attr-defined]
            "accounts/change_profile_picture/", data
        )
        return result.get("user", result)
