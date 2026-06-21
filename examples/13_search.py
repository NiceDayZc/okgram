# -*- coding: utf-8 -*-
"""Search & explore examples — demonstrates every SearchMixin method (plus explore)."""
from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    target_user_id,
    writes_disabled_note,
)

cl = login(get_client())
tid = target_user_id(cl)   # numeric id of the IG_TARGET account (used for chaining)

section("Read examples")

# Blended top search (mix of users / hashtags / places) for a query
show("fbsearch_topsearch", cl.fbsearch_topsearch("nasa"))

# Same blended search but flattened to just the combined result list
show("fbsearch_topsearch_flat", len(cl.fbsearch_topsearch_flat("nasa")))

# Search users by name/username
show("search_users", len(cl.search_users("nasa", count=10)))

# Search users by keyword (alias of search_users)
show("search_users_by_keyword", len(cl.search_users_by_keyword("nasa", count=10)))

# Search hashtags matching a query
show("search_hashtags", len(cl.search_hashtags("travel", count=10)))

# Search places/locations matching a query
show("search_locations", len(cl.search_locations("Bangkok", count=10)))

# Search places (alias of search_locations)
show("search_places", len(cl.search_places("Bangkok", count=10)))

# Fetch one raw page of the explore feed
show("explore_feed", list(cl.explore_feed().keys()))

# Fetch up to 30 media items from the explore page (auto-paginates)
show("explore_medias", len(cl.explore_medias(amount=30)))

# Fetch related/suggested accounts derived from a target user id
show("discover_chaining", len(cl.discover_chaining(target_id=tid)))

# Fetch accounts IG suggests you follow (best-effort)
show("suggested_users", len(cl.suggested_users(limit=30)))

# Fetch suggested searches/accounts on the search page
show("suggested_searches", len(cl.suggested_searches("blended")))

# Fetch the account's recent search history
show("recent_searches", len(cl.recent_searches()))

section("Write examples (guarded)")
if RUN_WRITES:
    # Clear all of the account's search history
    show("clear_search_history", cl.clear_search_history())
else:
    writes_disabled_note()

print("\nSearch examples done.")
