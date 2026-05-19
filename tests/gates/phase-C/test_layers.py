"""Tests for the 7 permission layers + orchestrator — 9 unit tests."""

from __future__ import annotations

import argparse
import json


from vibecodekit_mql5.permission import (
    layer1_source_lint,
    layer2_compile,
    layer3_ap_lint,
    layer4_checklist,
    layer5_methodology,
    layer6_quality_matrix,
    layer7_broker_safety,
    orchestrator,
)


# ─── Layer 1 ─────────────────────────────────────────────────────────────────

def test_layer1_source_lint_passes_on_clean_source(tmp_path):
    src = tmp_path / "ok.mq5"
    src.write_text("//+----+\nvoid OnTick(){\n    int x = 0;\n}\n", encoding="utf-8")
    result = layer1_source_lint.lint_source(src)
    assert result["ok"] is True
    assert result["issues"] == []


def test_layer1_source_lint_fails_on_unbalanced_braces(tmp_path):
    src = tmp_path / "bad.mq5"
    src.write_text("void OnTick(){\n    int x = 0;\n", encoding="utf-8")
    result = layer1_source_lint.lint_source(src)
    assert result["ok"] is False
    assert any("braces" in issue for issue in result["issues"])


# ─── Layer 2 ─────────────────────────────────────────────────────────────────

def test_layer2_compile_passes_with_zero_errors(tmp_path):
    log = tmp_path / "compile.json"
    log.write_text(json.dumps({
        "success": True, "errors": [], "warnings": ["unused var"],
        "ex5_path": "foo.ex5",
    }), encoding="utf-8")
    result = layer2_compile.gate(tmp_path / "foo.mq5", log_json=log)
    assert result["ok"] is True
    assert result["warnings"] == ["unused var"]


def test_layer2_compile_fails_with_errors(tmp_path):
    log = tmp_path / "compile.json"
    log.write_text(json.dumps({
        "success": False, "errors": ["'foo' undeclared"],
        "warnings": [], "ex5_path": "",
    }), encoding="utf-8")
    result = layer2_compile.gate(tmp_path / "foo.mq5", log_json=log)
    assert result["ok"] is False
    assert "'foo' undeclared" in result["errors"]


def test_layer2_compile_handles_compileresult_dataclass(tmp_path, monkeypatch):
    # Regression: `compile_mq5` returns a CompileResult dataclass, not a dict.
    # Layer 2 previously called `.get(...)` on it and crashed with AttributeError
    # whenever the orchestrator ran without a --compile-log (e.g. Wine missing).
    from vibecodekit_mql5 import compile as compile_mod

    def _fake_compile(_path, **_kwargs):
        return compile_mod.CompileResult(
            success=False,
            errors=["MetaEditor not invocable"],
            warnings=[],
        )

    monkeypatch.setattr(compile_mod, "compile_mq5", _fake_compile)
    result = layer2_compile.gate(tmp_path / "foo.mq5", log_json=None)
    assert result["ok"] is False
    assert "MetaEditor not invocable" in result["errors"]
    assert result["warnings"] == []


# ─── Layer 3 ─────────────────────────────────────────────────────────────────

def test_layer3_ap_lint_blocks_on_critical_ap1(tmp_path):
    # Phase A AP-1 detector flags CTrade.Buy without a stop-loss arg.
    src = tmp_path / "bad.mq5"
    src.write_text(
        "// digits-tested: 5,3\n"
        "#include <Trade/Trade.mqh>\n"
        "CTrade trade;\n"
        "void OnTick(){ trade.Buy(0.01); }\n",
        encoding="utf-8",
    )
    result = layer3_ap_lint.gate(src)
    assert result["ok"] is False
    codes = {e["code"] for e in result["critical_errors"]}
    assert "AP-1" in codes


def test_layer3_ap_lint_passes_when_only_warns(tmp_path):
    # No critical findings; AP-14 (no MFE/MAE) is WARN-only and shouldn't fail.
    src = tmp_path / "ok.mq5"
    src.write_text(
        "// digits-tested: 5,3\n"
        "#include <Trade/Trade.mqh>\n"
        "CTrade trade;\n"
        "double risk_lot=0; double sl;\n"
        "void OnTick(){\n"
        "  if(Bars(_Symbol,_Period)>0){ sl=0; trade.Buy(risk_lot, NULL, 0, sl); }\n"
        "}\n",
        encoding="utf-8",
    )
    result = layer3_ap_lint.gate(src)
    assert result["ok"] is True


# ─── Layer 4 ─────────────────────────────────────────────────────────────────

