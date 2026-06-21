# -*- coding: utf-8 -*-
"""Media examples — demonstrates every MediaMixin method."""
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
uid = target_user_id(cl)              # numeric id of the IG_TARGET account

# Grab a sample media of the target so we have a real id/code/url to work with.
media = first_media_of(cl, uid)
mid = media.get("id") or media.get("pk")        # full media_id '<pk>_<uid>' or bare pk
code = media.get("code")                          # shortcode, e.g. 'CXXXXXXX'
sample_url = "https://www.instagram.com/p/CXXXXXXX/"  # used for url-based helpers

section("Read examples")

# --- pure helpers: convert between url / code / pk (no network) ---
# Extract the shortcode from a post url
show("media_code_from_url", cl.media_code_from_url(sample_url))

# Convert a post url straight to its numeric pk
show("media_pk_from_url", cl.media_pk_from_url(sample_url))

# Convert a shortcode to its numeric pk
show("media_pk_from_code", cl.media_pk_from_code("CXXXXXXX"))

if mid:
    # Extract the bare pk from a full media_id '<pk>_<uid>'
    show("media_pk", cl.media_pk(mid))

    # Convert a media pk back to its shortcode
    show("media_code_from_pk", cl.media_code_from_pk(cl.media_pk(mid)))

    # Full media info (GET) for the sample post
    show("media_info", cl.media_info(mid))

    # The owner (user) of the post, taken from media_info
    show("media_user", cl.media_user(mid))

    # Number of comments on the post
    show("media_comment_count", cl.media_comment_count(mid))

    # Number of likes on the post
    show("media_like_count", cl.media_like_count(mid))

    # Users who liked the post
    show("media_likers", len(cl.media_likers(mid)))

    # Permalink (public url) of the post
    show("media_permalink", cl.media_permalink(mid))

if code:
    # Fetch post info directly from a shortcode
    show("media_info_by_code", cl.media_info_by_code(code))

    # oEmbed metadata from a post url built from the shortcode
    show("media_oembed", cl.media_oembed(f"https://www.instagram.com/p/{code}/"))

    # Fetch post info directly from a full url
    show("media_info_by_url", cl.media_info_by_url(f"https://www.instagram.com/p/{code}/"))

# Likers of a specific comment (uses the sample post id as a stand-in comment id)
if mid:
    show("media_comment_likers", len(cl.media_comment_likers(mid)))

# List of media that are blocked/restricted for us
show("media_blocked", cl.media_blocked())

# Mark a list of media as 'seen' (best-effort; harmless read-like ping)
if mid:
    show("media_seen", cl.media_seen([mid]))

section("Write examples (guarded)")
if RUN_WRITES and mid:
    # Like the sample post
    show("media_like", cl.media_like(mid))

    # Unlike the sample post
    show("media_unlike", cl.media_unlike(mid))

    # Toggle like state (likes if unliked, unlikes if liked)
    show("media_like_toggle", cl.media_like_toggle(mid))

    # Save the post to the default saved collection
    show("media_save", cl.media_save(mid))

    # Remove the post from saved
    show("media_unsave", cl.media_unsave(mid))

    # Archive one of OUR own posts (only_me); use a media we own in real usage
    own = first_media_of(cl, my_user_id(cl))
    own_mid = own.get("id") or own.get("pk")
    if own_mid:
        # Archive our own post (hide from profile)
        show("media_archive", cl.media_archive(own_mid))

        # Unarchive our own post (show again)
        show("media_unarchive", cl.media_unarchive(own_mid))

        # Edit the caption of our own post
        show("media_edit", cl.media_edit(own_mid, "Updated caption from the API"))

        # Delete our own post (destructive!)
        show("media_delete", cl.media_delete(own_mid))
else:
    writes_disabled_note()

print("\nMedia examples done.")
