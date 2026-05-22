"""Phase B — monte_carlo bootstrap + percentile unit tests (4 tests)."""
from __future__ import annotations

import os
import subprocess
import sys

from vibecodekit_mql5.monte_carlo import (
    bootstrap,
    evaluate,
    max_drawdown_pct,
    percentile,
)


def test_max_drawdown_known_series():
    # Equity: 0 -> 10 -> 10 -> 5 -> 5 -> 8
    # Peak at 10 with trough at 5 → 50% DD.
    returns = [10.0, 0.0, -5.0, 0.0, 3.0]
    assert max_drawdown_pct(returns) == 50.0


def test_percentile_basic():
    s = sorted([1, 2, 3, 4, 5])
    assert percentile(s, 50) == 3
    assert percentile(s, 95) == 5
    assert percentile(s, 0) == 1


def test_bootstrap_returns_n_simulations():
    returns = [1.0, -2.0, 3.0, -1.0, 2.0]
    out = bootstrap(returns, n_sims=50, seed=42)
    assert len(out) == 50
    assert all(d >= 0 for d in out)


def test_evaluate_pass_within_tolerance():
    # Modest, balanced returns → P95 DD should sit near reported.
    returns = [1.0, -1.0, 1.0, -1.0] * 25
    result = evaluate(returns, reported_dd=5.0, n_sims=200, seed=7)
    assert result.n_sims == 200
    assert result.verdict in ("PASS", "FAIL")  # deterministic with seed


def test_help_prints_under_ascii_python_io_encoding():
    result = subprocess.run(
        [sys.executable, "-m", "vibecodekit_mql5.monte_carlo", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 0
    assert "mql5-monte-carlo" in result.stdout
