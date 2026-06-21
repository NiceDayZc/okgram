# -*- coding: utf-8 -*-
"""Direct/DM examples — demonstrates every DirectMixin method."""
from _common import get_client, login, section, show, RUN_WRITES, target_user_id, writes_disabled_note

cl = login(get_client())
uid = target_user_id(cl)   # a user to message / share (IG_TARGET)

section("Read examples")
# Fetch up to 5 inbox threads (direct_v2/inbox/)
threads = cl.direct_threads(amount=5); show("direct_threads", threads)
# Fetch one raw page of the inbox (with the oldest_cursor for paging)
res = cl.direct_inbox_page(); show("direct_inbox_page", res)
# Fetch up to 5 pending (message request) threads
res = cl.direct_pending_threads(amount=5); show("direct_pending_threads", res)
# Fetch one raw page of the pending (request) inbox
res = cl.direct_pending_inbox(); show("direct_pending_inbox", res)
# Number of pending message requests (badge count)
res = cl.direct_pending_count(); show("direct_pending_count", res)
# Search recipients/threads by query (ranked recipients)
res = cl.direct_search("john"); show("direct_search", res)
# Fetch suggested recipients without a query
res = cl.direct_ranked_recipients(); show("direct_ranked_recipients", res)
# Fetch the online status (presence) of people you've talked to
res = cl.direct_presence(); show("direct_presence", res)
# Find a thread whose participants match the given user_ids (use before sending)
res = cl.direct_thread_by_participants([uid]); show("direct_thread_by_participants", res)

# Pull a thread id (and a message item id) from the first inbox thread (guard if empty)
first_thread = threads[0] if threads else {}
tid = first_thread.get("thread_id", "")           # thread id of the first inbox thread
if tid:
    # Fetch one thread's details (direct_v2/threads/<id>/)
    res = cl.direct_thread(tid); show("direct_thread", res)
    # Fetch up to 10 messages (items) in the thread
    messages = cl.direct_messages(tid, amount=10); show("direct_messages", messages)
    item_id = (messages[0].get("item_id", "") if messages else "")  # id of a message item
else:
    show("direct_thread", "(skipped — no inbox thread available)")
    item_id = ""

section("Write examples (guarded)")
if RUN_WRITES:
    # Send a plain text message to a user
    cl.direct_send_text("Hello from the API", user_ids=[uid])
    # Send a message containing a link (shows a preview)
    cl.direct_send_link("Check this out", "https://example.com", user_ids=[uid])
    # Share a post (media) into direct by its full media id
    cl.direct_send_media_share("1234567890_1234567890", user_ids=[uid])
    # Share a post into direct by its bare pk
    cl.direct_send_media_share_by_pk("1234567890", user_ids=[uid])
    # Send a photo into direct (uploads the bytes first)
    cl.direct_send_photo("photo.jpg", user_ids=[uid])
    # Share a hashtag into direct
    cl.direct_send_hashtag("instagram", "Look at this tag", user_ids=[uid])
    # Share a user profile (profile card) into direct
    cl.direct_send_profile(uid, "Check this profile", user_ids=[uid])
    # Send a heart/like sticker into direct
    cl.direct_send_like(user_ids=[uid])

    if tid:
        # Send a 'typing' status to the thread
        cl.direct_send_typing_indicator(tid, activity=1)
        # Mark the latest message in the thread as seen
        if item_id:
            cl.direct_mark_seen(tid, item_id)
            # Delete (unsend) a message item in the thread
            cl.direct_message_delete(tid, item_id)
        # Mark the thread as unread again
        cl.direct_thread_mark_unread(tid)
        # Mute notifications for the thread
        cl.direct_thread_mute(tid)
        # Unmute notifications for the thread
        cl.direct_thread_unmute(tid)
        # Hide/remove the thread from the inbox
        cl.direct_thread_hide(tid)
        # Approve a pending message request thread
        cl.direct_thread_approve(tid)
        # Decline a pending message request thread
        cl.direct_thread_decline(tid)
        # Rename a group thread
        cl.direct_thread_update_title(tid, "New group title")
        # Add members to a group thread
        cl.direct_thread_add_users(tid, [uid])
        # Remove members from a group thread
        cl.direct_thread_remove_users(tid, [uid])
        # Leave a group thread
        cl.direct_thread_leave(tid)
else:
    writes_disabled_note()

print("\nDirect examples done.")
