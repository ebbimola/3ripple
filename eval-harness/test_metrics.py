"""The estimators are code too. Check them against values you can work out by hand.

    pytest test_metrics.py
"""

import pytest

from metrics import fail_rate_upper, pass_at_k, pass_hat_k


def test_pass_hat_k_matches_the_combinatorial_count():
    # 16 passes in 20 trials, k = 4: C(16,4) / C(20,4) = 1820 / 4845
    assert pass_hat_k(20, 16, 4) == pytest.approx(1820 / 4845)


def test_pass_hat_k_is_below_the_naive_power_at_small_n():
    assert pass_hat_k(20, 16, 4) < 0.8 ** 4


def test_pass_at_k_is_one_when_failures_are_fewer_than_k():
    assert pass_at_k(20, 19, 4) == 1.0


@pytest.mark.parametrize("n, bound", [(20, 0.139), (100, 0.030), (300, 0.0099)])
def test_zero_failures_bound_matches_closed_form(n, bound):
    # With no failures the Clopper-Pearson upper bound is 1 - 0.05 ** (1/n).
    assert fail_rate_upper(n, 0) == pytest.approx(1 - 0.05 ** (1 / n), rel=1e-6)
    assert fail_rate_upper(n, 0) == pytest.approx(bound, abs=0.001)


def test_bound_grows_with_failures_and_shrinks_with_trials():
    assert fail_rate_upper(20, 0) < fail_rate_upper(20, 1) < fail_rate_upper(20, 4)
    assert fail_rate_upper(300, 0) < fail_rate_upper(100, 0) < fail_rate_upper(20, 0)


def test_all_failures_bound_is_one():
    assert fail_rate_upper(20, 20) == 1.0


def test_bound_gate_needs_enough_clean_trials():
    from metrics import summarise
    def clean(n):
        return [({"trial": i, "tool_calls": [], "usage": {"input_tokens": 0, "output_tokens": 0}, "latency_s": 0}, "pass", [])
                for i in range(1, n + 1)]
    task = {"id": "privacy", "gate": 1.0, "max_fail_rate": 0.01}
    assert summarise(task, clean(20), 4)["gate_result"] == "FAIL"    # 20/20 only bounds the rate at 14%
    assert summarise(task, clean(300), 4)["gate_result"] == "PASS"   # 300/300 bounds it just under 1%
