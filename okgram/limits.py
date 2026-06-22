"""
Human-like rate governor -- the brake that stops ``feedback_required`` / action
blocks (the *other* way an account gets "bounced").

Instagram does not just look at TLS/headers; it watches *cadence*. Firing 300
likes or 80 follows in an hour is the clearest possible automation signal. The
:class:`RateGovernor` enforces conservative, human-like limits per action class:

- a rolling **per-hour** and **per-day** cap for each action (like / follow / dm …)
- a randomised **think-time** before each action (no machine-gun bursts)
- an optional **sleep window** (local hours where a human wouldn't be active)
- a **cool-down** that backs off automatically when IG returns ``feedback_required``

It is opt-in (``InstagramAPI(govern=True)`` or ``cl.enable_governor()``), wired into
the request chokepoint so only *write* actions are gated -- reads pass straight
through. Counts persist in the session bundle, so caps survive restarts.
"""
from __future__ import annotations

import logging
import random
import time
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from .exceptions import RateLimitReached

logger = logging.getLogger("okgram")

#: action -> (per_hour, per_day). Deliberately conservative -- raise at your own risk.
DEFAULT_LIMITS: Dict[str, Tuple[int, int]] = {
    "like":         (60, 500),
    "unlike":       (60, 500),
    "follow":       (30, 150),
    "unfollow":     (30, 150),
    "comment":      (30, 200),
    "comment_like": (60, 500),
    "comment_unlike": (60, 500),
    "dm":           (40, 200),
    "save":         (60, 600),
    "block":        (20, 100),
    "story_seen":   (300, 3000),
    "media_seen":   (300, 3000),
    "upload":       (10, 50),
    "default_write": (80, 1000),
}

#: endpoint substring -> action class. First match wins; anything that matches no
#: write pattern is treated as a READ and is never gated (feed/timeline is a POST
#: but a read, so it must stay exempt).
ENDPOINT_ACTION: List[Tuple[str, str]] = [
    ("comment_unlike", "comment_unlike"),   # before comment_like / comment/
    ("comment_like", "comment_like"),
    ("comment/", "comment"),          # media/<id>/comment/  (post a comment)
    ("/like/", "like"),
    ("/unlike/", "unlike"),
    ("friendships/create", "follow"),
    ("friendships/destroy", "unfollow"),
    ("friendships/block", "block"),
    ("friendships/unblock", "block"),
    ("direct_v2/threads/broadcast", "dm"),
    ("direct_v2/", "dm"),
    ("/save/", "save"),
    ("/unsave/", "save"),
    ("seen", "media_seen"),
    ("configure", "upload"),
    ("rupload", "upload"),
]

_HOUR = 3600.0
_DAY = 86400.0


