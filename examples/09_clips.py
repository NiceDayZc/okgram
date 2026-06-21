# -*- coding: utf-8 -*-
"""Clips/Reels & IGTV examples — demonstrates every ClipsMixin method."""
from _common import get_client, login, section, show, RUN_WRITES, target_user_id, writes_disabled_note

cl = login(get_client())
uid = target_user_id(cl)   # a public account to read (IG_TARGET)

section("Read examples")
# Fetch up to 5 of the target user's Reels (clips/user/)
clips = cl.user_clips(uid, amount=5); show("user_clips", clips)
# Fetch the suggested Reels feed (clips/discover/), capped to a few items
res = cl.clips_discover(amount=5); show("clips_discover", res)

# Pull a reel id and an audio/music id from the first fetched clip (guard if none)
clip = clips[0] if clips else {}
clip_id = clip.get("pk") or clip.get("id") or ""           # bare pk of the first reel
audio_id = ((clip.get("clips_metadata") or {}).get("music_info") or {}) \
    .get("music_asset_info", {}).get("audio_cluster_id", "")  # audio id from the reel's metadata

if clip_id:
    # Fetch a single reel's full info by its media id (media/<id>/info/)
    res = cl.clip_info(clip_id); show("clip_info", res)
    # Fetch a single reel's info from a bare pk (binds the current user id)
    res = cl.clip_info_by_pk(clip_id); show("clip_info_by_pk", res)
else:
    show("clip_info", "(skipped — no reel found for target user)")

if audio_id:
    # Fetch other Reels that use the same audio/music track (clips/music/)
    res = cl.clips_by_music(audio_id, amount=5); show("clips_by_music", res)
    # Fetch audio/music details from its id (music/audio_by_canonical_id/)
    res = cl.music_by_id(audio_id); show("music_by_id", res)
else:
    show("clips_by_music", "(skipped — no audio id on the first reel)")

# Search audio/music tracks you could use in a reel (music/search/)
tracks = cl.music_search("song"); show("music_search", tracks)

# Fetch one page of the target user's IGTV channel (igtv/channel/)
res = cl.igtv_channel(uid); show("igtv_channel", res)
# Fetch up to 5 of the target user's IGTV videos (paginated)
res = cl.igtv_videos(uid, amount=5); show("igtv_videos", res)

section("Write examples (guarded)")
if RUN_WRITES:
    if clip_id:
        # Mark the reel as viewed/seen (clips/item/seen/)
        cl.clip_seen(clip_id, view_duration=5.0)
        # Like the reel (media/<id>/like/)
        cl.clip_like(clip_id)
        # Unlike the reel again (media/<id>/unlike/)
        cl.clip_unlike(clip_id)
        # Post a comment on the reel (media/<id>/comment/)
        cl.clip_comment(clip_id, "Nice reel!")
    # End-to-end reel upload: upload the video bytes then configure_to_clips
    cl.clip_upload("reel.mp4", "My reel caption")
    # Low-level: configure a reel whose bytes are already uploaded (needs an upload_id)
    cl.clip_configure("UPLOAD_ID_HERE", "My reel caption")
    # End-to-end IGTV upload: upload the video bytes then configure_to_igtv
    cl.igtv_upload("video.mp4", "My IGTV title", "My IGTV caption")
    # Low-level: configure an IGTV video whose bytes are already uploaded (needs an upload_id)
    cl.igtv_configure("UPLOAD_ID_HERE", "My IGTV title", "My IGTV caption")
else:
    writes_disabled_note()

print("\nClips examples done.")
