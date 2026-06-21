# -*- coding: utf-8 -*-
"""Friendship examples — demonstrates every FriendshipMixin method."""
from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    target_user_id,
    my_user_id,
    first_media_of,
    writes_disabled_note,
)

cl = login(get_client())
uid = target_user_id(cl)          # numeric id of the IG_TARGET account
me = my_user_id(cl)               # our own numeric id

section("Read examples")

# View the relationship status with a single user (following/followed_by/blocking/...)
show("friendship_show", cl.friendship_show(uid))

# View the relationship status with several users at once (list of ids)
show("friendship_show_many", cl.friendship_show_many([uid]))

# True if we are currently following this user
show("is_following", cl.is_following(uid))

# True if this user follows us back
show("is_followed_by", cl.is_followed_by(uid))

# First 50 followers of the target (user_followers auto-paginates)
show("user_followers (50)", len(cl.user_followers(uid, amount=50)))

# First 50 accounts the target is following
show("user_following (50)", len(cl.user_following(uid, amount=50)))

# Only the numeric ids of the first 50 followers
show("user_followers_ids (50)", cl.user_followers_ids(uid, amount=50)[:10])

# Only the numeric ids of the first 50 following
show("user_following_ids (50)", cl.user_following_ids(uid, amount=50)[:10])

# Follow requests awaiting our approval (private account inbox) — list of users
show("pending_requests", len(cl.pending_requests()))

# Full pending inbox payload (users + suggested_users + ...)
show("pending_inbox keys", list(cl.pending_inbox().keys()))

# Accounts we have blocked
show("blocked_users", len(cl.blocked_users()))

# Accounts we have restricted
show("restricted_users", len(cl.restricted_users()))

section("Write examples (guarded)")
if RUN_WRITES:
    # Follow the target user
    show("follow", cl.follow(uid))

    # Unfollow the target user
    show("unfollow", cl.unfollow(uid))

    # Block the target user
    show("block", cl.block(uid))

    # Unblock the target user
    show("unblock", cl.unblock(uid))

    # Remove this user from our followers (without blocking)
    show("remove_follower", cl.remove_follower(uid))

    # Hide the user's posts from our feed
    show("mute_posts", cl.mute_posts(uid))

    # Unmute the user's posts
    show("unmute_posts", cl.unmute_posts(uid))

    # Hide the user's stories
    show("mute_stories", cl.mute_stories(uid))

    # Unmute the user's stories
    show("unmute_stories", cl.unmute_stories(uid))

    # Mute both posts and stories in one call
    show("mute_posts_and_stories", cl.mute_posts_and_stories(uid))

    # Unmute both posts and stories in one call
    show("unmute_posts_and_stories", cl.unmute_posts_and_stories(uid))

    # Restrict the user (limits their interactions with us)
    show("restrict", cl.restrict(uid))

    # Unrestrict the user
    show("unrestrict", cl.unrestrict(uid))

    # Approve a pending follow request from this user (no-op if none pending)
    show("approve_pending", cl.approve_pending(uid))

    # Reject/ignore a pending follow request from this user
    show("reject_pending", cl.reject_pending(uid))
else:
    writes_disabled_note()

print("\nFriendship examples done.")