class RateGovernor:
    """Per-action rolling-window limiter with think-time, sleep window and cooldown."""

    def __init__(
        self,
        limits: Optional[Dict[str, Tuple[int, int]]] = None,
        *,
        timezone_offset: int = 0,
        think_time: Tuple[float, float] = (0.8, 3.0),
        sleep_window: Optional[Tuple[int, int]] = None,
        mode: str = "sleep",
        max_block_wait: float = 300.0,
        enabled: bool = True,
    ):
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self.timezone_offset = timezone_offset
        self.think_time = think_time
        self.sleep_window = sleep_window          # e.g. (1, 6) -> 01:00..05:59 local
        self.mode = mode                          # "sleep" (wait) or "raise"
        self.max_block_wait = max_block_wait      # never block longer than this; raise instead
        self.enabled = enabled
        self._events: Dict[str, Deque[float]] = {}
        self._cooldown_until = 0.0
        self._consecutive_blocks = 0

    # -- classification --------------------------------------------------
    def classify(self, endpoint: str) -> Optional[str]:
        ep = (endpoint or "").lower()
        for needle, action in ENDPOINT_ACTION:
            if needle in ep:
                return action
        return None

    # -- counting --------------------------------------------------------
    def _bucket(self, action: str) -> Deque[float]:
        return self._events.setdefault(action, deque())

    def _prune(self, action: str, now: float) -> None:
        b = self._bucket(action)
        cutoff = now - _DAY
        while b and b[0] < cutoff:
            b.popleft()

    def counts(self, action: str, now: Optional[float] = None) -> Tuple[int, int]:
        now = now if now is not None else time.time()
        self._prune(action, now)
        b = self._bucket(action)
        hour = sum(1 for t in b if t >= now - _HOUR)
        return hour, len(b)

    def remaining(self, action: str) -> Tuple[int, int]:
        per_hour, per_day = self.limits.get(action, self.limits["default_write"])
        h, d = self.counts(action)
        return max(0, per_hour - h), max(0, per_day - d)

    def record(self, action: str, now: Optional[float] = None) -> None:
        self._bucket(action).append(now if now is not None else time.time())

    # -- sleep window ----------------------------------------------------
    def local_hour(self, now: Optional[float] = None) -> int:
        now = now if now is not None else time.time()
        return int(((now + self.timezone_offset) % _DAY) // _HOUR)

    def in_sleep_window(self, now: Optional[float] = None) -> bool:
        if not self.sleep_window:
            return False
        start, end = self.sleep_window
        h = self.local_hour(now)
        if start <= end:
            return start <= h < end
        return h >= start or h < end       # window wraps midnight

    # -- cooldown (set on feedback_required / throttle) ------------------
    def note_block(self, seconds: Optional[float] = None) -> float:
        self._consecutive_blocks += 1
        if seconds is None:
            # exponential backoff: 5m, 10m, 20m ... capped at 6h
            seconds = min(300 * (2 ** (self._consecutive_blocks - 1)), 6 * _HOUR)
        self._cooldown_until = time.time() + seconds
        logger.warning("rate governor: cooldown %.0fs (block #%d)", seconds, self._consecutive_blocks)
        return seconds

    def note_success(self) -> None:
        self._consecutive_blocks = 0

    # -- the gate --------------------------------------------------------
    def _wait_or_raise(self, seconds: float, why: str) -> None:
        if seconds <= 0:
            return
        if self.mode == "raise" or seconds > self.max_block_wait:
            raise RateLimitReached(f"{why} (need ~{seconds:.0f}s)")
        logger.info("rate governor: waiting %.1fs (%s)", seconds, why)
        time.sleep(seconds)

    def gate(self, endpoint: str) -> Optional[str]:
        """Enforce limits for ``endpoint``. Returns the action class (or None if a
        read / not gated). Sleeps or raises :class:`RateLimitReached` per ``mode``."""
        if not self.enabled:
            return None
        action = self.classify(endpoint)
        if action is None:
            return None

        now = time.time()

        # 1) active cooldown from a previous block
        if now < self._cooldown_until:
            self._wait_or_raise(self._cooldown_until - now, "feedback cooldown")
            now = time.time()

        # 2) sleep window -- never hang for hours; raise so the caller backs off
        if self.in_sleep_window(now):
            raise RateLimitReached(
                f"within sleep window {self.sleep_window} (local hour {self.local_hour(now)})"
            )

        # 3) hourly / daily caps
        per_hour, per_day = self.limits.get(action, self.limits["default_write"])
        self._prune(action, now)
        b = self._bucket(action)
        day_count = len(b)
        if day_count >= per_day:
            wait = _DAY - (now - b[0])
            self._wait_or_raise(wait, f"{action} daily cap {per_day}")
            now = time.time()
        hour_events = [t for t in b if t >= now - _HOUR]
        if len(hour_events) >= per_hour:
            wait = _HOUR - (now - hour_events[0])
            self._wait_or_raise(wait, f"{action} hourly cap {per_hour}")

        # 4) human think-time
        if self.think_time:
            time.sleep(random.uniform(*self.think_time))

        self.record(action)
        return action

    # -- persistence -----------------------------------------------------
    def to_dict(self) -> dict:
        now = time.time()
        return {
            "events": {a: [t for t in b if t >= now - _DAY] for a, b in self._events.items()},
            "cooldown_until": self._cooldown_until,
            "consecutive_blocks": self._consecutive_blocks,
        }

    def load_dict(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        now = time.time()
        for action, times in (data.get("events") or {}).items():
            self._events[action] = deque(t for t in times if t >= now - _DAY)
        self._cooldown_until = data.get("cooldown_until", 0.0) or 0.0
        self._consecutive_blocks = data.get("consecutive_blocks", 0) or 0
