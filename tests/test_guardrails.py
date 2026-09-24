from __future__ import annotations

from datetime import date

from app.guardrails import AnswerCache, QueryBudget


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_answer_cache_expires_entries() -> None:
    clock = Clock()
    cache: AnswerCache[str] = AnswerCache(ttl_seconds=10, max_entries=4, clock=clock)
    cache.put("q", "answer")

    clock.now = 9.9
    assert cache.get("q") == "answer"
    clock.now = 10.0
    assert cache.get("q") is None


def test_answer_cache_evicts_least_recently_used() -> None:
    cache: AnswerCache[int] = AnswerCache(ttl_seconds=60, max_entries=2, clock=Clock())
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)

    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_answer_cache_can_be_disabled_and_cleared() -> None:
    disabled: AnswerCache[int] = AnswerCache(ttl_seconds=0, max_entries=2)
    disabled.put("a", 1)
    assert disabled.get("a") is None

    cache: AnswerCache[int] = AnswerCache(ttl_seconds=60, max_entries=2)
    cache.put("a", 1)
    cache.clear()
    assert cache.get("a") is None


def test_query_budget_refills_per_minute() -> None:
    clock = Clock()
    budget = QueryBudget(per_minute=2, per_day=0, clock=clock, today=lambda: date(2026, 9, 23))

    assert budget.try_acquire() is None
    assert budget.try_acquire() is None
    retry_after = budget.try_acquire()
    assert retry_after is not None and 29 < retry_after <= 30

    clock.now = 30.0
    assert budget.try_acquire() is None


def test_query_budget_enforces_daily_ceiling_and_resets_next_day() -> None:
    day = {"value": date(2026, 9, 23)}
    budget = QueryBudget(per_minute=0, per_day=2, clock=Clock(), today=lambda: day["value"])

    assert budget.try_acquire() is None
    assert budget.try_acquire() is None
    assert budget.try_acquire() is not None

    day["value"] = date(2026, 9, 24)
    assert budget.try_acquire() is None


def test_query_budget_disabled_limits_always_allow() -> None:
    budget = QueryBudget(per_minute=0, per_day=0)
    assert all(budget.try_acquire() is None for _ in range(100))


def test_query_budget_reset_restores_capacity() -> None:
    budget = QueryBudget(per_minute=1, per_day=1, clock=Clock(), today=lambda: date(2026, 9, 23))
    assert budget.try_acquire() is None
    assert budget.try_acquire() is not None
    budget.reset()
    assert budget.try_acquire() is None
