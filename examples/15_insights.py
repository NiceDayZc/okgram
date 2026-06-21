# -*- coding: utf-8 -*-
"""
Insights examples — demonstrates every InsightsMixin method.

IMPORTANT: insights work ONLY for a professional account (business / creator).
On a personal account Instagram rejects these endpoints, so every call below is
wrapped in try/except ClientError to print a friendly note instead of crashing.
"""
from _common import (
    get_client,
    login,
    section,
    show,
    my_user_id,
    first_media_of,
    ClientError,
)


def safe(label, func, *args, **kwargs):
    """Run a read-only insights call and print the result, or a friendly note on error."""
    try:
        show(label, func(*args, **kwargs))
    except ClientError as exc:
        show(label, f"(unavailable — needs a professional account: {exc})")


cl = login(get_client())
me = my_user_id(cl)   # the logged-in account's user id

# Grab one of our own posts (insights only work on your own media)
my_media = first_media_of(cl, me)
media_id = my_media.get("id") or ""          # full media_id '<pk>_<uid>' of our first post
media_pk = my_media.get("pk") or ""          # bare pk of our first post
media_code = my_media.get("code") or ""      # shortcode used to build a post url

section("Account insights (read)")
# Overview of organic account insights (insights/account_organic_insights/)
safe("insights_account", cl.insights_account, first=30)
# Summarized account insights (falls back to the organic overview if absent)
safe("insights_account_summary", cl.insights_account_summary)
# Convenience: total account reach pulled from the insights dict
safe("account_reach", cl.account_reach, first=30)
# Convenience: total account impressions pulled from the insights dict
safe("account_impressions", cl.account_impressions, first=30)

section("Media insights (read)")
if media_id:
    # Insights for a single post by full media_id (insights/media_organic_insights/)
    safe("insights_media", cl.insights_media, media_id)
    # Convenience: a post's reach value pulled from its insights
    safe("media_reach", cl.media_reach, media_id)
    # Convenience: a post's impressions value pulled from its insights
    safe("media_impressions", cl.media_impressions, media_id)
    # Convenience: a post's engagement value pulled from its insights
    safe("media_engagement", cl.media_engagement, media_id)
    # Convenience: a post's saves value pulled from its insights
    safe("media_saves", cl.media_saves, media_id)
else:
    show("insights_media", "(skipped — no media found on this account)")

if media_pk:
    # Insights for a post from a bare pk (user_id appended automatically)
    safe("insights_media_by_pk", cl.insights_media_by_pk, media_pk)
else:
    show("insights_media_by_pk", "(skipped — no media pk available)")

if media_code:
    # Insights for a post from its public url (/p/<code>/)
    safe("insights_media_by_url", cl.insights_media_by_url, f"https://www.instagram.com/p/{media_code}/")
else:
    show("insights_media_by_url", "(skipped — no media shortcode available)")

# Insights for all posts at once, ranked by reach over the last week (paginated)
safe("insights_media_feed_all", cl.insights_media_feed_all, "ONE_WEEK", "REACH_COUNT", 20, 10)

section("Story insights (read)")
if media_id:
    # Insights for a single story by id (works only within ~14 days of posting)
    safe("insights_story", cl.insights_story, media_id)
    # Insights for several stories at once (unfetchable ones are skipped)
    safe("insights_stories_all", cl.insights_stories_all, [media_id])
else:
    show("insights_story", "(skipped — no media/story id available)")

print("\nInsights examples done.")
