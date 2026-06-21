# -*- coding: utf-8 -*-
"""
Live broadcast examples — demonstrates every LiveMixin method.

Creating/starting/ending a live and every live interaction are WRITE actions,
so the whole flow is guarded behind RUN_WRITES. The info/comment readers all need
a real broadcast_id, which only exists once you have created a live — so they are
shown inside the same guarded flow.
"""
from _common import (
    get_client,
    login,
    section,
    show,
    RUN_WRITES,
    writes_disabled_note,
)

cl = login(get_client())

section("Live broadcast flow (guarded)")
if RUN_WRITES:
    # Reserve a new live channel — returns broadcast_id + the RTMP upload_url
    broadcast = cl.live_create(preview_width=1080, preview_height=1920, message="Going live!")
    show("live_create", broadcast)
    bid = broadcast.get("broadcast_id") or ""   # the id used for every live action below

    if bid:
        # Start the live (after you begin pushing the stream to the RTMP url)
        show("live_start", cl.live_start(bid, send_notifications=True))
        # Fetch the live's current info (status, broadcaster, viewer count, etc.)
        show("live_info", cl.live_info(bid))
        # Send a heartbeat and get back the current viewer count
        show("live_heartbeat", cl.live_heartbeat(bid))
        # Convenience: just the current viewer count as an int
        show("live_viewer_count", cl.live_viewer_count(bid))
        # Fetch the current list of viewers (list of user dicts)
        show("live_viewers", cl.live_viewers(bid))
        # Fetch people requesting to join the live ("live with")
        show("live_join_requests", cl.live_join_requests(bid))

        # Enable comments on the live
        show("live_enable_comments", cl.live_enable_comments(bid))
        # Post a comment to the live and read it back
        comment = cl.live_comment(bid, "Hello everyone!"); show("live_comment", comment)
        cmt_id = comment.get("pk") or comment.get("id") or ""   # id of the comment we posted
        # Fetch the live's recent comments (list of comment dicts)
        show("live_comments", cl.live_comments(bid))
        if cmt_id:
            # Pin our comment to the top of the live (owner only)
            show("live_pin_comment", cl.live_pin_comment(bid, cmt_id))
            # Unpin that comment again
            show("live_unpin_comment", cl.live_unpin_comment(bid, cmt_id))
        # Disable comments on the live
        show("live_disable_comments", cl.live_disable_comments(bid))

        # Send 5 likes (hearts) into the live
        show("live_like", cl.live_like(bid, count=5))
        # Fetch the live's current like count
        show("live_like_count", cl.live_like_count(bid))
        # Wave to a specific viewer (using our own id here as a placeholder viewer)
        show("live_wave", cl.live_wave(bid, str(cl.user_id)))

        # End the live broadcast
        show("live_end", cl.live_end(bid))

        # Now that it has ended, read the post-live (replay) info
        show("live_post_info", cl.live_post_info(bid))
        # Read up to 20 comments captured during the ended live
        show("live_post_comments", cl.live_post_comments(bid, amount=20))
        # Fetch the final viewer list recorded after the live ended
        show("live_get_final_viewer_list", cl.live_get_final_viewer_list(bid))
else:
    writes_disabled_note()

print("\nLive examples done.")
