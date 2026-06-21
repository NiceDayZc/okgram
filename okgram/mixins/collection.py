"""
CollectionMixin — manages an account's saved collections

Covers: listing collections, creating/deleting collections, adding/removing
media in a collection, fetching collection media with pagination, and viewing
the saved media list (saved feed)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .. import config, utils  # noqa: F401  (config kept for use/consistency with other mixins)
from ..exceptions import ClientError, CollectionNotFound

# Standard collection type values that IG returns in collections/list/
DEFAULT_COLLECTION_TYPES: List[str] = [
    "ALL_MEDIA_AUTO_COLLECTION",
    "PRODUCT_AUTO_COLLECTION",
    "MEDIA",
]

# Cap pagination at this many pages (in case IG returns next_max_id endlessly)
_MAX_PAGES = 50


class CollectionMixin:
    """Collection of methods related to saved collections"""

    # Attributes provided by the main client (declared for type hints only)
    user_id: Optional[str]
    last_json: Dict[str, Any]

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _action_fields(self) -> Dict[str, str]:
        """Standard fields attached to an action-style POST (_uuid / _uid)"""
        return {
            "_uuid": self.device.uuid,
            "_uid": str(self.user_id or ""),
        }

    @staticmethod
    def _as_media_id_list(media_ids: Optional[List[str]]) -> List[str]:
        """Always convert to a list of full media_id strings"""
        return [str(m) for m in (media_ids or [])]

    # ------------------------------------------------------------------
    # list all collections
    # ------------------------------------------------------------------
    def collections(
        self,
        collection_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all collections of the logged-in account
        Returns a list of collection dicts (with collection_id, collection_name, etc.)
        """
        types = collection_types or DEFAULT_COLLECTION_TYPES
        params = {"collection_types": utils.json_dumps(types)}
        result = self.private_request("collections/list/", params=params)
        return result.get("items", [])

    def collection_info(
        self,
        collection_id: Union[int, str],
        collection_types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Find the metadata of a single collection from collections() by collection_id
        Raises CollectionNotFound if not found
        """
        target = str(collection_id)
        for item in self.collections(collection_types):
            if str(item.get("collection_id")) == target:
                return item
        raise CollectionNotFound(f"Collection {collection_id} not found")

    def collection_id_by_name(self, name: str) -> str:
        """Find a collection_id by collection name (case-insensitive) — raises if not found"""
        name_l = name.strip().lower()
        for item in self.collections():
            if str(item.get("collection_name", "")).strip().lower() == name_l:
                return str(item.get("collection_id"))
        raise CollectionNotFound(f"Collection named {name!r} not found")

    # ------------------------------------------------------------------
    # create / delete collection
    # ------------------------------------------------------------------
    def collection_create(
        self,
        name: str,
        media_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new collection (initial media can be added via media_ids)
        Returns the response dict (with the collection_id of the created collection)
        """
        data = {
            "name": name,
            "added_media_ids": utils.json_dumps(self._as_media_id_list(media_ids)),
        }
        data.update(self._action_fields())
        return self.private_request("collections/create/", data)

    def collection_delete(self, collection_id: Union[int, str]) -> bool:
        """Delete an entire collection (media inside remain saved in the general saved feed)"""
        data = self._action_fields()
        result = self.private_request(
            f"collections/{collection_id}/delete/", data
        )
        return result.get("status") == "ok"

    def collection_edit_name(
        self,
        collection_id: Union[int, str],
        name: str,
    ) -> Dict[str, Any]:
        """Rename a collection, returns the response dict"""
        data = {"name": name}
        data.update(self._action_fields())
        return self.private_request(
            f"collections/{collection_id}/edit/", data
        )

    # ------------------------------------------------------------------
    # add / remove media in a collection
    # ------------------------------------------------------------------
    def collection_add_media(
        self,
        collection_id: Union[int, str],
        media_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Add media (in '<pk>_<userid>' format) to an existing collection
        Returns the response dict
        """
        data = {
            "added_media_ids": utils.json_dumps(self._as_media_id_list(media_ids)),
        }
        data.update(self._action_fields())
        return self.private_request(
            f"collections/{collection_id}/edit/", data
        )

    def collection_remove_media(
        self,
        collection_id: Union[int, str],
        media_ids: List[str],
    ) -> Dict[str, Any]:
        """
        Remove media from a collection (media remain saved in the general saved feed)
        Returns the response dict
        """
        data = {
            "removed_media_ids": utils.json_dumps(self._as_media_id_list(media_ids)),
        }
        data.update(self._action_fields())
        return self.private_request(
            f"collections/{collection_id}/edit/", data
        )

    def collection_add_media_by_pk(
        self,
        collection_id: Union[int, str],
        media_pks: List[Union[int, str]],
    ) -> Dict[str, Any]:
        """convenience: add media by pk (converted to '<pk>_<self.user_id>')"""
        media_ids = [
            utils.pk_with_user_id(pk, self.user_id) for pk in media_pks
        ]
        return self.collection_add_media(collection_id, media_ids)

    # ------------------------------------------------------------------
    # fetch collection media (two-level pagination)
    # ------------------------------------------------------------------
    def collection_medias_page(
        self,
        collection_id: Union[int, str],
        max_id: str = "",
    ) -> Dict[str, Any]:
        """
        Fetch one page of collection media (raw) — pass max_id to request the next page
        Returns the full dict (with 'items', 'more_available', 'next_max_id')
        """
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        return self.private_request(
            f"feed/collection/{collection_id}/", params=params or None
        )

    def collection_medias(
        self,
        collection_id: Union[int, str],
        amount: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Fetch all media in a collection (paginates automatically)
        amount=0 = fetch all (capped at ~50 pages); returns a list of media dicts
        """
        medias: List[Dict[str, Any]] = []
        max_id = ""
        pages = 0
        while pages < _MAX_PAGES:
            pages += 1
            result = self.collection_medias_page(collection_id, max_id)
            # Each item in the collection feed may wrap the media under the 'media' key
            for item in result.get("items", []):
                medias.append(item.get("media", item))
                if amount and len(medias) >= amount:
                    return medias[:amount]
            max_id = result.get("next_max_id") or ""
            if not result.get("more_available") or not max_id:
                break
        if amount:
            return medias[:amount]
        return medias

    # ------------------------------------------------------------------
    # all saved media (saved feed) — not limited to a collection
    # ------------------------------------------------------------------
    def saved_medias_page(self, max_id: str = "") -> Dict[str, Any]:
        """Fetch one page of saved media (raw) from feed/saved/ — pass max_id for the next page"""
        params: Dict[str, Any] = {}
        if max_id:
            params["max_id"] = max_id
        return self.private_request("feed/saved/", params=params or None)

    def saved_medias(self, amount: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch all saved media of the account (paginates automatically)
        amount=0 = fetch all (capped at ~50 pages); returns a list of media dicts
        """
        medias: List[Dict[str, Any]] = []
        max_id = ""
        pages = 0
        while pages < _MAX_PAGES:
            pages += 1
            result = self.saved_medias_page(max_id)
            for item in result.get("items", []):
                medias.append(item.get("media", item))
                if amount and len(medias) >= amount:
                    return medias[:amount]
            max_id = result.get("next_max_id") or ""
            if not result.get("more_available") or not max_id:
                break
        if amount:
            return medias[:amount]
        return medias
