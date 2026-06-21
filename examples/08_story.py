# -*- coding: utf-8 -*-
"""Story examples — demonstrates every StoryMixin method (stories + highlights)."""
from _common import get_client, login, section, show, RUN_WRITES, TARGET_USERNAME, my_user_id, target_user_id, writes_disabled_note

cl = login(get_client())
uid = target_user_id(cl)   # a public account whose stories/highlights we read

section("Read examples")
# Fetch the reels tray (the story bar at the top of the feed) — whole dict
res = cl.reels_tray(); show("reels_tray", res)
# Fetch only the list of items/reels in the reels tray (key 'tray')
res = cl.reels_tray_items(); show("reels_tray_items", res)
# Fetch a single user's story items (list, empty if no active stories)
stories = cl.user_stories(uid); show("user_stories", stories)
# Fetch the user's whole reel dict (items, expiring_at, latest_reel_media, ...)
res = cl.user_stories_reel(uid); show("user_stories_reel", res)
# Fetch the stories of multiple users at once -> {user_id: [items...]}
res = cl.users_stories([uid]); show("users_stories", res)
# Fetch a user's stories directly from a username (resolves the id for you)
res = cl.user_story_by_username(TARGET_USERNAME); show("user_story_by_username", res)
# Fetch a user's highlights tray (list of highlights)
highlights = cl.user_highlights(uid); show("user_highlights", highlights)
# Fetch a user's highlights tray directly from a username
res = cl.user_highlights_by_username(TARGET_USERNAME); show("user_highlights_by_username", res)

# resolve a single story media id + its pk from the first story item (guarded if empty)
first_story = stories[0] if stories else {}
story_pk = first_story.get("pk") or first_story.get("id")            # numeric pk of one story
story_media_id = first_story.get("id") or (str(story_pk) if story_pk else None)  # full '<pk>_<uid>' media_id
if story_pk:
    # Fetch the viewers of one of YOUR OWN stories (works on stories you own)
    res = cl.story_viewers(story_pk, amount=20); show("story_viewers", res)
    # Fetch the people who liked one of YOUR OWN stories
    res = cl.story_likers(story_pk); show("story_likers", res)
else:
    show("story_viewers/story_likers", "skipped — no story items returned")

# resolve a highlight id from the user's highlights tray (guarded if empty)
first_highlight = highlights[0] if highlights else {}
highlight_id = first_highlight.get("id") or first_highlight.get("pk")  # e.g. 'highlight:17xxx' or '17xxx'
if highlight_id:
    # Fetch the full reel dict of one highlight (all its items)
    res = cl.highlight_info(highlight_id); show("highlight_info", res)
    # Fetch only the list of media items inside that highlight
    res = cl.highlight_items(highlight_id); show("highlight_items", res)
else:
    show("highlight_info/highlight_items", "skipped — user has no highlights")

section("Write examples (guarded)")
if RUN_WRITES:
    if story_pk:
        # Mark a list of story dicts as "seen" (records a view for each one)
        cl.story_seen([first_story])
        # Mark a single story as seen from its pk + the owner's user_id
        cl.story_seen_one(story_pk, uid)
    if story_media_id:
        # Like a story by its full media_id
        cl.story_like(story_media_id)
        # Remove the like from a story by its full media_id
        cl.story_unlike(story_media_id)
        # Vote on a poll sticker in a story (poll_id from the sticker; vote 0 or 1)
        cl.story_vote_poll(story_media_id, "POLL_STICKER_ID", 1)
        # Answer a quiz sticker in a story (quiz_id from the sticker; answer = choice index)
        cl.story_answer_quiz(story_media_id, "QUIZ_STICKER_ID", 0)
        # Respond to an emoji-slider sticker in a story (slider_id; vote 0.0-1.0)
        cl.story_vote_slider(story_media_id, "SLIDER_STICKER_ID", 0.5)
    # Create a new highlight from existing story media_ids (first one becomes the cover)
    new_highlight = cl.highlight_create("My API", ["111_222", "333_444"], cover_media_id="111_222"); show("highlight_create", new_highlight)
    # Edit a highlight: rename it, swap its cover, and add/remove media
    cl.highlight_edit(highlight_id or "highlight:17xxx", title="Renamed", cover_media_id="333_444", added_media_ids=["555_666"], removed_media_ids=["111_222"])
    # Delete a highlight by its id
    cl.highlight_delete(highlight_id or "highlight:17xxx")
else:
    writes_disabled_note()

print("\nStory examples done.")
