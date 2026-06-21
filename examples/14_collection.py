# -*- coding: utf-8 -*-
"""Saved collections examples — demonstrates every CollectionMixin method."""
from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    my_user_id,
    first_media_of,
    writes_disabled_note,
)

cl = login(get_client())
me = my_user_id(cl)   # the logged-in account's user id

section("Read examples")
# List all of the logged-in account's saved collections (collections/list/)
cols = cl.collections(); show("collections", cols)
# Fetch up to 20 saved media from the general saved feed (feed/saved/)
saved = cl.saved_medias(amount=20); show("saved_medias", saved)

# Resolve a real collection_id from the first collection (guard if there are none)
first_col = cols[0] if cols else {}
cid = first_col.get("collection_id") or ""        # id of the first collection
cname = first_col.get("collection_name") or ""    # name of the first collection

if cid:
    # Fetch a single collection's metadata by its collection_id
    res = cl.collection_info(cid); show("collection_info", res)
    # Fetch up to 10 media saved inside that collection (feed/collection/<id>/)
    res = cl.collection_medias(cid, amount=10); show("collection_medias", res)
else:
    show("collection_info", "(skipped — no collections found on this account)")

if cname:
    # Resolve a collection_id from a collection name (case-insensitive)
    res = cl.collection_id_by_name(cname); show("collection_id_by_name", res)
else:
    show("collection_id_by_name", "(skipped — no named collection to resolve)")

section("Write examples (guarded)")
if RUN_WRITES:
    # Grab one of our own posts to add into a collection (full media_id '<pk>_<uid>')
    my_media = first_media_of(cl, me)
    media_id = my_media.get("id") or ""            # full media_id of our first post
    media_pk = my_media.get("pk") or ""            # bare pk of our first post

    # Create a brand-new collection (collections/create/) and read back its id
    created = cl.collection_create("Example Collection"); show("collection_create", created)
    new_cid = created.get("collection_id") or ""

    if new_cid:
        # Rename the collection we just created (collections/<id>/edit/)
        res = cl.collection_edit_name(new_cid, "Renamed Collection"); show("collection_edit_name", res)
        if media_id:
            # Add a media (full '<pk>_<uid>' id) into the collection
            res = cl.collection_add_media(new_cid, [media_id]); show("collection_add_media", res)
            # Remove that same media from the collection again
            res = cl.collection_remove_media(new_cid, [media_id]); show("collection_remove_media", res)
        if media_pk:
            # Add a media by its bare pk (binds the current user id automatically)
            res = cl.collection_add_media_by_pk(new_cid, [media_pk]); show("collection_add_media_by_pk", res)
        # Delete the whole collection (saved media stay in the general saved feed)
        res = cl.collection_delete(new_cid); show("collection_delete", res)
else:
    writes_disabled_note()

print("\nCollection examples done.")
