# -*- coding: utf-8 -*-
"""Upload examples — demonstrates every UploadMixin method.

Every method here POSTS content to your account, so the whole file is a WRITE
demo guarded by RUN_WRITES. Set IG_RUN_WRITES=1 to actually run it, and make
sure the placeholder files below exist in your working directory:
    photo.jpg, video.mp4, cover.jpg, a.jpg, b.jpg
"""
from _common import get_client, login, section, show, RUN_WRITES, my_user_id, target_user_id, writes_disabled_note

cl = login(get_client())
me = my_user_id(cl)          # the logged-in account's user id
uid = target_user_id(cl)     # a user id to tag (mentions) in stories

section("Write examples (guarded) — every upload posts content")
if RUN_WRITES:
    # Upload one feed photo with a caption (rupload bytes + media/configure)
    res = cl.photo_upload("photo.jpg", "A single photo from the API"); show("photo_upload", res)
    # Upload one feed video with a caption and an explicit cover image
    res = cl.video_upload("video.mp4", "A single video from the API", thumbnail="cover.jpg"); show("video_upload", res)
    # Upload an album/carousel of multiple files as a single post (2-10 files)
    res = cl.album_upload(["a.jpg", "b.jpg"], "An album from the API"); show("album_upload", res)
    # Upload a photo to your story, tagging a user at the center via a mention sticker
    res = cl.photo_upload_to_story("photo.jpg", mentions=[{"user_id": uid, "x": 0.5, "y": 0.5}]); show("photo_upload_to_story", res)
    # Upload a video to your story (with cover) and a mention sticker placed at the center
    res = cl.video_upload_to_story("video.mp4", thumbnail="cover.jpg", mentions=[{"user_id": uid, "x": 0.5, "y": 0.5}]); show("video_upload_to_story", res)

    # --- low-level two-step flow: rupload (send bytes) -> configure (create post) ---
    # Step 1/2: send the raw photo bytes and get back an upload_id (no post created yet)
    photo_upload_id = cl.photo_rupload("photo.jpg"); show("photo_rupload", photo_upload_id)
    # Step 2/2: bind that upload_id to a caption to actually create the photo post
    res = cl.photo_configure(photo_upload_id, "Photo via the low-level configure step"); show("photo_configure", res)
    # Step 1/2: send the raw video bytes; returns (upload_id, width, height, duration_ms)
    video_upload_id, vw, vh, vdur = cl.video_rupload("video.mp4"); show("video_rupload", (video_upload_id, vw, vh, vdur))
    # Step 2/2: bind that upload_id (with its dimensions/duration) to create the video post
    res = cl.video_configure(video_upload_id, vw, vh, vdur, "Video via the low-level configure step"); show("video_configure", res)
    # story_configure: turn an already-ruploaded upload_id into a story (configure_to_story)
    story_upload_id = cl.photo_rupload("photo.jpg")  # rupload bytes first, then configure as a story
    res = cl.story_configure(story_upload_id, is_video=False, mentions=[{"user_id": uid, "x": 0.5, "y": 0.5}]); show("story_configure", res)

    # Upload an image and set it as the account's new profile picture
    res = cl.change_profile_picture("photo.jpg"); show("change_profile_picture", res)
else:
    writes_disabled_note()

print("\nUpload examples done.")
