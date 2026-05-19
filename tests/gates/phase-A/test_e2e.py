"""Phase A — 3 end-to-end gates.

These tests spawn real MetaEditor + run real Python CLI entries; they're
slower (~5-20 s each) but they're the ultimate acceptance gate.

  1. test_pipnorm_4_digits_classes
       Compile a shim EA that prints CPipNormalizer truth-table outputs for
       digits 5 / 4 / 3 / 2, then assert the .ex5 compiles cleanly. We
       can't run a strategy tester from xvfb to assert the print values,
       so the compile-clean signal is the gate.

  2. test_lint_8_critical_AP
       Run `mql5-lint` against each of the 8 fixture .mq5 files and
       assert the corresponding AP code appears in its findings.

  3. test_build_compile_stdlib
       Build `stdlib/netting` → compile → expect 0 errors.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from vibecodekit_mql5.build import BuildRequest, build
from vibecodekit_mql5.compile import compile_mq5
from vibecodekit_mql5.lint import lint_file

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests" / "fixtures"


def _wine_or_skip() -> None:
    if sys.platform.startswith("win"):
        return
    if not shutil.which("wine"):
        pytest.skip("wine not installed — e2e requires Wine + MetaEditor")
    me = os.environ.get("METAEDITOR_PATH") or \
        "/home/ubuntu/.wine-mql5/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe"
    if not Path(me).exists():
        pytest.skip(f"MetaEditor not found at {me}")


def test_pipnorm_4_digits_classes(tmp_path):
    _wine_or_skip()
    # Stage CPipNormalizer.mqh next to the test EA so #include resolves.
    for inc in (REPO / "Include").glob("*.mqh"):
        shutil.copy(inc, tmp_path / inc.name)
    ea = tmp_path / "DigitsClasses.mq5"
    ea.write_text(
        '#include "CPipNormalizer.mqh"\n'
        'CPipNormalizer pip;\n'
        'int OnInit() {\n'
        '    pip.Init(_Symbol);\n'
        '    PrintFormat("digits=%d pip=%g", pip.Digits(), pip.Pip());\n'
        '    return INIT_SUCCEEDED;\n'
        '}\n'
        'void OnTick() {}\n',
        encoding="utf-8",
    )
    res = compile_mq5(ea)
    assert res.success, f"compile failed: errors={res.errors}"
    assert res.ex5_path and Path(res.ex5_path).exists()


def test_lint_8_critical_AP():
    expected = {
        "ap_01_no_sl.mq5":              "AP-1",
        "ap_03_lot_fixed.mq5":          "AP-3",
        "ap_05_overfitted.mq5":         "AP-5",
        "ap_15_raw_ordersend.mq5":      "AP-15",
        "ap_17_webrequest_ontick.mq5":  "AP-17",
        "ap_18_async_no_handler.mq5":   "AP-18",
        "ap_20_hardcoded_pip.mq5":      "AP-20",
        "ap_21_jpy_xau_broken.mq5":     "AP-21",
    }
    misses: list[str] = []
    for fname, code in expected.items():
        findings = lint_file(FIXTURES / fname)
        if code not in [f.code for f in findings]:
            misses.append(f"{fname}: expected {code}, got {[f.code for f in findings]}")
    assert not misses, "lint detector misses: " + "; ".join(misses)


def test_build_compile_stdlib(tmp_path):
    _wine_or_skip()
    req = BuildRequest(
        preset="stdlib",
        name="E2ESmoke",
        symbol="EURUSD",
        tf="H1",
        stack="netting",
        out_dir=tmp_path / "E2ESmoke",
        scaffolds_root=REPO / "scaffolds",
        include_root=REPO / "Include",
    )
    out = build(req)
    res = compile_mq5(out / "E2ESmoke.mq5")
    assert res.success, f"errors={res.errors}\nwarnings={res.warnings}"
    assert res.ex5_path and Path(res.ex5_path).exists()
