"""
App-like behavior -- make the *sequence* of calls look like a real session, not
just the individual requests.

Two things a real Instagram app does that a naive client doesn't:

1. **A navigation chain** (``X-IG-Nav-Chain``): every screen the user passes
   through is appended, so the server sees a believable path
   (``cold start -> feed -> profile -> ...``) instead of a context-free deep call.

2. **A cold-start warmup**: on app open it fetches the timeline, the story tray,
   the inbox and the current user *before* the user does anything. A session that
   pops into existence and immediately performs an action looks automated.

Everything here is best-effort and never raises -- warmup failures must not break
a login.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, List, Tuple

logger = logging.getLogger("okgram")

# A few real IG Android screen/module identifiers used to build the nav chain.
_SCREENS = {
    "cold_start": ("IgCdsScreenNavigationLoggerModule", "cold_start"),
    "feed": ("MainFeedFragment", "feed_timeline"),
    "stories": ("ReelViewerFragment", "reel_feed_timeline"),
    "inbox": ("DirectInboxFragment", "direct_inbox"),
    "notifications": ("NewsfeedFragment", "newsfeed_you"),
    "profile": ("UserDetailFragment", "profile"),
    "self_profile": ("SelfFragment", "self_profile"),
    "explore": ("ExploreFragment", "explore_popular"),
    "search": ("SearchFragment", "search"),
}


class NavChain:
    """Builds the ``X-IG-Nav-Chain`` header value from visited screens."""

    __slots__ = ("_entries", "_pos")

    def __init__(self) -> None:
        self._entries: List[Tuple[str, str, int, str, float]] = []
        self._pos = 0

    def push(self, screen_key: str, click_point: str = "button") -> "NavChain":
        module, screen = _SCREENS.get(screen_key, (screen_key, screen_key))
        self._pos += 1
        self._entries.append((module, screen, self._pos, click_point, time.time()))
        # keep the chain to the last ~10 hops like the app's bounded logger
        if len(self._entries) > 10:
            self._entries = self._entries[-10:]
        return self

    def render(self) -> str:
        # entry format: Module:screen:position:click_point:timestamp::
        parts = [
            f"{m}:{s}:{pos}:{cp}:{ts:.3f}::"
            for (m, s, pos, cp, ts) in self._entries
        ]
        return ",".join(parts)

    def __bool__(self) -> bool:
        return bool(self._entries)


def push_nav(client: Any, screen_key: str, click_point: str = "button") -> None:
    """Append a screen to the client's nav chain and refresh the header value."""
    chain = getattr(client, "_nav_chain_obj", None)
    if chain is None:
        chain = NavChain()
        client._nav_chain_obj = chain
    chain.push(screen_key, click_point)
    client.nav_chain = chain.render()


def human_pause(low: float = 0.6, high: float = 2.4) -> float:
    """A short, human-like pause between high-level actions."""
    delay = random.uniform(low, high)
    time.sleep(delay)
    return delay


def cold_start(client: Any, *, full: bool = True) -> dict:
    """
    Replay the app's cold-start sequence so the session looks freshly *opened*.

    Order mirrors the real client: nav=cold_start -> timeline(cold_start_fetch)
    -> reels tray -> inbox/notifications -> current user. Each step is optional and
    swallowed on error. Returns a small report of which steps ran.
    """
    report = {"ran": [], "failed": []}

    def step(name: str, fn) -> None:
        try:
            fn()
            report["ran"].append(name)
        except Exception as exc:  # noqa: BLE001 -- warmup must never break login
            report["failed"].append(name)
            logger.debug("cold_start step %s failed: %s", name, exc)

    push_nav(client, "cold_start", "cold_start")
    push_nav(client, "feed", "cold_start")

    if hasattr(client, "get_timeline_feed"):
        step("timeline", lambda: client.get_timeline_feed(reason="cold_start_fetch"))
        human_pause()

    if full and hasattr(client, "reels_tray"):
        push_nav(client, "stories")
        step("reels_tray", lambda: client.reels_tray())
        human_pause()

    if full and hasattr(client, "direct_inbox"):
        push_nav(client, "inbox")
        step("direct_inbox", lambda: client.direct_inbox())
        human_pause()
    elif full and hasattr(client, "get_direct_inbox"):
        push_nav(client, "inbox")
        step("direct_inbox", lambda: client.get_direct_inbox())
        human_pause()

    if full and hasattr(client, "get_recent_activity"):
        push_nav(client, "notifications")
        step("activity", lambda: client.get_recent_activity())
        human_pause()

    if hasattr(client, "get_current_user"):
        push_nav(client, "self_profile")
        step("current_user", lambda: client.get_current_user())

    logger.info("cold_start done: ran=%s failed=%s", report["ran"], report["failed"])
    return report
