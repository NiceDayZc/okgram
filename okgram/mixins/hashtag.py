"""
HashtagMixin — methods related to hashtags (#tag)

Covers: viewing hashtag info, fetching top/recent posts, following/unfollowing hashtags,
hashtag stories, and the list of hashtags a user follows.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError, HashtagNotFound

# Maximum number of pages to loop, to prevent an infinite loop when IG returns next ids endlessly
_MAX_PAGES = 50


class HashtagMixin:
    """Collection of all hashtag-related methods (a mixin — no __init__)"""

    # these attributes are set by the main client (see type hints for clarity)
    user_id: Optional[str]
    last_json: Dict[str, Any]
    device: Any

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_name(name: str) -> str:
        """Strip '#' and whitespace from a hashtag name, then lowercase it"""
        return str(name).lstrip("#").strip()

    @staticmethod
    def _extract_section_medias(sections: List[dict]) -> List[dict]:
        """Extract media dicts from the sections[].layout_content.medias[].media structure"""
        medias: List[dict] = []
        for section in sections or []:
            layout = (section or {}).get("layout_content") or {}
            # main structure: layout_content.medias[].media
            for item in layout.get("medias") or []:
                media = (item or {}).get("media")
                if media:
                    medias.append(media)
            # some pages use one_by_two_item / fill_items for explore-style layouts
            for key in ("one_by_two_item", "fill_items"):
                block = layout.get(key)
                if isinstance(block, dict):
                    for item in (block.get("clips") or {}).get("items") or []:
                        media = (item or {}).get("media")
                        if media:
                            medias.append(media)
                elif isinstance(block, list):
                    for item in block:
                        media = (item or {}).get("media")
                        if media:
                            medias.append(media)
        return medias

    # ------------------------------------------------------------------
    # Hashtag info
    # ------------------------------------------------------------------
    def hashtag_info(self, name: str) -> Dict[str, Any]:
        """Fetch basic info about a hashtag (post count, id, follow status, etc.)"""
        name = self._clean_name(name)
        try:
            result = self.private_request(f"tags/{name}/info/")
        except ClientNotFoundError as exc:
            raise HashtagNotFound(f"Hashtag #{name} not found", **exc.extra) from exc
        return result

    def hashtag_info_a1(self, name: str) -> Dict[str, Any]:
        """Fetch hashtag info via the web public API (fallback when not logged in)"""
        name = self._clean_name(name)
        data = self.public_request(
            f"explore/tags/{name}/", params={"__a": "1", "__d": "dis"}
        )
        return (data.get("graphql") or {}).get("hashtag") or data

    def hashtag_related(self, name: str) -> List[dict]:
        """Fetch the list of related hashtags (best-effort — some accounts may have no data)"""
        name = self._clean_name(name)
        try:
            result = self.private_request(f"tags/{name}/related/")
        except ClientError:
            return []
        related = result.get("related") or []
        return [r for r in related if isinstance(r, dict)]

    # ------------------------------------------------------------------
    # Posts in a hashtag (sections: top / recent)
    # ------------------------------------------------------------------
    def hashtag_sections_page(
        self,
        name: str,
        tab: str = "top",
        max_id: str = "",
        page: Union[str, int] = "",
        next_media_ids: Optional[List[Union[str, int]]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch one page of hashtag sections (raw) for tab='top' or 'recent'.
        Returns the raw dict from IG (contains sections, next_max_id, more_available, next_page, etc.)
        """
        name = self._clean_name(name)
        data: Dict[str, Any] = {
            "_csrftoken": getattr(self, "csrftoken", ""),
            "_uuid": self.device.uuid,
            "supported_tabs": utils.json_dumps(["top", "recent"]),
            "include_persistent": "true",
            "tab": tab,
        }
        if max_id:
            data["max_id"] = max_id
        if page != "" and page is not None:
            data["page"] = str(page)
        if next_media_ids:
            data["next_media_ids"] = utils.json_dumps(
                [str(m) for m in next_media_ids]
            )
        try:
            return self.private_request(f"tags/{name}/sections/", data)
        except ClientNotFoundError as exc:
            raise HashtagNotFound(f"Hashtag #{name} not found", **exc.extra) from exc

    def hashtag_medias_page(
        self, name: str, tab: str = "top", amount: int = 27
    ) -> List[dict]:
        """
        Loop over hashtag sections for the given tab and return a list of media dicts.
        (Shared method used by both top and recent.)
        """
        name = self._clean_name(name)
        medias: List[dict] = []
        max_id = ""
        page: Union[str, int] = ""
        next_media_ids: Optional[List[Union[str, int]]] = None

        for _ in range(_MAX_PAGES):
            result = self.hashtag_sections_page(
                name, tab=tab, max_id=max_id, page=page,
                next_media_ids=next_media_ids,
            )
            sections = result.get("sections") or []
            medias.extend(self._extract_section_medias(sections))

            if amount and len(medias) >= amount:
                break
            if not result.get("more_available"):
                break
            next_max_id = result.get("next_max_id")
            if not next_max_id or next_max_id == max_id:
                break
            max_id = next_max_id
            page = result.get("next_page") or page
            next_media_ids = result.get("next_media_ids") or None

        return medias[:amount] if amount else medias

    def hashtag_medias_top(self, name: str, amount: int = 27) -> List[dict]:
        """Fetch the top posts (Top) of a hashtag; returns a list of media dicts"""
        return self.hashtag_medias_page(name, tab="top", amount=amount)

    def hashtag_medias_recent(self, name: str, amount: int = 27) -> List[dict]:
        """Fetch the latest posts (Recent) of a hashtag; returns a list of media dicts"""
        return self.hashtag_medias_page(name, tab="recent", amount=amount)

    # ------------------------------------------------------------------
    # Follow / unfollow a hashtag
    # ------------------------------------------------------------------
    def hashtag_follow(self, name: str) -> bool:
        """Follow a hashtag; returns True on success"""
        name = self._clean_name(name)
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        result = self.private_request(f"tags/follow/{name}/", data)
        return result.get("status") == "ok"

    def hashtag_unfollow(self, name: str) -> bool:
        """Unfollow a hashtag; returns True on success"""
        name = self._clean_name(name)
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        result = self.private_request(f"tags/unfollow/{name}/", data)
        return result.get("status") == "ok"

    # ------------------------------------------------------------------
    # Hashtag stories
    # ------------------------------------------------------------------
    def hashtag_story(self, name: str) -> List[dict]:
        """Fetch the list of story (reel item) of a hashtag; returns a list of media dicts"""
        name = self._clean_name(name)
        try:
            result = self.private_request(f"tags/{name}/story/")
        except ClientError:
            return []
        reel = result.get("story") or result.get("reel") or {}
        items = reel.get("items") or []
        return [i for i in items if isinstance(i, dict)]

    # ------------------------------------------------------------------
    # Hashtags a user follows
    # ------------------------------------------------------------------
    def hashtags_followed(
        self, user_id: Optional[str] = None, amount: int = 0
    ) -> List[dict]:
        """
        Fetch the list of hashtags a user follows (best-effort).
        user_id=None = use the currently logged-in account; returns a list of tag dicts.
        """
        user_id = str(user_id or self.user_id)
        try:
            result = self.private_request(
                f"users/{user_id}/following_tags_info/"
            )
        except ClientError:
            return []
        tags = result.get("tags") or []
        tags = [t for t in tags if isinstance(t, dict)]
        return tags[:amount] if amount else tags

    def hashtag_following(self, name: str, amount: int = 0) -> List[dict]:
        """Fetch the list of users who follow this hashtag (best-effort); returns a list of user dicts"""
        name = self._clean_name(name)
        users: List[dict] = []
        max_id = ""
        for _ in range(_MAX_PAGES):
            params: Dict[str, Any] = {}
            if max_id:
                params["max_id"] = max_id
            try:
                result = self.private_request(
                    f"tags/{name}/following/", params=params or None
                )
            except ClientError:
                break
            users.extend(
                u for u in (result.get("users") or []) if isinstance(u, dict)
            )
            if amount and len(users) >= amount:
                break
            next_max_id = result.get("next_max_id")
            if not next_max_id or next_max_id == max_id:
                break
            max_id = next_max_id
        return users[:amount] if amount else users
