"""Phase E unit tests — ``auto_fix`` AP transformer pipeline (P1.2).

Verifies each of the 8 critical Phase-A anti-patterns is either mutated
(rewritten so the detector re-passes) or annotated (a ``// FIXME AP-N:``
bookmark is inserted on the line *above* the finding).  Also exercises the
CLI in ``--check`` and ``--diff`` modes plus the report's JSON shape.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from vibecodekit_mql5 import auto_fix, lint as lint_mod  # noqa: E402


# Helper: a tiny EA that imports CPipNormalizer so the mutating fixers
# (AP-3, AP-20) are allowed to rewrite the file (they bail when ``pip`` is
# out of scope to avoid introducing undefined-symbol compile errors).
def _ea_with_pip() -> str:
    return dedent(
        """\
        //+------------------------------------------------------------------+
        //| Test EA — has CPipNormalizer pip; in scope                        |
        //+------------------------------------------------------------------+
        // digits-tested: 5, 3
        #include "CPipNormalizer.mqh"
        CPipNormalizer pip;
        input int InpSlPips = 30;
        input double InpRiskMoney = 100.0;

        void OnTick()
          {
           double lot = 0.01;
           double sl  = _Bid - 30 * _Point;
           double tp  = _Bid + 60 * Point();
          }
        """
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mutating fixers
# ─────────────────────────────────────────────────────────────────────────────

def test_fix_ap3_replaces_hardcoded_lot_when_pip_in_scope() -> None:
    src = _ea_with_pip()
    out, log = auto_fix.fix_ap3(src)
    assert "lot = pip.LotForRisk(InpRiskMoney, InpSlPips)" in out
    assert "lot = 0.01" not in out
    assert log and "AP-3" in log[0]


def test_fix_ap3_no_op_when_pip_not_in_scope() -> None:
    # No CPipNormalizer declaration anywhere → fixer refuses to touch the
    # file (rewriting would introduce an undefined-symbol compile error).
    src = "void OnTick() { double lot = 0.01; }\n"
    out, log = auto_fix.fix_ap3(src)
    assert out == src
    assert log == []


def test_fix_ap18_inserts_handler_stub_when_async_used_without_handler() -> None:
    src = dedent(
        """\
        void OnTick()
          {
           OrderSendAsync(req, res);
          }
        """
    )
    out, log = auto_fix.fix_ap18(src)
    assert "void OnTradeTransaction" in out
    assert "AP-18 stub" in out
    assert log and "AP-18" in log[0]


def test_fix_ap18_no_op_when_handler_already_present() -> None:
    src = dedent(
        """\
        void OnTick() { OrderSendAsync(req, res); }
        void OnTradeTransaction(const MqlTradeTransaction& t,
                                const MqlTradeRequest&     r,
                                const MqlTradeResult&      x) {}
        """
    )
    out, log = auto_fix.fix_ap18(src)
    assert out == src
    assert log == []


def test_fix_ap20_replaces_all_hardcoded_pip_math() -> None:
    src = _ea_with_pip()
    out, log = auto_fix.fix_ap20(src)
    assert "* pip.Point()" in out
    assert "* _Point" not in out
    assert "* Point()" not in out
    assert log and "AP-20" in log[0]
    # The summary count covers every replacement.
    assert "2 hardcoded pip operation(s)" in log[0]


def test_fix_ap20_no_op_when_pip_not_in_scope() -> None:
    src = "void OnTick() { double sl = _Bid - 30 * _Point; }\n"
    out, log = auto_fix.fix_ap20(src)
    assert out == src
    assert log == []


def test_fix_ap21_expands_single_digit_class_tag() -> None:
    src = "// digits-tested: 5\nvoid OnTick() {}\n"
    out, log = auto_fix.fix_ap21(src)
    # Either ordering is acceptable; check both classes show up.
    assert "5" in out and "3" in out
    assert "digits-tested" in out
    # Lint detector should now report 0 AP-21 findings.
    findings = lint_mod.lint_source("<x>", out)
    assert not [f for f in findings if f.code == "AP-21"]
    assert log and "AP-21" in log[0]


def test_fix_ap21_inserts_tag_when_missing_entirely() -> None:
    src = "void OnTick() {}\n"
    out, log = auto_fix.fix_ap21(src)
    assert out.startswith("// digits-tested: 3, 5")
    findings = lint_mod.lint_source("<x>", out)
    assert not [f for f in findings if f.code == "AP-21"]
    assert log and "AP-21" in log[0]


def test_fix_ap21_no_op_when_tag_already_lists_2_classes() -> None:
    src = "// digits-tested: 5, 3\nvoid OnTick() {}\n"
    out, log = auto_fix.fix_ap21(src)
    assert out == src
    assert log == []


# ─────────────────────────────────────────────────────────────────────────────
# Annotating fixers
# ─────────────────────────────────────────────────────────────────────────────

def test_fix_ap1_annotates_trade_buy_without_sl() -> None:
    src = dedent(
        """\
        void OnTick()
          {
           CTrade trade;
           trade.Buy(0.1, _Symbol);
          }
        """
    )
    out, log = auto_fix.fix_ap1(src)
    assert "// FIXME AP-1:" in out
    # The FIXME line must sit directly above the trade.Buy call.
    lines = out.splitlines()
    fixme_idx = next(i for i, ln in enumerate(lines) if "FIXME AP-1" in ln)
    assert "trade.Buy" in lines[fixme_idx + 1]
    assert log and "AP-1" in log[0]


def test_annotating_fixers_are_idempotent() -> None:
    """Running auto-fix twice must not stack ``// FIXME AP-1:`` comments."""
    src = dedent(
        """\
        void OnTick()
          {
           CTrade trade;
           trade.Buy(0.1, _Symbol);
          }
        """
    )
    once = auto_fix.fix_source("ea.mq5", src).fixed_text
    twice = auto_fix.fix_source("ea.mq5", once).fixed_text
    assert twice == once
    assert once.count("// FIXME AP-1:") == 1