def test_layer4_checklist_thresholds(tmp_path):
    report = tmp_path / "tc.json"
    payload = {f"check_{i}": "PASS" for i in range(15)}
    payload.update({"check_15": "WARN", "check_16": "WARN", "_summary": "..."})
    report.write_text(json.dumps(payload), encoding="utf-8")
    assert layer4_checklist.gate(report, "personal")["ok"] is True   # 15 ≥ 15
    assert layer4_checklist.gate(report, "enterprise")["ok"] is False  # 15 < 17


# ─── Layer 5 ─────────────────────────────────────────────────────────────────

def test_layer5_methodology_personal_is_skipped(tmp_path):
    result = layer5_methodology.gate(tmp_path, "personal")
    assert result["ok"] is True
    assert result.get("skipped") is True


def test_layer5_methodology_enterprise_requires_sentinels(tmp_path):
    # Empty state dir → enterprise fails.
    result = layer5_methodology.gate(tmp_path, "enterprise")
    assert result["ok"] is False
    assert "scan" in result["missing_steps"]
    # Touch all 8 sentinels → enterprise passes.
    for s in ("scan", "rri", "vision", "blueprint", "tip", "build", "verify", "refine"):
        (tmp_path / f"{s}.done").touch()
    assert layer5_methodology.gate(tmp_path, "enterprise")["ok"] is True


# ─── Layer 6 ─────────────────────────────────────────────────────────────────

def test_layer6_quality_matrix_skipped_for_non_enterprise(tmp_path):
    matrix = tmp_path / "m.json"
    matrix.write_text("{}", encoding="utf-8")
    assert layer6_quality_matrix.gate(matrix, "personal")["ok"] is True
    assert layer6_quality_matrix.gate(matrix, "team")["ok"] is True


def test_layer6_quality_matrix_enterprise_threshold(tmp_path):
    # 60 PASS + 4 WARN → enterprise PASS; 59 PASS → fail.
    from vibecodekit_mql5.rri.matrix import AXES, DIMS

    def build(passes: int) -> dict:
        cells = []
        for d in DIMS:
            for a in AXES:
                cells.append((d, a))
        payload = {}
        for i, (d, a) in enumerate(cells):
            payload[f"{d}/{a}"] = {"status": "PASS" if i < passes else "WARN"}
        return payload

    ok_payload = tmp_path / "ok.json"
    ok_payload.write_text(json.dumps(build(60)), encoding="utf-8")
    assert layer6_quality_matrix.gate(ok_payload, "enterprise")["ok"] is True

    bad_payload = tmp_path / "bad.json"
    bad_payload.write_text(json.dumps(build(59)), encoding="utf-8")
    assert layer6_quality_matrix.gate(bad_payload, "enterprise")["ok"] is False


# ─── Layer 7 ─────────────────────────────────────────────────────────────────

def test_layer7_broker_safety_requires_pass_and_pipnorm_log(tmp_path):
    mb = tmp_path / "mb.json"
    mb.write_text(json.dumps({
        "verdict": "PASS",
        "pf_cv": 0.1,
        "pipnorm_log_seen": ["broker1.log"],
        "details": [],
    }), encoding="utf-8")
    assert layer7_broker_safety.gate(mb)["ok"] is True

    mb.write_text(json.dumps({
        "verdict": "FAIL",
        "pipnorm_log_seen": ["broker1.log"],
        "details": ["PF CV 0.4 > 0.3"],
    }), encoding="utf-8")
    assert layer7_broker_safety.gate(mb)["ok"] is False

    mb.write_text(json.dumps({
        "verdict": "PASS",
        "pipnorm_log_seen": [],
        "details": [],
    }), encoding="utf-8")
    assert layer7_broker_safety.gate(mb)["ok"] is False


# ─── Orchestrator ────────────────────────────────────────────────────────────

def test_orchestrator_fail_fast_stops_at_first_failure(tmp_path):
    # Create a source that fails Layer 1 (unbalanced braces) — orchestrator
    # should never reach layers 2+.
    src = tmp_path / "bad.mq5"
    src.write_text("void OnTick(){ // mismatched braces\n", encoding="utf-8")
    args = argparse.Namespace(
        source=src,
        mode="personal",
        compile_log=None,
        trader_check_report=None,
        state_dir=tmp_path / "state",
        matrix=None,
        multibroker=None,
        journal=None,
    )
    report = orchestrator.run(args)
    assert report.ok is False
    assert len(report.layers) == 1  # fail-fast: only Layer 1 ran
    assert report.layers[0]["layer"] == 1
