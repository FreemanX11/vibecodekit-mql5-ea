"""Phase B unit tests for the optimization driver.

Mirrors the design of ``test_tester_run.py``: the driver shells out to
``terminal64.exe`` (or Wine) which we cannot install on a hermetic CI
runner, so the tests cover the pieces that DO run in process —
tester.ini rendering, SpreadsheetML parsing, top-N selection, and
``main()`` plumbing via ``--from-xml`` and ``--print-ini-only``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibecodekit_mql5 import optimize_run
from vibecodekit_mql5.optimize_run import (
    OPTIMIZATION_CRITERIA,
    OPTIMIZATION_MODES,
    OptResult,
    main,
    parse_opt_xml,
    parse_opt_xml_file,
    render_optimize_ini,
    top_n,
)

FIXTURE = Path(__file__).parent / "fixtures" / "opt_results_minimal.xml"


# ─────────────────────────────────────────────────────────────────────────────
# render_optimize_ini
# ─────────────────────────────────────────────────────────────────────────────

def test_render_optimize_ini_contains_mode_and_criterion():
    txt = render_optimize_ini(
        ea_path="MyEA.ex5",
        set_path="default.set",
        symbol="EURUSD",
        period="H1",
        from_date="2024.01.01",
        to_date="2024.12.31",
        optimization_mode=OPTIMIZATION_MODES["genetic"],
        optimization_criterion=int(OPTIMIZATION_CRITERIA["sharpe-max"]["id"]),
        report_path="opt-results.xml",
    )
    assert "Optimization=2\n" in txt
    assert "OptimizationCriterion=5\n" in txt
    assert "Report=opt-results.xml\n" in txt
    assert "ShutdownTerminal=1\n" in txt
    assert "ReplaceReport=1\n" in txt
    assert "Expert=MyEA.ex5\n" in txt
    assert "ExpertParameters=default.set\n" in txt


def test_render_optimize_ini_rejects_bad_mode():
    with pytest.raises(ValueError, match="optimization_mode"):
        render_optimize_ini(
            ea_path="x", set_path="y", symbol="EURUSD", period="H1",
            from_date="2024.01.01", to_date="2024.06.30",
            optimization_mode=99,
            optimization_criterion=0,
        )


def test_render_optimize_ini_rejects_bad_criterion():
    with pytest.raises(ValueError, match="optimization_criterion"):
        render_optimize_ini(
            ea_path="x", set_path="y", symbol="EURUSD", period="H1",
            from_date="2024.01.01", to_date="2024.06.30",
            optimization_mode=2,
            optimization_criterion=99,
        )


# ─────────────────────────────────────────────────────────────────────────────
# parse_opt_xml — SpreadsheetML happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_opt_xml_recovers_all_rows():
    rows = parse_opt_xml_file(FIXTURE)
    assert len(rows) == 5
    assert [r.pass_num for r in rows] == [1, 2, 3, 4, 5]


def test_parse_opt_xml_splits_metrics_from_params():
    rows = parse_opt_xml_file(FIXTURE)
    first = rows[0]
    # InpFastPeriod / InpSlowPeriod are EA inputs, not optimizer columns.
    assert "InpFastPeriod" in first.params
    assert "InpSlowPeriod" in first.params
    assert first.params["InpFastPeriod"] == "8"
    # Known statistics columns land in metrics as floats.
    assert pytest.approx(first.metrics["Sharpe Ratio"], rel=1e-6) == 0.85
    assert pytest.approx(first.metrics["Profit"], rel=1e-6) == 1250.5
    # The Pass column never bleeds into params or metrics — it's the row id.
    assert "Pass" not in first.params
    assert "Pass" not in first.metrics


def test_parse_opt_xml_preserves_pass_zero():
    """MT5 optimization passes are 0-indexed. A row with Pass=0 must
    stay 0 in the parsed result, not silently get renumbered to the
    1-based row index — otherwise pass 0 and pass 1 collide.
    """
    raw = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="T">
  <Table>
   <Row>
    <Cell><Data ss:Type="String">Pass</Data></Cell>
    <Cell><Data ss:Type="String">Result</Data></Cell>
    <Cell><Data ss:Type="String">InpA</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">0</Data></Cell>
    <Cell><Data ss:Type="Number">100</Data></Cell>
    <Cell><Data ss:Type="Number">5</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">1</Data></Cell>
    <Cell><Data ss:Type="Number">200</Data></Cell>
    <Cell><Data ss:Type="Number">7</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
</Workbook>
"""
    rows = parse_opt_xml(raw)
    assert [r.pass_num for r in rows] == [0, 1]
    # Distinct values — the Pass=0 row did not collide with Pass=1.
    assert len({r.pass_num for r in rows}) == 2


def test_parse_opt_xml_falls_back_to_idx_when_pass_missing():
    """If the Pass column is absent or unparseable, we still hand back
    a unique 1-based identifier (the row index) so downstream callers
    can address each row.
    """
    raw = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="T">
  <Table>
   <Row>
    <Cell><Data ss:Type="String">Result</Data></Cell>
    <Cell><Data ss:Type="String">InpA</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">42</Data></Cell>
    <Cell><Data ss:Type="Number">8</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">99</Data></Cell>
    <Cell><Data ss:Type="Number">11</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