def test_fix_ap15_annotates_raw_ordersend() -> None:
    src = dedent(
        """\
        void OnTick()
          {
           OrderSend(req, res);
          }
        """
    )
    out, log = auto_fix.fix_ap15(src)
    assert "// FIXME AP-15:" in out
    assert log and "AP-15" in log[0]


def test_fix_ap17_annotates_webrequest_in_ontick() -> None:
    # AP-17 detector requires the closing ``}`` to sit at column 0 (regex is
    # ``\n\}``), so the fixture mirrors the layout that real MetaEditor
    # scaffolds emit.
    src = dedent(
        """\
        void OnTick() {
            string res;
            int code = WebRequest("GET", "http://x", "", 5000, NULL, res, 0);
        }
        """
    )
    out, log = auto_fix.fix_ap17(src)
    assert "// FIXME AP-17:" in out
    assert log and "AP-17" in log[0]


def test_fix_ap5_annotates_when_more_than_6_inputs() -> None:
    src = dedent(
        """\
        // digits-tested: 5, 3
        input int A=1;
        input int B=1;
        input int C=1;
        input int D=1;
        input int E=1;
        input int F=1;
        input int G=1;
        input int H=1;
        void OnTick() {}
        """
    )
    out, log = auto_fix.fix_ap5(src)
    assert "// FIXME AP-5:" in out
    assert log and "AP-5" in log[0]


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline + CLI
# ─────────────────────────────────────────────────────────────────────────────

def test_fix_source_reduces_error_count_on_kitchen_sink_ea() -> None:
    """A single source with 4 mutating + 2 annotating findings:

    * AP-3 (hardcoded lot)        — mutating
    * AP-20 (hardcoded pip math)  — mutating
    * AP-21 (missing tag)         — mutating
    * AP-18 (async no handler)    — mutating
    * AP-1 (Buy w/o SL)           — annotating
    * AP-15 (raw OrderSend)       — annotating
    """
    src = dedent(
        """\
        #include "CPipNormalizer.mqh"
        CPipNormalizer pip;
        input int InpSlPips = 30;
        input double InpRiskMoney = 100.0;
        CTrade trade;

        void OnTick()
          {
           double lot = 0.01;
           double sl  = _Bid - 30 * _Point;
           trade.Buy(lot, _Symbol);
           OrderSend(req, res);
           OrderSendAsync(req, res);
          }
        """
    )
    report = auto_fix.fix_source("ea.mq5", src)
    errs_before = sum(1 for f in report.findings_before if f.severity == "ERROR")
    errs_after  = sum(1 for f in report.findings_after  if f.severity == "ERROR")
    assert errs_before > errs_after, f"before={errs_before} after={errs_after}"
    # AP-3, AP-18, AP-20, AP-21 must be fully cleared post-fix.
    cleared = {"AP-3", "AP-18", "AP-20", "AP-21"}
    remaining = {f.code for f in report.findings_after}
    assert not (cleared & remaining), \
        f"mutating fixers did not clear {cleared & remaining}"


def test_cli_check_mode_exits_1_on_dirty_file(tmp_path: Path, capsys) -> None:
    target = tmp_path / "dirty.mq5"
    target.write_text("// digits-tested: 5\nvoid OnTick() {}\n")
    rc = auto_fix.main([str(target), "--check"])
    assert rc == 1
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["changed"] is True


def test_cli_check_mode_exits_0_on_clean_file(tmp_path: Path, capsys) -> None:
    target = tmp_path / "clean.mq5"
    target.write_text("// digits-tested: 5, 3\nvoid OnTick() {}\n")
    rc = auto_fix.main([str(target), "--check"])
    assert rc == 0


def test_cli_write_mode_creates_backup_and_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "ea.mq5"
    src = "// digits-tested: 5\nvoid OnTick() {}\n"
    target.write_text(src)
    rc = auto_fix.main([str(target)])
    assert rc == 0
    # Original preserved in .bak alongside.
    assert (tmp_path / "ea.mq5.bak").read_text() == src
    # File now passes lint for AP-21.
    new = target.read_text()
    assert new != src
    assert "3" in new and "5" in new


def test_cli_diff_mode_writes_unified_diff_and_does_not_modify_file(
    tmp_path: Path, capsys,
) -> None:
    target = tmp_path / "ea.mq5"
    src = "// digits-tested: 5\nvoid OnTick() {}\n"
    target.write_text(src)
    rc = auto_fix.main([str(target), "--diff"])
    assert rc == 0
    # The file on disk is untouched.
    assert target.read_text() == src
    captured = capsys.readouterr()
    assert "--- " in captured.out and "+++ " in captured.out


def test_cli_rejects_non_file(capsys) -> None:
    rc = auto_fix.main(["/nonexistent/path.mq5"])
    assert rc == 2
