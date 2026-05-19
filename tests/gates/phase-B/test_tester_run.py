"""Phase B unit tests for the W8 Strategy Tester driver.

The driver shells out to ``terminal64.exe`` (or Wine), which we cannot
install in CI on a hermetic runner. Every test in this file therefore
exercises the *composition* logic: tester.ini generation, terminal
probe ordering, command construction, report polling, and exit code
mapping. The single integration test that needs a real terminal is
gated by ``MQL5_TERMINAL_PATH`` and skipped otherwise.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from vibecodekit_mql5 import tester_run
from vibecodekit_mql5.tester_run import (
    TerminalLocation,
    TesterRunSpec,
    build_command,
    find_terminal,
    main,
    run,
    wait_for_report,
)


# ─────────────────────────────────────────────────────────────────────────────
# find_terminal — probe order
# ─────────────────────────────────────────────────────────────────────────────

def test_find_terminal_honours_override(tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_text("stub")
    loc = find_terminal(str(fake), use_wine=True, platform="linux")
    assert loc.path == fake
    assert loc.use_wine is True


def test_find_terminal_honours_env_var(tmp_path, monkeypatch):
    fake = tmp_path / "terminal64.exe"
    fake.write_text("stub")
    monkeypatch.setenv("MQL5_TERMINAL_PATH", str(fake))
    loc = find_terminal(None, use_wine=False, platform="linux")
    assert loc.path == fake


def test_find_terminal_missing_is_explicit(tmp_path, monkeypatch):
    # Point every probe path at a guaranteed-empty dir so the search
    # exhausts deterministically.
    monkeypatch.delenv("MQL5_TERMINAL_PATH", raising=False)
    monkeypatch.setenv("WINEPREFIX", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(FileNotFoundError) as exc:
        find_terminal(None, use_wine=True, platform="linux")
    msg = str(exc.value)
    assert "terminal64.exe not found" in msg
    # The error names the probe set so the operator can see what to fix.
    assert "Set $MQL5_TERMINAL_PATH" in msg


def test_find_terminal_platform_specific_probes(tmp_path, monkeypatch):
    # Windows probes look for C:\Program Files\..., not Wine prefixes.
    # CI runners on Windows have MT5 installed at the default path, so the
    # probe would succeed; redirect the probe set at a guaranteed-empty
    # location so the lookup definitively fails.
    monkeypatch.delenv("MQL5_TERMINAL_PATH", raising=False)
    monkeypatch.setattr(
        tester_run,
        "_PROBE_PATHS_WIN",
        (
            "$MQL5_TERMINAL_PATH",
            str(tmp_path / "Program Files" / "MetaTrader 5" / "terminal64.exe"),
        ),
    )
    with pytest.raises(FileNotFoundError) as exc:
        find_terminal(None, platform="win32")
    assert "Program Files" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# build_command — wine vs native
# ─────────────────────────────────────────────────────────────────────────────

def test_build_command_wine_prepends_wine(tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_text("stub")
    loc = TerminalLocation(fake, use_wine=True, probed=())
    cmd = build_command(loc, tmp_path / "tester.ini")
    assert cmd[0] == "wine"
    assert cmd[1] == str(fake)
    assert "/portable" in cmd
    assert any(part.startswith("/config:") for part in cmd)


def test_build_command_native_omits_wine(tmp_path):
    fake = tmp_path / "terminal64.exe"
    fake.write_text("stub")
    loc = TerminalLocation(fake, use_wine=False, probed=())
    cmd = build_command(loc, tmp_path / "tester.ini")
    assert cmd[0] == str(fake)
    assert cmd[1].startswith("/config:")
    assert "/portable" in cmd


# ─────────────────────────────────────────────────────────────────────────────
# wait_for_report — polling logic
# ─────────────────────────────────────────────────────────────────────────────

def test_wait_for_report_returns_true_when_file_appears(tmp_path):
    target = tmp_path / "tester.xml"
    target.write_text("<report/>")
    clock = [0.0]
    assert wait_for_report(
        target,
        timeout_sec=5.0,
        sleep=lambda _: None,
        now=lambda: clock[0],
    ) is True


def test_wait_for_report_times_out_when_missing(tmp_path):
    target = tmp_path / "tester.xml"
    clock = [0.0]
    def fake_sleep(s):
        clock[0] += s
    assert wait_for_report(
        target,
        timeout_sec=2.0,
        poll_interval_sec=0.5,
        sleep=fake_sleep,
        now=lambda: clock[0],
    ) is False


def test_wait_for_report_rejects_empty_file(tmp_path):
    target = tmp_path / "tester.xml"
    target.write_text("")  # zero-byte report is not "done"
    clock = [0.0]
    def fake_sleep(s):
        clock[0] += s
    assert wait_for_report(
        target,
        timeout_sec=0.5,
        sleep=fake_sleep,
        now=lambda: clock[0],
    ) is False


# ─────────────────────────────────────────────────────────────────────────────
# run() composition — mock subprocess + pre-stage XML
# ─────────────────────────────────────────────────────────────────────────────

_FAKE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<Tester>
  <Symbol>EURUSD</Symbol>
  <Period>H1</Period>
  <Statistics>
    <ProfitFactor>1.50</ProfitFactor>
    <RecoveryFactor>3.0</RecoveryFactor>
    <SharpeRatio>0.75</SharpeRatio>
    <MaxDrawdownPct>10.0</MaxDrawdownPct>
    <TotalTrades>42</TotalTrades>
  </Statistics>
</Tester>
"""


