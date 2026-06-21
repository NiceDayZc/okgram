# -*- coding: utf-8 -*-
"""
Example 06 — FeedMixin (all read-only)

Demonstrates every method of the FeedMixin: the home timeline, a single
user's feed (by id, by username, paged), the logged-in account's own posts,
liked/saved posts, posts inside a saved collection, the reels tray and the
popular feed. Every method here is read-only, so there is no IG_RUN_WRITES
guard.

Usage:
    python examples/06_feed.py
"""
from __future__ import annotations

from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    TARGET_USERNAME,
    my_user_id,
    target_user_id,
    first_media_of,
    writes_disabled_note,
)


def main() -> None:
    # build an authenticated client (reuses a saved session when possible)
    cl = login(get_client())

    # resolve a target user id once for the per-user feeds below
    uid = target_user_id(cl)
    show("target_user_id", uid)

    # ------------------------------------------------------------------
    # Home timeline feed
    # ------------------------------------------------------------------
    section("Timeline feed (home)")
    timeline = cl.get_timeline_feed()                      # raw first page of the home timeline
    show("get_timeline_feed.more_available", timeline.get("more_available"))
    show("get_timeline_feed.next_max_id", timeline.get("next_max_id"))

    items = cl.timeline_feed_items(amount=1)               # paged list of feed items (just 1)
    show("timeline_feed_items count", len(items))

    # ------------------------------------------------------------------
    # A single user's feed
    # ------------------------------------------------------------------
    section("User feed")
    medias = cl.user_medias(uid, amount=12)               # up to 12 posts of the target user
    show("user_medias count", len(medias))

    user_page = cl.user_feed_page(uid, count=12)          # one raw page of the target's feed
    show("user_feed_page.more_available", user_page.get("more_available"))
    show("user_feed_page.next_max_id", user_page.get("next_max_id"))

    by_username = cl.user_feed_by_username(TARGET_USERNAME)  # same feed resolved by username
    show("user_feed_by_username count", len(by_username))

    # ------------------------------------------------------------------
    # The logged-in account's own posts
    # ------------------------------------------------------------------
    section("My posts")
    mine = cl.my_medias(amount=12)                        # up to 12 of my own posts
    show("my_medias count", len(mine))

    # ------------------------------------------------------------------
    # Liked + saved posts of the logged-in account
    # ------------------------------------------------------------------
    section("Liked + saved posts")
    liked = cl.liked_medias(amount=12)                    # up to 12 posts I have liked
    show("liked_medias count", len(liked))

    saved = cl.saved_medias(amount=12)                    # up to 12 posts I have saved
    show("saved_medias count", len(saved))

    # ------------------------------------------------------------------
    # Posts inside a saved collection (collection_id resolved via collections())
    # ------------------------------------------------------------------
    section("Collection posts")
    collections = cl.collections()                       # my saved collections (for an id)
    collection_id = collections[0].get("collection_id") if collections else None
    show("collection_id", collection_id)
    if collection_id:
        coll_medias = cl.collection_medias(collection_id, amount=12)  # posts in that collection
        show("collection_medias count", len(coll_medias))
    else:
        print("  (no saved collections found — skipping collection_medias)")

    # ------------------------------------------------------------------
    # Reels tray (stories row) + popular feed
    # ------------------------------------------------------------------
    section("Reels tray + popular feed")
    tray = cl.reels_tray()                               # the story tray at the top of home
    show("reels_tray count", len(tray))

    popular = cl.popular_feed(amount=12)                 # up to 12 posts from the popular feed
    show("popular_feed count", len(popular))

    print("done")


if __name__ == "__main__":
    main()
