"""Phase B — walkforward (Forward 1/4) unit tests (6 tests)."""
from __future__ import annotations


from vibecodekit_mql5.backtest import BacktestResult
from vibecodekit_mql5.walkforward import (
    FORWARD_QUARTER,
    correlation,
    evaluate,
    verdict,
)


def _make(sharpe: float) -> BacktestResult:
    r = BacktestResult()
    r.sharpe = sharpe
    return r


def test_forward_quarter_constant():
    assert FORWARD_QUARTER == 3


def test_correlation_clamps_to_one_when_oos_exceeds_is():
    assert correlation(1.0, 5.0) == 1.0


def test_correlation_zero_when_is_negative_or_zero():
    assert correlation(0.0, 0.5) == 0.0
    assert correlation(-0.1, 0.5) == 0.0


def test_verdict_pass_warn_fail():
    assert verdict(0.8) == "PASS"
    assert verdict(0.4) == "WARN"
    assert verdict(0.2) == "FAIL"


def test_evaluate_pass_case():
    r = evaluate(_make(1.0), _make(0.8))
    assert r.verdict == "PASS"
    assert r.correlation == 0.8


def test_evaluate_fail_case():
    r = evaluate(_make(1.0), _make(0.1))
    assert r.verdict == "FAIL"
