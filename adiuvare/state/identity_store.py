import time
import threading
from dataclasses import dataclass

from cachetools import TTLCache


@dataclass
class IdentityWindow:
    """Track rolling per-identity state used by behavior, blocking, and monitored mode."""

    seen: int = 0
    score_ewma: float = 0.0
    blocked_until: float = 0.0
    monitored_remaining: int = 0
    monitored_multiplier: float = 1.0


class IdentityStore:
    """Keep short-lived identity windows in memory and apply block or monitor state."""

    def __init__(self, ttl: int = 300, block_ttl: int = 60) -> None:
        self._block_ttl = block_ttl
        self._windows: TTLCache[str, IdentityWindow] = TTLCache(maxsize=10000, ttl=ttl)
        self._lock = threading.RLock()

    def get(self, identity: str) -> IdentityWindow:
        with self._lock:
            win = self._windows.get(identity)
            if win is None:
                win = IdentityWindow()
                self._windows[identity] = win
            return win

    def update(self, identity: str, win: IdentityWindow) -> None:
        with self._lock:
            self._windows[identity] = win

    def items(self) -> list[tuple[str, IdentityWindow]]:
        with self._lock:
            return list(self._windows.items())

    def set_blocked(self, identity: str, seconds: int | float | None = None) -> None:
        win = self.get(identity)
        win.blocked_until = time.time() + (seconds or self._block_ttl)
        self.update(identity, win)

    def block(self, identity: str) -> None:
        self.set_blocked(identity)

    def clear_block(self, identity: str) -> None:
        win = self.get(identity)
        win.blocked_until = 0.0
        self.update(identity, win)

    def unblock(self, identity: str) -> None:
        self.clear_block(identity)

    def is_blocked(self, identity: str) -> bool:
        with self._lock:
            win = self._windows.get(identity)
            if win is None:
                return False

            if win.blocked_until <= time.time():
                win.blocked_until = 0.0
                self.update(identity, win)
                return False

            return True

    def bump(self, identity: str) -> int:
        win = self.get(identity)
        win.seen += 1
        self.update(identity, win)
        return win.seen

    def bump_and_maybe_block(self, identity: str, cap: int, block_ttl: float | None = None) -> tuple[int, bool]:
        """Atomically check-is-blocked → bump → conditionally set-blocked.

        Holds ``_lock`` across the full sequence so no two coroutines can
        both pass the is-blocked check and both increment before either
        applies the block.

        Returns:
            (seen, blocked_now) where *blocked_now* is True when this call
            is the one that pushed the count over *cap* (caller should
            return 429) or the identity was already blocked (caller should
            also return 429).
        """
        with self._lock:
            # is_blocked inline — no extra lock round-trip
            win = self._windows.get(identity)
            if win is None:
                win = IdentityWindow()
                self._windows[identity] = win

            if win.blocked_until > time.time():
                return win.seen, True
            win.blocked_until = 0.0  # expire stale block in-place

            # bump
            win.seen += 1

            # maybe block
            if win.seen > cap:
                win.blocked_until = time.time() + (
                    block_ttl if block_ttl is not None else self._block_ttl
                )
                self._windows[identity] = win
                return win.seen, True

            self._windows[identity] = win
            return win.seen, False

    def apply_score(self, identity: str, score: float, alpha: float = 0.35) -> IdentityWindow:
        """Blend the new score into EWMA and consume one monitored request if active."""

        win = self.get(identity)
        if win.score_ewma == 0.0:
            win.score_ewma = score
        else:
            win.score_ewma = (win.score_ewma * (1 - alpha)) + (score * alpha)
        if win.monitored_remaining > 0:
            win.monitored_remaining = max(0, win.monitored_remaining - 1)
            if win.monitored_remaining == 0:
                win.monitored_multiplier = 1.0
        self.update(identity, win)
        return win

    def set_monitored(
        self,
        identity: str,
        requests: int = 20,
        multiplier: float = 1.2,
    ) -> IdentityWindow:
        """Mark an identity for tighter scoring over the next few requests."""

        win = self.get(identity)
        win.monitored_remaining = max(0, int(requests))
        win.monitored_multiplier = max(1.0, float(multiplier))
        self.update(identity, win)
        return win

    def clear_monitored(self, identity: str) -> IdentityWindow:
        win = self.get(identity)
        win.monitored_remaining = 0
        win.monitored_multiplier = 1.0
        self.update(identity, win)
        return win

    def is_monitored(self, identity: str) -> bool:
        win = self.get(identity)
        return win.monitored_remaining > 0


class ThreadSafeIdentityStore(IdentityStore):
    """Wrap IdentityStore with an extra lock for threaded WSGI request handling."""

    def __init__(self, ttl: int = 300, block_ttl: int = 60) -> None:
        super().__init__(ttl=ttl, block_ttl=block_ttl)
        self._thread = threading.RLock()

    def get(self, identity: str) -> IdentityWindow:
        with self._thread:
            return super().get(identity)

    def update(self, identity: str, win: IdentityWindow) -> None:
        with self._thread:
            super().update(identity, win)

    def items(self) -> list[tuple[str, IdentityWindow]]:
        with self._thread:
            return super().items()

    def set_blocked(self, identity: str, seconds: int | float | None = None) -> None:
        with self._thread:
            super().set_blocked(identity, seconds)

    def clear_block(self, identity: str) -> None:
        with self._thread:
            super().clear_block(identity)

    def is_blocked(self, identity: str) -> bool:
        with self._thread:
            return super().is_blocked(identity)

    def bump(self, identity: str) -> int:
        with self._thread:
            return super().bump(identity)

    def bump_and_maybe_block(self, identity: str, cap: int, block_ttl: float | None = None) -> tuple[int, bool]:
        with self._thread:
            return super().bump_and_maybe_block(identity, cap, block_ttl)

    def apply_score(self, identity: str, score: float, alpha: float = 0.35) -> IdentityWindow:
        with self._thread:
            return super().apply_score(identity, score, alpha)