# -*- coding: utf-8 -*-
"""
Example 05 — CommentMixin

Demonstrates every method of the CommentMixin: reading comments and their
replies (with pagination), inspecting who liked a comment, and the full set
of WRITE/destructive actions (write/reply/like/unlike/delete/bulk-delete/
pin/unpin/enable/disable) which only run when IG_RUN_WRITES=1.

Usage:
    python examples/05_comment.py
    IG_RUN_WRITES=1 python examples/05_comment.py   # enable WRITE actions
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

    # ------------------------------------------------------------------
    # Resolve a target user and one of their media to work with
    # ------------------------------------------------------------------
    section("Resolve target user + sample media")
    uid = target_user_id(cl)                       # IG_TARGET username -> user id
    show("my_user_id", my_user_id(cl))             # the logged-in account id
    show("target_user_id", uid)                    # the account we will read
    media = first_media_of(cl, uid)                # first post of that account
    mid = media.get("id") or media.get("pk")       # media id (full '<pk>_<uid>' or pk)
    show("media_id", mid)

    if not mid:
        print("  (no media found for target — cannot demo comment methods)")
        print("done")
        return

    # ------------------------------------------------------------------
    # READ: fetch comments (paged + convenience list)
    # ------------------------------------------------------------------
    section("Read comments")
    page = cl.media_comments_page(mid)                          # one raw page of comments
    show("media_comments_page.keys", list(page.keys()))
    show("media_comments_page.next_max_id", page.get("next_max_id"))

    comments = cl.media_comments(mid, amount=10)                # up to 10 comments as a list
    show("media_comments count", len(comments))

    # grab a comment_id to use in the comment-specific methods below (guard if empty)
    comment_id = comments[0].get("pk") if comments else None
    show("first comment_id", comment_id)

    # ------------------------------------------------------------------
    # READ: replies, likers, info for a specific comment
    # ------------------------------------------------------------------
    section("Read replies / likers / info for one comment")
    if comment_id:
        replies = cl.comment_replies(mid, comment_id, amount=5)   # child comments (replies)
        show("comment_replies count", len(replies))

        likers = cl.comment_likers(comment_id)                    # users who liked the comment
        show("comment_likers count", len(likers))

        info = cl.comment_info(mid, comment_id)                   # single comment looked up by pk
        show("comment_info.text", info.get("text"))
    else:
        print("  (no comments on this media — skipping reply/likers/info reads)")

    # ------------------------------------------------------------------
    # WRITE / destructive actions (guarded by IG_RUN_WRITES)
    # ------------------------------------------------------------------
    section("WRITE actions (guarded)")
    if RUN_WRITES:
        # write a new top-level comment on the media
        new_comment = cl.media_comment(mid, "Nice post! (demo)")
        new_comment_id = new_comment.get("pk")
        show("media_comment -> pk", new_comment_id)

        if new_comment_id:
            # reply to the comment we just created
            reply = cl.reply_to_comment(mid, "Replying to my own comment (demo)", new_comment_id)
            reply_id = reply.get("pk")
            show("reply_to_comment -> pk", reply_id)

            # like then unlike our new comment
            show("comment_like", cl.comment_like(new_comment_id))
            show("comment_unlike", cl.comment_unlike(new_comment_id))

            # pin then unpin our new comment (post owner only)
            show("comment_pin", cl.comment_pin(mid, new_comment_id))
            show("comment_unpin", cl.comment_unpin(mid, new_comment_id))

            # delete the reply, then bulk-delete the top-level comment
            if reply_id:
                show("comment_delete", cl.comment_delete(mid, reply_id))
            show("comment_bulk_delete", cl.comment_bulk_delete(mid, [new_comment_id]))

        # turn commenting off then back on for this media (post owner only)
        show("disable_comments", cl.disable_comments(mid))
        show("enable_comments", cl.enable_comments(mid))
    else:
        writes_disabled_note()

    print("done")


if __name__ == "__main__":
    main()