</Workbook>
"""
    rows = parse_opt_xml(raw)
    assert [r.pass_num for r in rows] == [1, 2]


def test_parse_opt_xml_handles_empty_table():
    empty_xml = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Tester">
  <Table/>
 </Worksheet>
</Workbook>
"""
    assert parse_opt_xml(empty_xml) == []


def test_parse_opt_xml_honours_ss_index_for_gappy_rows(tmp_path):
    # Excel allows ``<Cell ss:Index="N">`` to skip empty columns. We
    # honour that so a row with one blank column at position 3 still
    # aligns with the header.
    raw = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="T">
  <Table>
   <Row>
    <Cell><Data ss:Type="String">Pass</Data></Cell>
    <Cell><Data ss:Type="String">Result</Data></Cell>
    <Cell><Data ss:Type="String">Profit</Data></Cell>
    <Cell><Data ss:Type="String">InpA</Data></Cell>
   </Row>
   <Row>
    <Cell><Data ss:Type="Number">1</Data></Cell>
    <Cell><Data ss:Type="Number">100</Data></Cell>
    <Cell ss:Index="4"><Data ss:Type="String">x</Data></Cell>
   </Row>
  </Table>
 </Worksheet>
</Workbook>
"""
    rows = parse_opt_xml(raw)
    assert len(rows) == 1
    assert rows[0].params == {"InpA": "x"}
    assert rows[0].metrics["Result"] == 100.0
    assert "Profit" not in rows[0].metrics  # gappy cell stayed empty


# ─────────────────────────────────────────────────────────────────────────────
# top_n — sort direction + filtering
# ─────────────────────────────────────────────────────────────────────────────

def test_top_n_descending_for_maximise_fitness():
    rows = parse_opt_xml_file(FIXTURE)
    top = top_n(rows, "Sharpe Ratio", 3, minimise=False)
    assert [r.pass_num for r in top] == [4, 2, 1]


def test_top_n_ascending_for_minimise_fitness():
    rows = parse_opt_xml_file(FIXTURE)
    top = top_n(rows, "Equity DD %", 2, minimise=True)
    assert [r.pass_num for r in top] == [4, 2]


def test_top_n_drops_rows_missing_the_fitness_column():
    rows = [
        OptResult(pass_num=1, metrics={"Sharpe Ratio": 1.5}),
        OptResult(pass_num=2, metrics={"Profit": 100.0}),  # no Sharpe
    ]
    top = top_n(rows, "Sharpe Ratio", 5)
    assert [r.pass_num for r in top] == [1]


def test_top_n_zero_returns_empty():
    rows = parse_opt_xml_file(FIXTURE)
    assert top_n(rows, "Sharpe Ratio", 0) == []


# ─────────────────────────────────────────────────────────────────────────────
# main() — CLI plumbing via hermetic --from-xml
# ─────────────────────────────────────────────────────────────────────────────

def test_main_from_xml_emits_json_with_top_block(capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--from-xml", str(FIXTURE),
        "--criterion", "sharpe-max",
        "--top", "2",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["fitness_column"] == "Sharpe Ratio"
    assert payload["minimise"] is False
    assert payload["total_passes"] == 5
    assert [row["pass"] for row in payload["top"]] == [4, 2]


def test_main_from_xml_minimise_criterion_inverts_sort(capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--from-xml", str(FIXTURE),
        "--criterion", "drawdown-min",
        "--top", "3",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["minimise"] is True
    assert [row["pass"] for row in payload["top"]] == [4, 2, 1]


def test_main_print_ini_only_renders_and_exits(capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--mode", "slow",
        "--criterion", "profit-factor-max",
        "--print-ini-only",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Optimization=1\n" in out  # slow complete
    assert "OptimizationCriterion=1\n" in out  # profit-factor-max
    assert "Expert=MyEA.ex5" in out


def test_main_rejects_mode_off(capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--mode", "off",
        "--from-xml", str(FIXTURE),
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "mql5-tester-run" in err


def test_main_bad_period_format(capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "not-a-period",
        "--from-xml", str(FIXTURE),
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "[optimize-run]" in err


def test_main_missing_xml_returns_5(capsys, tmp_path):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--from-xml", str(tmp_path / "does-not-exist.xml"),
    ])
    err = capsys.readouterr().err
    assert rc == 5
    assert "XML parse failed" in err


def test_main_empty_xml_reports_zero_rows(capsys, tmp_path):
    empty = tmp_path / "empty.xml"
    empty.write_text(
        '<?xml version="1.0"?>\n'
        '<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"'
        ' xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">'
        '<Worksheet ss:Name="T"><Table/></Worksheet></Workbook>'
    )
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--from-xml", str(empty),
    ])
    out = capsys.readouterr().out
    assert rc == 1
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["total_passes"] == 0


def test_main_mutually_exclusive_wine_flags(capsys):
    rc = main([
        "MyEA.ex5", "default.set",
        "--period", "2024.01.01-2024.12.31",
        "--wine", "--no-wine",
    ])
    err = capsys.readouterr().err
    assert rc == 2
    assert "mutually exclusive" in err


# ─────────────────────────────────────────────────────────────────────────────
# Smoke test: the CLI script entry point exists in the installed dist.
# ─────────────────────────────────────────────────────────────────────────────

def test_module_main_exists():
    # Belt-and-braces — guards against accidental rename when refactoring.
    assert callable(optimize_run.main)
