"""
InsightsMixin — fetch statistics/insights for the account and posts

Covers: account insights (account organic), post insights (media),
story insights, the aggregated feed of insights for all posts (with pagination),
and helpers to summarize reach / engagement totals

Important warning:
    insights endpoints "work only for professional accounts" (business / creator)
    If called with a personal account, IG returns an error (often 400/feedback_required)
    Additionally, insights is a category where IG changes endpoints/parameters often —
    methods marked best-effort may need to be adjusted to match the app version in use

Note: this is a mixin, so it has no __init__ — state/request methods come from the
main class (InstagramAPI) via multiple inheritance
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils  # noqa: F401  (config kept for later use)
from ..exceptions import ClientError, ClientNotFoundError, MediaNotFound

# Ceiling on the number of pages to iterate during pagination (prevents endless loops when amount=0)
_MAX_PAGES = 50

# media_id accepts either a full id ('<pk>_<uid>') or a bare pk (int/str)
MediaId = Union[int, str]


class InsightsMixin:
    """
    Collection of insights-fetching methods — works only for professional accounts (business/creator)

    This is a mixin with no __init__, only methods
    """

    # Attributes the main class (InstagramAPI) already provides — declared for type hints
    user_id: Optional[str]
    username: Optional[str]
    device: Any
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _media_id(self, media_id: MediaId) -> str:
        """
        Convert input into a media_id string that can be sent to IG
        Accepts either a full id ('<pk>_<uid>') or a bare pk
        """
        return str(media_id)

    def _full_media_id(self, media_id: MediaId) -> str:
        """
        Return the full media_id '<pk>_<userid>'
        If a bare pk is given (no '_'), the current account's user_id is appended
        (insights are viewable only for one's own posts, so it defaults to self.user_id)
        """
        mid = str(media_id)
        if "_" in mid:
            return mid
        return utils.pk_with_user_id(mid, self.user_id or "")

    def _insights_error(self, exc: ClientError) -> ClientError:
        """
        Translate an insights error into something meaningful — the most common cause
        is that the account is not professional and therefore cannot access insights
        """
        msg = (getattr(exc, "message", "") or str(exc)).lower()
        if "not authorized" in msg or "business" in msg or "professional" in msg:
            return ClientError(
                "Cannot access insights — requires a professional account "
                "(business/creator) only",
                response=getattr(exc, "response", None),
                code=getattr(exc, "code", None),
            )
        return exc

    # ==================================================================
    # ACCOUNT INSIGHTS
    # ==================================================================
    def insights_account(
        self,
        *,
        show_promotions_in_landing_page: bool = True,
        first: int = 30,
    ) -> Dict[str, Any]:
        """
        Fetch overview insights for the account (organic) (GET) — returns a dict (last_json)

        Requires a professional account only
        """
        params: Dict[str, Any] = {
            "show_promotions_in_landing_page": (
                "true" if show_promotions_in_landing_page else "false"
            ),
            "first": first,
        }
        try:
            self.private_request(
                "insights/account_organic_insights/", params=params
            )
        except ClientError as exc:
            raise self._insights_error(exc) from exc
        return self.last_json

    def insights_account_summary(self) -> Dict[str, Any]:
        """
        Fetch summarized account insights (best-effort)

        Tries the summary endpoint first; if absent, falls back to insights_account()
        Requires a professional account only
        """
        try:
            return self.private_request("insights/account_insights/")
        except ClientError:
            # fall back to the regular organic insights
            return self.insights_account()

    # ==================================================================
    # MEDIA INSIGHTS
    # ==================================================================
    def insights_media(self, media_id: MediaId) -> Dict[str, Any]:
        """
        Fetch insights for a single post (GET organic insights) — returns a dict (last_json)

        media_id: accepts a full id '<pk>_<uid>' or a bare pk
        Requires being the post owner and a professional account
        """
        full_id = self._full_media_id(media_id)
        params = {"ig_media_id": full_id}
        try:
            self.private_request(
                "insights/media_organic_insights/", params=params
            )
        except ClientNotFoundError as exc:
            raise MediaNotFound(
                f"Media {full_id} not found",
                response=getattr(exc, "response", None),
            ) from exc
        except ClientError as exc:
            raise self._insights_error(exc) from exc
        return self.last_json

    def insights_media_v2(self, media_id: MediaId) -> Dict[str, Any]:
        """
        Fetch post insights via the media/{id}/insights/ endpoint (POST, best-effort)

        An alternative to insights_media() in case the organic endpoint is disabled
        Requires being the post owner and a professional account
        """
        full_id = self._full_media_id(media_id)
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        try:
            return self.private_request(f"media/{full_id}/insights/", data=data)
        except ClientError as exc:
            raise self._insights_error(exc) from exc

    def insights_media_by_pk(self, pk: MediaId) -> Dict[str, Any]:
        """
        convenience: fetch post insights from a bare pk (user_id appended automatically)
        Returns a dict (last_json) — requires a professional account
        """
        return self.insights_media(self._full_media_id(pk))

    def insights_media_by_url(self, url: str) -> Dict[str, Any]:
        """
        convenience: fetch post insights from a full url (e.g. /p/<code>/)
        Uses MediaMixin's media_pk_from_url — requires a professional account
        """
        pk = self.media_pk_from_url(url)  # type: ignore[attr-defined]
        return self.insights_media(self._full_media_id(pk))

    # ==================================================================
    # MEDIA INSIGHTS FEED (all posts combined, with pagination)
    # ==================================================================
    def insights_media_feed_page(
        self,
        *,
        timeframe: str = "ONE_WEEK",
        data_ordering: str = "REACH_COUNT",
        count: int = 20,
        cursor: str = "",
    ) -> Dict[str, Any]:
        """
        Fetch one raw page of insights for all posts (POST, best-effort)

        timeframe: ONE_WEEK | TWO_WEEKS | ONE_MONTH | THREE_MONTHS | SIX_MONTHS | ONE_YEAR | TWO_YEARS
        data_ordering: REACH_COUNT | IMPRESSION_COUNT | LIKE_COUNT | COMMENT_COUNT
                       | SHARE_COUNT | SAVE_COUNT | ENGAGEMENT_COUNT | FOLLOW
        Returns the full dict (typically containing media and paging/cursor)

        NOTE (best-effort): IG changes this endpoint's schema often
        (formerly GraphQL/Bloks). If returned fields do not match, adjust data/data_ordering
        to match the app version in use — requires a professional account only
        """
        data: Dict[str, Any] = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
            "timeframe": timeframe,
            "data_ordering": data_ordering,
            "count": count,
        }
        if cursor:
            data["cursor"] = cursor
        try:
            return self.private_request(
                "insights/account_organic_insights/", data=data
            )
        except ClientError as exc:
            raise self._insights_error(exc) from exc

    def insights_media_feed_all(
        self,
        timeframe: str = "ONE_WEEK",
        data_ordering: str = "REACH_COUNT",
        count: int = 20,
        amount: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetch insights for all posts (paginates by cursor) (best-effort)

        amount=0 = fetch all (capped at ~50 pages), greater than 0 = stop once the count is reached
        Returns a list of media-insight dicts — requires a professional account

        NOTE (best-effort): the response structure may vary by version — this method
        tries to read the list from several possible keys (media / nodes / data)
        """
        items: List[Dict[str, Any]] = []
        cursor = ""
        for _ in range(_MAX_PAGES):
            result = self.insights_media_feed_page(
                timeframe=timeframe,
                data_ordering=data_ordering,
                count=count,
                cursor=cursor,
            )
            page_items = self._extract_feed_items(result)
            items.extend(page_items)
            if amount and len(items) >= amount:
                return items[:amount]
            cursor = self._extract_next_cursor(result)
            if not cursor or not page_items:
                break
        return items[:amount] if amount else items

    @staticmethod
    def _extract_feed_items(result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract the list of media from a response with an uncertain schema (best-effort)"""
        for key in ("media", "items", "nodes", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return value
        # Some versions nest under edges -> [{node: {...}}, ...]
        edges = result.get("edges")
        if isinstance(edges, list):
            return [e.get("node", e) for e in edges if isinstance(e, dict)]
        return []

    @staticmethod
    def _extract_next_cursor(result: Dict[str, Any]) -> str:
        """Extract the next page's cursor from a response with an uncertain schema (best-effort)"""
        for key in ("next_cursor", "next_max_id", "max_id", "end_cursor"):
            value = result.get(key)
            if value:
                return str(value)
        paging = result.get("paging") or result.get("page_info") or {}
        if isinstance(paging, dict):
            if not paging.get("has_next_page", True):
                return ""
            for key in ("next_cursor", "end_cursor", "cursor", "next_max_id"):
                value = paging.get(key)
                if value:
                    return str(value)
        return ""

    # ==================================================================
    # STORY INSIGHTS
    # ==================================================================
    def insights_story(self, story_id: MediaId) -> Dict[str, Any]:
        """
        Fetch insights for a single story (POST media insights, best-effort)

        story_id: full id '<pk>_<uid>' or a bare pk
        Requires being the story owner and a professional account
        (stories retain insights for up to about 14 days)
        """
        full_id = self._full_media_id(story_id)
        data = {
            "_uuid": self.device.uuid,
            "_uid": self.user_id,
            "device_id": self.device.device_id,
        }
        try:
            return self.private_request(f"media/{full_id}/insights/", data=data)
        except ClientNotFoundError as exc:
            raise MediaNotFound(
                f"Story {full_id} not found (may be expired or over 14 days old)",
                response=getattr(exc, "response", None),
            ) from exc
        except ClientError as exc:
            raise self._insights_error(exc) from exc

    def insights_stories_all(
        self, story_ids: List[MediaId]
    ) -> List[Dict[str, Any]]:
        """
        Fetch insights for multiple stories one at a time — returns a list of result dicts
        Items that cannot be fetched (expired, etc.) are skipped
        """
        out: List[Dict[str, Any]] = []
        for sid in story_ids:
            try:
                out.append(self.insights_story(sid))
            except ClientError:
                continue
        return out

    # ==================================================================
    # summary helpers (extract notable values from an insights dict)
    # ==================================================================
    @staticmethod
    def _find_metric(data: Any, *names: str) -> Optional[int]:
        """
        Recursively search for a metric in an insights dict (deeply nested structure)
        Returns the int of the first matching value, or None — best-effort
        """
        targets = {n.lower() for n in names}
        stack: List[Any] = [data]
        while stack:
            cur = stack.pop()
            if isinstance(cur, dict):
                for key, value in cur.items():
                    if isinstance(key, str) and key.lower() in targets:
                        if isinstance(value, (int, float)):
                            return int(value)
                        if isinstance(value, dict):
                            inner = value.get("value", value.get("count"))
                            if isinstance(inner, (int, float)):
                                return int(inner)
                        if isinstance(value, str) and value.isdigit():
                            return int(value)
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(cur, list):
                stack.extend(cur)
        return None

    def media_reach(self, media_id: MediaId) -> int:
        """Get a post's reach from insights — returns 0 if not found (best-effort)"""
        data = self.insights_media(media_id)
        return self._find_metric(data, "reach", "reach_count") or 0

    def media_impressions(self, media_id: MediaId) -> int:
        """Get a post's impressions from insights — returns 0 if not found (best-effort)"""
        data = self.insights_media(media_id)
        return (
            self._find_metric(data, "impressions", "impression_count") or 0
        )

    def media_engagement(self, media_id: MediaId) -> int:
        """Get a post's engagement from insights — returns 0 if not found (best-effort)"""
        data = self.insights_media(media_id)
        return (
            self._find_metric(data, "engagement", "engagement_count") or 0
        )

    def media_saves(self, media_id: MediaId) -> int:
        """Get a post's saves from insights — returns 0 if not found (best-effort)"""
        data = self.insights_media(media_id)
        return self._find_metric(data, "saved", "save_count", "saves") or 0

    def account_reach(
        self, *, first: int = 30
    ) -> int:
        """Get the account's total reach from insights — returns 0 if not found (best-effort)"""
        data = self.insights_account(first=first)
        return self._find_metric(data, "reach", "reach_count") or 0

    def account_impressions(
        self, *, first: int = 30
    ) -> int:
        """Get the account's total impressions — returns 0 if not found (best-effort)"""
        data = self.insights_account(first=first)
        return (
            self._find_metric(data, "impressions", "impression_count") or 0
        )