def test_run_composes_ini_then_terminal_then_parse(tmp_path):
    """Driver writes tester.ini, invokes the runner, then parses XML."""
    fake_terminal = tmp_path / "terminal64.exe"
    fake_terminal.write_text("stub")
    loc = TerminalLocation(fake_terminal, use_wine=False, probed=())
    report = tmp_path / "tester.xml"
    ini_path = tmp_path / "tester.ini"

    spec = TesterRunSpec(
        ea_path="MyEA.ex5",
        set_path="default.set",
        symbol="EURUSD",
        period="H1",
        from_date="2024.01.01",
        to_date="2024.12.31",
        report_path=str(report),
    )

    runner_calls: list[list[str]] = []

    def fake_runner(cmd, *, timeout=None, check=False):
        runner_calls.append(cmd)
        # Simulate the terminal: write the XML before "exiting".
        report.write_text(_FAKE_XML)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    result = run(
        spec,
        terminal=loc,
        ini_path=ini_path,
        timeout_sec=2.0,
        subprocess_runner=fake_runner,
    )

    # tester.ini was materialised with the spec's values.
    ini_text = ini_path.read_text(encoding="utf-8")
    assert "Symbol=EURUSD" in ini_text
    assert "FromDate=2024.01.01" in ini_text
    assert "ToDate=2024.12.31" in ini_text
    assert f"Report={report}" in ini_text

    # The runner was called exactly once with /portable mode.
    assert len(runner_calls) == 1
    assert "/portable" in runner_calls[0]

    # And the XML was parsed back into a BacktestResult.
    assert result.profit_factor == pytest.approx(1.50)
    assert result.total_trades == 42


def test_run_timeout_propagates_as_timeouterror(tmp_path):
    fake_terminal = tmp_path / "terminal64.exe"
    fake_terminal.write_text("stub")
    loc = TerminalLocation(fake_terminal, use_wine=False, probed=())
    spec = TesterRunSpec(
        ea_path="MyEA.ex5", set_path="default.set",
        symbol="EURUSD", period="H1",
        from_date="2024.01.01", to_date="2024.12.31",
        report_path=str(tmp_path / "tester.xml"),
    )

    def hung_runner(cmd, *, timeout=None, check=False):
        raise subprocess.TimeoutExpired(cmd, timeout)

    with pytest.raises(TimeoutError):
        run(spec, terminal=loc, ini_path=tmp_path / "tester.ini",
            timeout_sec=0.5, subprocess_runner=hung_runner)


def test_run_missing_report_after_exit_is_timeouterror(tmp_path):
    """Terminal exited cleanly but no XML — surface as TimeoutError."""
    fake_terminal = tmp_path / "terminal64.exe"
    fake_terminal.write_text("stub")
    loc = TerminalLocation(fake_terminal, use_wine=False, probed=())
    spec = TesterRunSpec(
        ea_path="MyEA.ex5", set_path="default.set",
        symbol="EURUSD", period="H1",
        from_date="2024.01.01", to_date="2024.12.31",
        report_path=str(tmp_path / "tester.xml"),
    )

    def clean_runner(cmd, *, timeout=None, check=False):
        # Do NOT write the report — emulate a silent failure.
        return subprocess.CompletedProcess(cmd, 0, "", "")

    with pytest.raises(TimeoutError) as exc:
        run(spec, terminal=loc, ini_path=tmp_path / "tester.ini",
            timeout_sec=0.5, subprocess_runner=clean_runner)
    assert "was not produced" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# CLI exit codes
# ─────────────────────────────────────────────────────────────────────────────

def test_cli_print_ini_only_emits_canonical_ini(tmp_path, capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--tf", "H1",
        "--print-ini-only",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[Tester]" in out
    assert "Symbol=EURUSD" in out
    assert "FromDate=2024.01.01" in out
    assert "Period=H1" in out


def test_cli_bad_period_returns_2(tmp_path, capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "not-a-period",
        "--print-ini-only",
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "period" in err.lower()


def test_cli_missing_terminal_returns_3(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("MQL5_TERMINAL_PATH", raising=False)
    monkeypatch.setenv("WINEPREFIX", str(tmp_path / "empty"))
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    # On Windows CI the default `C:\Program Files\MetaTrader 5\terminal64.exe`
    # probe is populated by the MT5 install step; redirect both probe sets
    # at empty tmp paths so the lookup definitively exits with rc=3 instead
    # of finding the real terminal and timing out with rc=4.
    empty_probes = (
        "$MQL5_TERMINAL_PATH",
        str(tmp_path / "nope" / "terminal64.exe"),
    )
    monkeypatch.setattr(tester_run, "_PROBE_PATHS_LINUX", empty_probes)
    monkeypatch.setattr(tester_run, "_PROBE_PATHS_WIN", empty_probes)
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--tf", "H1",
    ])
    err = capsys.readouterr().err
    assert rc == 3
    assert "terminal64.exe not found" in err


def test_cli_mutually_exclusive_wine_flags_return_2(tmp_path, capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--wine", "--no-wine",
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "mutually exclusive" in err


# ─────────────────────────────────────────────────────────────────────────────
# Integration — requires a real terminal install
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("MQL5_TERMINAL_PATH"),
    reason="MQL5_TERMINAL_PATH not set — skipping live tester-run integration",
)
def test_integration_tester_run_live(tmp_path):
    """Optional: opt-in live test. Exercises the full driver against the
    real terminal binary. Skipped unless MQL5_TERMINAL_PATH is set."""
    spec = TesterRunSpec(
        ea_path="ExpertMACD.ex5",
        set_path="",
        symbol="EURUSD",
        period="H1",
        from_date="2024.01.01",
        to_date="2024.01.31",
        report_path=str(tmp_path / "report.xml"),
    )
    loc = find_terminal(None)
    result = run(
        spec, terminal=loc,
        ini_path=tmp_path / "tester.ini",
        timeout_sec=120.0,
    )
    assert result.total_trades >= 0
