"""
Tests for the atomic bump_and_maybe_block fix (issue #160).

Covers:
  - Single-threaded regression: existing boundary semantics preserved
  - Concurrency: 50 tasks at cap-1 must produce at most 1 passing request
  - ThreadSafeIdentityStore: same atomic guarantee under threading
  - Pre-existing block: returns identity_blocked reason (not rate_limit_hit)
  - bump_and_maybe_block direct unit tests
"""

import asyncio
import threading
import time

import pytest

from adiuvare.core.gate import run_trackA, trackA_cap
from adiuvare.core.models import RequestContext
from adiuvare.state.identity_store import IdentityStore, ThreadSafeIdentityStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx(identity: str = "u1") -> RequestContext:
    return RequestContext(
        identity=identity,
        payload=None,
        url="/",
        method="GET",
        headers={},
        ip="127.0.0.1",
        endpoint="/",
    )


# ---------------------------------------------------------------------------
# Unit tests for bump_and_maybe_block
# ---------------------------------------------------------------------------

class TestBumpAndMaybeBlock:
    def test_returns_seen_and_false_below_cap(self):
        store = IdentityStore()
        seen, blocked = store.bump_and_maybe_block("u1", cap=5)
        assert seen == 1
        assert blocked is False

    def test_returns_blocked_true_when_over_cap(self):
        store = IdentityStore()
        for _ in range(5):
            store.bump_and_maybe_block("u1", cap=5)
        seen, blocked = store.bump_and_maybe_block("u1", cap=5)
        assert seen == 6
        assert blocked is True

    def test_already_blocked_identity_returns_blocked_true(self):
        store = IdentityStore()
        store.set_blocked("u1", seconds=60)
        seen, blocked = store.bump_and_maybe_block("u1", cap=200)
        assert blocked is True
        # seen must not have been incremented on an already-blocked identity
        win = store.get("u1")
        assert win.seen == 0

    def test_block_applied_and_persists(self):
        store = IdentityStore()
        for _ in range(200):
            store.bump_and_maybe_block("u1", cap=200)
        _, blocked = store.bump_and_maybe_block("u1", cap=200)
        assert blocked is True
        assert store.is_blocked("u1") is True

    def test_custom_block_ttl_respected(self):
        store = IdentityStore(block_ttl=9999)
        for _ in range(3):
            store.bump_and_maybe_block("u1", cap=3)
        store.bump_and_maybe_block("u1", cap=3, block_ttl=0.01)
        time.sleep(0.02)
        assert store.is_blocked("u1") is False

    def test_expired_block_cleared_and_request_passes(self):
        store = IdentityStore()
        store.set_blocked("u1", seconds=0.01)
        time.sleep(0.02)
        seen, blocked = store.bump_and_maybe_block("u1", cap=200)
        assert blocked is False
        assert seen == 1


# ---------------------------------------------------------------------------
# Single-threaded gate regression
# ---------------------------------------------------------------------------

class TestGateRegressionSingleThreaded:
    def test_exactly_200_requests_all_pass(self):
        store = IdentityStore()
        ctx = make_ctx()
        results = [run_trackA(ctx, store) for _ in range(200)]
        assert all(r.passed for r in results)

    def test_201st_request_blocked_with_rate_limit_hit(self):
        store = IdentityStore()
        ctx = make_ctx()
        for _ in range(200):
            run_trackA(ctx, store)
        res = run_trackA(ctx, store)
        assert res.passed is False
        assert res.status_code == 429
        assert res.block_reason == "rate_limit_hit"

    def test_pre_existing_block_returns_identity_blocked(self):
        store = IdentityStore()
        store.set_blocked("u1", seconds=60)
        res = run_trackA(make_ctx("u1"), store)
        assert res.passed is False
        assert res.block_reason == "identity_blocked"

    def test_separate_identities_tracked_independently(self):
        store = IdentityStore()
        ctx_a = make_ctx("alice")
        for _ in range(201):
            run_trackA(ctx_a, store)
        assert store.is_blocked("alice") is True
        res = run_trackA(make_ctx("bob"), store)
        assert res.passed is True


