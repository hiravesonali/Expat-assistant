"""Input validation and usage limits for the public app (no Streamlit imports: pure and unit-tested).

Why limits at all: the deployed app is public and every Live answer is paid from one OpenRouter key.
Three layers, from weakest to strongest:
1. Per-browser-session limit (`SlidingWindowLimiter`): stops accidental loops and casual spamming. A reload
   starts a new session, so on its own it is not a security boundary.
2. Daily cap for the whole server process (`DailyCap`): bounds the worst case per day, whoever sends the
   questions. Resets on app reboot (it lives in memory), which is acceptable for a demo.
3. The credit limit on the OpenRouter key itself (set in the OpenRouter dashboard): the hard ceiling.
"""

from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import date

# Control characters except tab and newline (e.g. NUL, bell, escape sequences pasted from terminals).
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MANY_NEWLINES = re.compile(r"\n{3,}")


@dataclass(frozen=True)
class QuestionCheck:
    text: str  # the cleaned question (empty if invalid)
    error: str | None  # user-facing reason, None if valid


def check_question(raw: str | None, max_chars: int) -> QuestionCheck:
    """Clean a chat question and validate it: not empty, not just punctuation, at most `max_chars`."""
    text = _CONTROL_CHARS.sub("", (raw or "").replace("\r\n", "\n"))
    text = _MANY_NEWLINES.sub("\n\n", text).strip()
    if not text or not any(ch.isalnum() for ch in text):
        return QuestionCheck("", "Please type a question.")
    if len(text) > max_chars:
        return QuestionCheck(
            "", f"That message is {len(text):,} characters long; please keep questions under {max_chars:,}."
        )
    return QuestionCheck(text, None)


@dataclass
class SlidingWindowLimiter:
    """At most `max_events` within any `window_s` seconds (e.g. 20 questions per rolling hour)."""

    max_events: int
    window_s: float
    _times: deque[float] = field(default_factory=deque)

    def try_acquire(self, now: float) -> float | None:
        """Record an event and return None if allowed; otherwise return seconds until the next free slot."""
        while self._times and now - self._times[0] >= self.window_s:
            self._times.popleft()
        if len(self._times) >= self.max_events:
            return self.window_s - (now - self._times[0])
        self._times.append(now)
        return None


@dataclass
class DailyCap:
    """At most `max_per_day` events per calendar day, shared by all sessions (thread-safe)."""

    max_per_day: int
    _day: date | None = None
    _count: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def try_acquire(self, today: date) -> bool:
        with self._lock:
            if today != self._day:
                self._day, self._count = today, 0
            if self._count >= self.max_per_day:
                return False
            self._count += 1
            return True


def estimate_cost_usd(input_tokens: int, output_tokens: int, price_in: float, price_out: float) -> float:
    """Cost from token counts and prices in USD per million tokens."""
    return (input_tokens * price_in + output_tokens * price_out) / 1_000_000
