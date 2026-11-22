from datetime import date

from expat.guards import DailyCap, SlidingWindowLimiter, check_question, estimate_cost_usd


def test_question_is_cleaned():
    check = check_question("  Wie melde ich\x00 mich an?\r\n\n\n\nDanke  ", max_chars=100)
    assert check.error is None
    assert check.text == "Wie melde ich mich an?\n\nDanke"


def test_empty_or_punctuation_only_questions_are_rejected():
    for raw in (None, "", "   ", "\n\n", "???", "…"):
        assert check_question(raw, max_chars=100).error == "Please type a question."


def test_too_long_question_is_rejected_with_its_length():
    check = check_question("a" * 1001, max_chars=1000)
    assert check.text == "" and "1,001 characters" in check.error and "1,000" in check.error


def test_sliding_window_allows_n_per_window_then_reports_wait():
    limiter = SlidingWindowLimiter(max_events=2, window_s=3600)
    assert limiter.try_acquire(0) is None
    assert limiter.try_acquire(10) is None
    assert limiter.try_acquire(20) == 3600 - 20  # the slot from t=0 frees up at t=3600
    assert limiter.try_acquire(3600) is None  # first event has left the window


def test_daily_cap_resets_on_a_new_day():
    cap = DailyCap(max_per_day=2)
    day1, day2 = date(2026, 11, 22), date(2026, 11, 23)
    assert cap.try_acquire(day1) and cap.try_acquire(day1)
    assert not cap.try_acquire(day1)
    assert cap.try_acquire(day2)


def test_cost_estimate():
    assert estimate_cost_usd(10_000, 1_000, price_in=0.40, price_out=1.60) == (4_000 + 1_600) / 1_000_000
