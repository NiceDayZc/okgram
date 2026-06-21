# -*- coding: utf-8 -*-
"""Notifications/activity examples — demonstrates every NotificationMixin method."""
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

section("Read examples")
# Fetch our activity notification inbox (likes/comments/follows) (news/inbox/)
inbox = cl.news_inbox(); show("news_inbox", inbox)
# Fetch up to 10 of our notification stories (new + old, paginated)
stories = cl.news_inbox_stories(amount=10); show("news_inbox_stories", stories)
# Fetch only the counts section of the news inbox (likes, comments, relationships)
res = cl.news_inbox_counts(); show("news_inbox_counts", res)
# Fetch activity from accounts we follow (news/) — may be deprecated
res = cl.news_following(); show("news_following", res)
# Fetch up to 10 activity stories from accounts we follow (paginated)
res = cl.news_following_stories(amount=10); show("news_following_stories", res)
# Fetch/refresh the notifications screen badge counts (notifications/badge/)
res = cl.notification_badge(); show("notification_badge", res)
# Fetch the raw unread direct-message badge (direct_v2/get_badge_count/)
res = cl.direct_badge_count(); show("direct_badge_count", res)
# Convenience: the unread direct-message count as an int
res = cl.direct_unread_count(); show("direct_unread_count", res)
# Fetch combined activity counts (relationships, comments, likes, etc.)
res = cl.activity_count(); show("activity_count", res)
# Fetch current per-category notification settings (users/notification_preference/)
res = cl.notification_settings(); show("notification_settings", res)

# Resolve a target user id from IG_TARGET (used by the write example below)
uid = target_user_id(cl)

# Pull a story_id from the first inbox story (used by mark_story_seen below; guard if none)
story_id = ""
all_stories = list(inbox.get("new_stories") or []) + list(inbox.get("old_stories") or [])
if all_stories:
    story_id = all_stories[0].get("story_id") or all_stories[0].get("pk") or ""

section("Write examples (guarded)")
if RUN_WRITES:
    # Mark every notification in the inbox as seen/read
    res = cl.mark_news_seen(); show("mark_news_seen", res)
    if story_id:
        # Mark a single notification (story) as seen by its story_id
        res = cl.mark_story_seen(story_id); show("mark_story_seen", res)
    # Register a push token (FCM) so the device receives push notifications
    res = cl.push_register("EXAMPLE_FCM_DEVICE_TOKEN"); show("push_register", res)
    # Remove that push token again to stop receiving push notifications
    res = cl.push_unregister("EXAMPLE_FCM_DEVICE_TOKEN"); show("push_unregister", res)
    # Enable post notifications for a specific user (friendships/favorite/)
    res = cl.set_user_notification(uid, enable=True); show("set_user_notification(on)", res)
    # Disable post notifications for that user again (friendships/unfavorite/)
    res = cl.set_user_notification(uid, enable=False); show("set_user_notification(off)", res)
else:
    writes_disabled_note()

print("\nNotification examples done.")
