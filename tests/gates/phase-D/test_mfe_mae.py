"""Regression tests for ``vibecodekit_mql5.mfe_mae`` — PR-12.

Covers two paths:

* Happy path — well-formed CSV → ``MfeMaeStats`` with the expected
  schema (``n_trades``, ``mean_mfe``, ``mean_mae``,
  ``mfe_profit_corr``, ``mae_profit_corr``).
* Sad path — CSV missing one or more required columns
  (``profit`` / ``mfe`` / ``mae``) raises :class:`MfeMaeCsvError`
  (a :class:`ValueError` subclass) with a single structured message
  that names the missing column(s) and the expected header.

The CLI entrypoint (``python -m vibecodekit_mql5.mfe_mae``) must
print a ``{"ok": false, "error": "…"}`` JSON envelope and exit ``2``
instead of letting a raw ``KeyError`` traceback escape — this matches
the ``{ok, error}`` style every other verify CLI uses, and is what
the smoke test in REPORT.md flagged as gap G3.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from vibecodekit_mql5 import mfe_mae


GOOD_CSV = textwrap.dedent(
    """\
    deal_id,open_time,close_time,magic,type,profit,mfe,mae
    1,2024-01-01,2024-01-02,12345,BUY,5.0,12.0,-4.0
    2,2024-01-02,2024-01-03,12345,SELL,-3.0,6.0,-8.0
    3,2024-01-03,2024-01-04,12345,BUY,7.5,15.0,-2.5
    """
)


def test_compute_stats_happy_path() -> None:
    rows = mfe_mae.parse_csv(GOOD_CSV)
    stats = mfe_mae.compute_stats(rows)
    assert stats.n_trades == 3
    payload = stats.to_dict()
    assert set(payload.keys()) == {
        "n_trades", "mean_mfe", "mean_mae",
        "mfe_profit_corr", "mae_profit_corr",
    }


def test_compute_stats_missing_mfe_column_raises_structured_error() -> None:
    text = textwrap.dedent(
        """\
        deal_id,open_time,close_time,magic,type,profit,mae
        1,2024-01-01,2024-01-02,12345,BUY,5.0,-4.0
        """
    )
    rows = mfe_mae.parse_csv(text)
    with pytest.raises(mfe_mae.MfeMaeCsvError) as exc_info:
        mfe_mae.compute_stats(rows)
    msg = str(exc_info.value)
    assert "'mfe'" in msg
    assert "expected header" in msg
    assert mfe_mae.EXPECTED_HEADER in msg


def test_compute_stats_missing_multiple_columns_lists_all() -> None:
    text = textwrap.dedent(
        """\
        deal_id,open_time,close_time,magic,type
        1,2024-01-01,2024-01-02,12345,BUY
        """
    )
    rows = mfe_mae.parse_csv(text)
    with pytest.raises(mfe_mae.MfeMaeCsvError) as exc_info:
        mfe_mae.compute_stats(rows)
    msg = str(exc_info.value)
    for col in ("profit", "mfe", "mae"):
        assert f"'{col}'" in msg


def test_mfe_mae_csv_error_is_value_error_subclass() -> None:
    """Bridge wrapper relies on ``except ValueError`` catching this."""
    assert issubclass(mfe_mae.MfeMaeCsvError, ValueError)


def test_cli_prints_structured_error_json_on_bad_header(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("wrong,columns,here\n1,2,3\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "vibecodekit_mql5.mfe_mae", str(bad)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2, proc.stderr
    # Error envelope is printed to stderr per CLI convention.
    payload = json.loads(proc.stderr.strip())
    assert payload["ok"] is False
    assert "csv missing required column" in payload["error"]
    assert "expected header" in payload["error"]


def test_cli_prints_structured_error_json_on_missing_file(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "vibecodekit_mql5.mfe_mae", str(tmp_path / "nope.csv")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stderr.strip())
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_cli_happy_path_prints_stats_json(tmp_path: Path) -> None:
    good = tmp_path / "good.csv"
    good.write_text(GOOD_CSV, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "vibecodekit_mql5.mfe_mae", str(good)],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(proc.stdout)
    assert payload["n_trades"] == 3
