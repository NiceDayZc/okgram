# -*- coding: utf-8 -*-
"""Hashtag examples — demonstrates every HashtagMixin method."""
from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    my_user_id,
    writes_disabled_note,
)

cl = login(get_client())
me = my_user_id(cl)        # the logged-in account's user id
TAG = "travel"             # a popular hashtag name to read

section("Read examples")

# Fetch basic info about a hashtag (post count, id, follow status, etc.)
show("hashtag_info", cl.hashtag_info(TAG))

# Fetch the list of related hashtags (best-effort)
show("hashtag_related", cl.hashtag_related(TAG))

# Fetch up to 20 of the top posts (Top tab) for this hashtag
show("hashtag_medias_top", len(cl.hashtag_medias_top(TAG, amount=20)))

# Fetch up to 20 of the latest posts (Recent tab) for this hashtag
show("hashtag_medias_recent", len(cl.hashtag_medias_recent(TAG, amount=20)))

# Fetch the current stories tagged with this hashtag
show("hashtag_story", cl.hashtag_story(TAG))

# Fetch the list of hashtags the logged-in account follows
show("hashtags_followed", cl.hashtags_followed(me))

# Fetch the list of users who follow this hashtag (best-effort)
show("hashtag_following", len(cl.hashtag_following(TAG, amount=20)))

section("Write examples (guarded)")
if RUN_WRITES:
    # Follow a hashtag (adds it to the account's followed tags)
    show("hashtag_follow", cl.hashtag_follow(TAG))

    # Unfollow a hashtag (removes it from the account's followed tags)
    show("hashtag_unfollow", cl.hashtag_unfollow(TAG))
else:
    writes_disabled_note()

print("\nHashtag examples done.")