# ---------------------------------------------------------------------------
# Concurrency tests — async (event-loop)
# ---------------------------------------------------------------------------

class TestConcurrentAsyncAtomicity:
    @pytest.mark.asyncio
    async def test_at_most_one_request_passes_at_boundary(self):
        """
        50 coroutines all call run_trackA when seen is at cap-1 (199).
        After the fix, at most 1 should pass; previously all 50 would pass.
        """
        store = IdentityStore()
        ctx = make_ctx("burst_user")

        for _ in range(199):
            seen, blocked = store.bump_and_maybe_block("burst_user", trackA_cap())
            assert not blocked

        async def one_request():
            await asyncio.sleep(0)
            return run_trackA(ctx, store)

        results = await asyncio.gather(*[one_request() for _ in range(50)])
        passed = [r for r in results if r.passed]

        assert len(passed) == 1, (
            f"Expected at most 1 passing request at the boundary, got {len(passed)}"
        )

    @pytest.mark.asyncio
    async def test_no_request_passes_when_already_at_cap(self):
        store = IdentityStore()
        ctx = make_ctx("over_cap_user")

        for _ in range(200):
            store.bump_and_maybe_block("over_cap_user", trackA_cap())

        async def one_request():
            await asyncio.sleep(0)
            return run_trackA(ctx, store)

        results = await asyncio.gather(*[one_request() for _ in range(50)])
        passed = [r for r in results if r.passed]
        assert len(passed) == 0

    @pytest.mark.asyncio
    async def test_seen_count_does_not_exceed_cap_plus_one(self):
        store = IdentityStore()
        ctx = make_ctx("seen_count_user")

        for _ in range(199):
            store.bump_and_maybe_block("seen_count_user", trackA_cap())

        async def one_request():
            await asyncio.sleep(0)
            run_trackA(ctx, store)

        await asyncio.gather(*[one_request() for _ in range(50)])
        win = store.get("seen_count_user")
        assert win.seen <= trackA_cap() + 1, (
            f"seen={win.seen} exceeded cap+1={trackA_cap() + 1}"
        )


# ---------------------------------------------------------------------------
# Concurrency tests — threading (ThreadSafeIdentityStore)
# ---------------------------------------------------------------------------

class TestConcurrentThreadedAtomicity:
    def test_thread_safe_store_at_most_one_passes_at_boundary(self):
        store = ThreadSafeIdentityStore()
        ctx = make_ctx("thread_burst_user")

        for _ in range(199):
            store.bump_and_maybe_block("thread_burst_user", trackA_cap())

        results: list = []
        lock = threading.Lock()

        def one_request():
            res = run_trackA(ctx, store)
            with lock:
                results.append(res)

        threads = [threading.Thread(target=one_request) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        passed = [r for r in results if r.passed]
        assert len(passed) == 1, (
            f"Expected at most 1 passing request at boundary, got {len(passed)}"
        )

    def test_thread_safe_store_seen_count_bounded(self):
        store = ThreadSafeIdentityStore()
        ctx = make_ctx("ts_seen_user")

        for _ in range(199):
            store.bump_and_maybe_block("ts_seen_user", trackA_cap())

        def one_request():
            run_trackA(ctx, store)

        threads = [threading.Thread(target=one_request) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        win = store.get("ts_seen_user")
        assert win.seen <= trackA_cap() + 1

    def test_thread_safe_bump_and_maybe_block_direct(self):
        store = ThreadSafeIdentityStore()
        results = []
        lock = threading.Lock()

        def do_bump():
            seen, blocked = store.bump_and_maybe_block("ts_direct", cap=10)
            with lock:
                results.append((seen, blocked))

        threads = [threading.Thread(target=do_bump) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        passed = [(s, b) for s, b in results if not b]
        blocked = [(s, b) for s, b in results if b]
        assert len(passed) == 10
        assert len(blocked) == 10
        # Each passing call must have received a unique seen value (1..10).
        # Blocked calls all return the same frozen seen count — uniqueness
        # only applies to the passing subset.
        passing_seen = [s for s, b in results if not b]
        assert len(passing_seen) == len(set(passing_seen)), (
            f"Duplicate seen values among passing calls: {passing_seen}"
        )