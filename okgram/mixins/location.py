"""
LocationMixin — methods related to "locations" (location / place)

Covers:
    - Fetching location info (location_info)
    - Fetching a location's feed (top / recent) with pagination
    - Searching locations by coordinates (location_search) and by query (fbsearch_places)
    - A location's story / related locations (related)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils
from ..exceptions import ClientNotFoundError, LocationNotFound


class LocationMixin:
    """Collection of location-related methods (read info / search / location feed)"""

    # attributes the main client already has (declared for type hints only)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # Maximum number of pages to loop to prevent an infinite loop
    _MAX_PAGES: int = 50

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @property
    def _location_rank_token(self) -> str:
        """rank_token that IG uses alongside searches = '<user_id>_<uuid>'"""
        uid = self.user_id or "0"
        return f"{uid}_{self.device.uuid}"

    # ------------------------------------------------------------------
    # Location info
    # ------------------------------------------------------------------
    def location_info(self, location_pk: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch info about a location by location_pk (GET).
        Returns the location dict (the whole last_json, since IG returns fields directly).
        """
        try:
            result = self.private_request(
                f"locations/{location_pk}/location_info/"
            )
        except ClientNotFoundError as exc:
            raise LocationNotFound(
                f"Location {location_pk} not found", **getattr(exc, "extra", {})
            ) from exc
        # some responses wrap the data inside "location"
        return result.get("location", result)

    def location_complaint_info(
        self, location_pk: Union[int, str]
    ) -> Dict[str, Any]:
        """Fetch complaint/report info for a location (GET) — returns last_json"""
        return self.private_request(
            f"locations/{location_pk}/complaint_info/"
        )

    def location_story(self, location_pk: Union[int, str]) -> Dict[str, Any]:
        """
        Fetch stories tagged with this location (GET).
        Returns the story dict (under the 'story' key if present, otherwise the whole payload).
        """
        result = self.private_request(f"locations/{location_pk}/story/")
        return result.get("story", result)

    def location_related(
        self, location_pk: Union[int, str]
    ) -> List[Dict[str, Any]]:
        """
        Fetch locations related to this location (GET).
        Returns a list of location dicts.
        """
        result = self.private_request(f"locations/{location_pk}/related/")
        related = result.get("related") or []
        if isinstance(related, dict):
            related = related.get("locations") or related.get("items") or []
        return related

    # ------------------------------------------------------------------
    # Location feed (sections) — top / recent
    # ------------------------------------------------------------------
    def location_sections_page(
        self,
        location_pk: Union[int, str],
        tab: str = "ranked",
        max_id: str = "",
        page: Union[int, str] = "",
        next_media_ids: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """
        Fetch one page of a location's feed (POST endpoint even though it is a read).
        tab: 'ranked' (top) or 'recent'.
        Returns the whole last_json (contains sections, next_max_id, next_page, more_available).
        """
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "session_id": utils.generate_uuid(),
            "tab": tab,
        }
        if self.user_id:
            data["_uid"] = self.user_id
        if max_id:
            data["max_id"] = max_id
        if page != "" and page is not None:
            data["page"] = str(page)
        if next_media_ids is not None:
            data["next_media_ids"] = utils.json_dumps(next_media_ids)
        return self.private_request(
            f"locations/{location_pk}/sections/", data
        )

    def _location_medias(
        self,
        location_pk: Union[int, str],
        tab: str,
        amount: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Loop and fetch media from a location's feed for the given tab until amount is reached or exhausted.
        amount=0 = fetch all (loop capped at _MAX_PAGES pages).
        Returns a list of media dicts.
        """
        medias: List[Dict[str, Any]] = []
        max_id: str = ""
        page: Union[int, str] = ""
        next_media_ids: Optional[List[Any]] = None

        for _ in range(self._MAX_PAGES):
            result = self.location_sections_page(
                location_pk,
                tab=tab,
                max_id=max_id,
                page=page,
                next_media_ids=next_media_ids,
            )
            for section in result.get("sections") or []:
                layout = section.get("layout_content") or {}
                medias_block = (
                    layout.get("medias")
                    or (
                        (layout.get("one_by_two_item") or {}).get("clips") or {}
                    ).get("items")
                    or []
                )
                for item in medias_block:
                    media = item.get("media") if isinstance(item, dict) else None
                    if media:
                        medias.append(media)
                    if amount and len(medias) >= amount:
                        return medias[:amount]

            if not result.get("more_available"):
                break
            new_max_id = result.get("next_max_id") or ""
            if not new_max_id or new_max_id == max_id:
                break
            max_id = new_max_id
            page = result.get("next_page", page)
            next_media_ids = result.get("next_media_ids")

        if amount:
            return medias[:amount]
        return medias

    def location_medias_top(
        self, location_pk: Union[int, str], amount: int = 27
    ) -> List[Dict[str, Any]]:
        """
        Fetch the top posts (top/ranked) of a location.
        amount=0 = all.
        """
        return self._location_medias(location_pk, "ranked", amount)

    def location_medias_recent(
        self, location_pk: Union[int, str], amount: int = 27
    ) -> List[Dict[str, Any]]:
        """
        Fetch the latest posts (recent) of a location.
        amount=0 = all.
        """
        return self._location_medias(location_pk, "recent", amount)

    # ------------------------------------------------------------------
    # Search locations
    # ------------------------------------------------------------------
    def location_search(
        self,
        lat: Union[float, str],
        lng: Union[float, str],
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Search for locations near the lat/lng coordinates (GET) — can also search with a query.
        Returns a list of venue dicts (from key 'venues').
        """
        params: Dict[str, Any] = {
            "latitude": str(lat),
            "longitude": str(lng),
            "rank_token": self._location_rank_token,
            "timestamp": str(utils.now_ms()),
        }
        if query:
            params["search_query"] = query
        result = self.private_request("location_search/", params=params)
        return result.get("venues") or []

    def fbsearch_places(
        self,
        query: str,
        lat: Optional[Union[float, str]] = None,
        lng: Optional[Union[float, str]] = None,
        count: int = 30,
    ) -> List[Dict[str, Any]]:
        """
        Search for locations by query (Facebook places search, GET).
        Provide lat/lng to rank by proximity.
        Returns a list of place item dicts (from key 'items').
        """
        params: Dict[str, Any] = {
            "search_surface": "places_search_page",
            "timezone_offset": str(getattr(self, "timezone_offset",
                                            config.TIMEZONE_OFFSET)),
            "count": str(count),
            "query": query,
            "rank_token": self._location_rank_token,
        }
        if lat is not None and lng is not None:
            params["lat"] = str(lat)
            params["lng"] = str(lng)
        result = self.private_request("fbsearch/places/", params=params)
        return result.get("items") or []

    def location_search_one(
        self,
        lat: Union[float, str],
        lng: Union[float, str],
        query: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Search for locations and return the single best match (or None if none found)"""
        venues = self.location_search(lat, lng, query)
        if venues:
            return venues[0]
        return None

    # ------------------------------------------------------------------
    # convenience: take a location dict and build a payload for tagging when posting
    # ------------------------------------------------------------------
    def location_build(self, location: Union[Dict[str, Any], str, int]) -> str:
        """
        Convert a location dict (from search results) -> JSON string for the 'location' field
        when configuring media (mimics the format the real app sends).
        """
        if not location:
            return utils.json_dumps({})
        # support input that is a pk (int/str) or a JSON string, not just a dict
        if not isinstance(location, dict):
            text = str(location)
            try:
                import json as _json
                parsed = _json.loads(text)
                location = parsed if isinstance(parsed, dict) else {"pk": text}
            except Exception:
                location = {"pk": text}
        pk = (
            location.get("pk")
            or location.get("external_id")
            or location.get("facebook_places_id")
            or (location.get("location") or {}).get("pk")
        )
        payload = {
            "name": location.get("name", ""),
            "address": location.get("address", ""),
            "lat": location.get("lat"),
            "lng": location.get("lng"),
            "external_source": location.get("external_source",
                                            "facebook_places"),
            "facebook_places_id": pk,
        }
        return utils.json_dumps(payload)
