"""
SearchMixin — search (users/hashtags/places) and the explore feed

Covers:
    - blended top search, user search, hashtag search, place search
    - explore feed / explore medias (with pagination)
    - discover chaining (related accounts) and suggested lists
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import config, utils
from ..exceptions import ClientError, ClientNotFoundError

# Prevent pagination from looping endlessly
_MAX_PAGES = 50


class SearchMixin:
    """Collection of search and explore methods (mixin — no __init__)"""

    # attributes the main client already has (declared for type hints)
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict

    # ------------------------------------------------------------------
    # rank token (used with IG's search/feed endpoints)
    # ------------------------------------------------------------------
    def generate_rank_token(self) -> str:
        """Generate a rank_token of the form '<user_id>_<uuid>' (or just uuid if not logged in)"""
        if self.user_id:
            return f"{self.user_id}_{self.device.uuid}"
        return f"{utils.generate_uuid()}_{self.device.uuid}"

    # ------------------------------------------------------------------
    # top search (blended)
    # ------------------------------------------------------------------
    def fbsearch_topsearch(
        self, query: str, count: int = 30
    ) -> Dict[str, Any]:
        """
        Blended search: returns a dict mixing users/hashtags/places
        in key 'list', as well as 'users'/'hashtags'/'places' (depending on results).
        """
        params: Dict[str, Any] = {
            "search_surface": "top_search_page",
            "context": "blended",
            "query": query,
            "rank_token": self.generate_rank_token(),
            "count": count,
            "timezone_offset": str(config.TIMEZONE_OFFSET),
        }
        result = self.private_request("fbsearch/topsearch/", params=params)
        return result

    def fbsearch_topsearch_flat(
        self, query: str, count: int = 30
    ) -> List[Dict[str, Any]]:
        """Return only the 'list' key (the flat combined result list) of topsearch"""
        result = self.fbsearch_topsearch(query, count=count)
        return result.get("list", []) or []

    # ------------------------------------------------------------------
    # Search users
    # ------------------------------------------------------------------
    def search_users(
        self, query: str, count: int = 30
    ) -> List[Dict[str, Any]]:
        """Search users by name/username — returns a list of user dicts"""
        params: Dict[str, Any] = {
            "search_surface": "user_search_page",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "count": count,
            "q": query,
            "rank_token": self.generate_rank_token(),
        }
        result = self.private_request("users/search/", params=params)
        return result.get("users", []) or []

    def search_users_by_keyword(
        self, query: str, count: int = 30
    ) -> List[Dict[str, Any]]:
        """alias of search_users (search users by keyword)"""
        return self.search_users(query, count=count)

    # ------------------------------------------------------------------
    # Search hashtags
    # ------------------------------------------------------------------
    def search_hashtags(
        self, query: str, count: int = 30
    ) -> List[Dict[str, Any]]:
        """Search hashtags — returns a list of tag dicts (key 'results')"""
        params: Dict[str, Any] = {
            "search_surface": "hashtag_search_page",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "count": count,
            "q": query.lstrip("#"),
            "rank_token": self.generate_rank_token(),
        }
        result = self.private_request("tags/search/", params=params)
        return result.get("results", []) or []

    # ------------------------------------------------------------------
    # Search places
    # ------------------------------------------------------------------
    def search_locations(
        self,
        query: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        count: int = 30,
    ) -> List[Dict[str, Any]]:
        """Search places by query (and coordinates if given) — returns a list of place items"""
        params: Dict[str, Any] = {
            "search_surface": "places_search_page",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "count": count,
            "query": query,
            "rank_token": self.generate_rank_token(),
        }
        if latitude is not None and longitude is not None:
            params["lat"] = str(latitude)
            params["lng"] = str(longitude)
        result = self.private_request("fbsearch/places/", params=params)
        return result.get("items", []) or []

    def search_places(
        self, query: str, count: int = 30
    ) -> List[Dict[str, Any]]:
        """alias of search_locations (search places)"""
        return self.search_locations(query, count=count)

    # ------------------------------------------------------------------
    # explore feed (explore page)
    # ------------------------------------------------------------------
    def explore_feed(
        self, max_id: str = "", is_prefetch: str = "false"
    ) -> Dict[str, Any]:
        """
        Fetch one page of the explore feed — returns the raw dict (contains sectional_items / items / next_max_id).
        Use max_id to request the next page (pagination).
        """
        params: Dict[str, Any] = {
            "is_prefetch": is_prefetch,
            "is_from_promote": "false",
            "timezone_offset": str(config.TIMEZONE_OFFSET),
            "session_id": self.device.client_session_id,
            "supported_capabilities_new": utils.json_dumps(
                config.SUPPORTED_CAPABILITIES
            ),
            "module": "explore_popular",
            "use_sectional_payload": "true",
        }
        if max_id:
            params["max_id"] = max_id
        result = self.private_request(
            "discover/topical_explore/", params=params
        )
        return result

    def _extract_explore_medias(self, feed: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract media dicts from the explore payload (supports both sectional and items)"""
        medias: List[Dict[str, Any]] = []
        # sectional format (new)
        for section in feed.get("sectional_items", []) or []:
            layout = section.get("layout_content", {}) or {}
            # grid media cards (one_by_two / two_by_two, etc.)
            for medium in layout.get("medias", []) or []:
                media = medium.get("media")
                if media:
                    medias.append(media)
            # fill_items (e.g. a single post)
            for fill in layout.get("fill_items", []) or []:
                media = fill.get("media")
                if media:
                    medias.append(media)
            # one_by_two_item -> clips/explore_grid
            obt = layout.get("one_by_two_item") or {}
            clips = (obt.get("clips") or {}).get("items", []) or []
            for clip in clips:
                media = clip.get("media")
                if media:
                    medias.append(media)
        # old format: items directly
        for item in feed.get("items", []) or []:
            media = item.get("media") or item
            if media.get("pk") or media.get("id"):
                medias.append(media)
        return medias

    def explore_medias(self, amount: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch media from the explore page (paginates automatically).
        amount=0 = fetch all that IG provides (loop capped at ~50 pages).
        """
        medias: List[Dict[str, Any]] = []
        max_id = ""
        is_prefetch = "true"
        for _ in range(_MAX_PAGES):
            feed = self.explore_feed(max_id=max_id, is_prefetch=is_prefetch)
            is_prefetch = "false"
            medias.extend(self._extract_explore_medias(feed))
            if amount and len(medias) >= amount:
                return medias[:amount]
            max_id = feed.get("next_max_id") or feed.get("max_id") or ""
            more = feed.get("more_available")
            if not max_id or more is False:
                break
        if amount:
            return medias[:amount]
        return medias

    # ------------------------------------------------------------------
    # discover chaining (related accounts / suggested from one account)
    # ------------------------------------------------------------------
    def discover_chaining(
        self, target_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch related/suggested accounts from the given user id (the 'Suggested for you' button).
        Returns a list of user dicts.
        """
        params: Dict[str, Any] = {
            "target_id": str(target_id),
            "include_reel": "true",
        }
        result = self.private_request("discover/chaining/", params=params)
        return result.get("users", []) or []

    def user_related_profiles(
        self, user_id: str
    ) -> List[Dict[str, Any]]:
        """alias of discover_chaining (profiles related to a user)"""
        return self.discover_chaining(user_id)

    # ------------------------------------------------------------------
    # Suggested lists (best-effort — IG changes the endpoint often)
    # ------------------------------------------------------------------
    def suggested_users(self, limit: int = 30) -> List[Dict[str, Any]]:
        """
        Fetch the list of accounts IG suggests you follow (best-effort).
        Try discover/ayml first, and if that fails fall back to fbsearch/suggested_searches.
        Returns a list of user dicts.
        """
        users = self._suggested_users_ayml(limit=limit)
        if users:
            return users
        return self._suggested_searches_users()

    def _suggested_users_ayml(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Fetch suggested accounts via discover/ayml/ (Accounts You Might Like)"""
        data: Dict[str, Any] = {
            "phone_id": self.device.phone_id,
            "module": "discover_aymf",
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "paginate": "true",
        }
        try:
            result = self.private_request("discover/ayml/", data)
        except (ClientError, ClientNotFoundError):
            return []
        users: List[Dict[str, Any]] = []
        for item in result.get("new_stories", []) or result.get(
            "suggestions", []
        ) or []:
            user = item.get("user") or item
            if user.get("pk"):
                users.append(user)
        if limit:
            return users[:limit]
        return users

    def _suggested_searches_users(self) -> List[Dict[str, Any]]:
        """Fetch top/suggested search results via fbsearch/suggested_searches/ (users)"""
        params = {"type": "users"}
        try:
            result = self.private_request(
                "fbsearch/suggested_searches/", params=params
            )
        except (ClientError, ClientNotFoundError):
            return []
        users: List[Dict[str, Any]] = []
        for entry in result.get("suggested", []) or result.get("list", []) or []:
            user = entry.get("user") or entry
            if isinstance(user, dict) and user.get("pk"):
                users.append(user)
        return users

    def suggested_searches(
        self, search_type: str = "blended"
    ) -> List[Dict[str, Any]]:
        """
        Fetch suggested searches/accounts on the search page (recent + suggested).
        search_type: 'blended' | 'users' | 'hashtag' | 'places'
        """
        params = {"type": search_type}
        result = self.private_request(
            "fbsearch/suggested_searches/", params=params
        )
        return result.get("list", []) or result.get("suggested", []) or []

    def recent_searches(self) -> List[Dict[str, Any]]:
        """Fetch the account's recent search history — returns a list of search entries"""
        result = self.private_request("fbsearch/recent_searches/")
        return result.get("recent", []) or []

    def clear_search_history(self) -> bool:
        """Clear all search history — returns True on success"""
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        result = self.private_request("fbsearch/clear_search_history/", data)
        return result.get("status") == "ok"

    def register_recent_search_click(
        self, entity_type: str, entity_id: str
    ) -> bool:
        """
        Record a search result click (so IG remembers it in recent) — best-effort.
        entity_type: 'user' | 'hashtag' | 'place'
        """
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
        }
        try:
            result = self.private_request(
                "fbsearch/register_recent_search_click/", data
            )
        except ClientError:
            return False
        return result.get("status") == "ok"
