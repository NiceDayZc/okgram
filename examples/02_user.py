# -*- coding: utf-8 -*-
"""User examples — demonstrates every UserMixin method."""
from _common import get_client, login, section, show, RUN_WRITES, TARGET_USERNAME, target_user_id, my_user_id, writes_disabled_note

cl = login(get_client())
uid = target_user_id(cl)   # a public account to read (IG_TARGET)

section("Read examples")
# Fetch user info by user pk via the private API
res = cl.user_info(uid); show("user_info", res)
# Fetch user info by username via the private API
res = cl.user_info_by_username(TARGET_USERNAME); show("user_info_by_username", res)
# Fetch profile info via the public web API
res = cl.web_profile_info(TARGET_USERNAME); show("web_profile_info", res)
# Convert a username into its numeric user id
res = cl.username_to_user_id(TARGET_USERNAME); show("username_to_user_id", res)
# Convert a numeric user id back into its username
res = cl.user_id_to_username(uid); show("user_id_to_username", res)
# Search users by free-text query (private API)
res = cl.search_users("cat", count=10); show("search_users", res)
# Search users via the public web topsearch API
res = cl.search_users_web("cat"); show("search_users_web", res)
# Number of accounts this user follows
res = cl.user_following_count(uid); show("user_following_count", res)
# Number of followers this user has
res = cl.user_followers_count(uid); show("user_followers_count", res)
# Total number of posts by this user
res = cl.user_media_count(uid); show("user_media_count", res)
# Whether this user is a private account
res = cl.user_is_private(uid); show("user_is_private", res)
# Fetch the reel/story settings of the logged-in account
res = cl.reel_settings(); show("reel_settings", res)
# Fetch followers this user shares in common with you
res = cl.user_mutual_followers(uid); show("user_mutual_followers", res)
# Fetch similar/suggested accounts derived from this user
res = cl.user_similar_accounts(uid); show("user_similar_accounts", res)
# Alias of user_similar_accounts — related/suggested profiles
res = cl.user_related_profiles(uid); show("user_related_profiles", res)
# Fetch the "about this account" info (signup date, country, etc.)
res = cl.user_about(uid); show("user_about", res)
# Fetch media this user is tagged in (capped to a few items here)
res = cl.usertag_medias(uid, amount=5); show("usertag_medias", res)
# Fetch all story highlights of this user
res = cl.user_highlights(uid); show("user_highlights", res)

section("Write examples (guarded)")
if RUN_WRITES:
    # UserMixin read methods only — no write methods in this category
    writes_disabled_note()
else:
    writes_disabled_note()

print("\nUser examples done.")
