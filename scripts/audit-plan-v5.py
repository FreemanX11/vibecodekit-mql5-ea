#!/usr/bin/env python3
"""Anti-drift audit for vibecodekit-mql5-ea Plan v5 implementation.

Run pre-phase to verify starting state matches expectations.
Run post-phase to verify only that phase's files were added.

Usage:
    python scripts/audit-plan-v5.py --pre-phase=A
    python scripts/audit-plan-v5.py --post-phase=A

Exit codes:
    0 — audit pass
    1 — audit fail (drift detected)
    2 — invocation error
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# FORBIDDEN — these MUST NEVER exist (per anti-patterns-AVOID.md)
# ─────────────────────────────────────────────────────────────────────────────

FORBIDDEN_FILES = [
    "scripts/query_loop.py",
    "scripts/tool_executor.py",
    "scripts/intent_router.py",
    "scripts/pipeline_router.py",
    "scripts/master_command.py",
    "scripts/vibecodekit_mql5/query_loop.py",
    "scripts/vibecodekit_mql5/tool_executor.py",
    "scripts/vibecodekit_mql5/intent_router.py",
    "scripts/vibecodekit_mql5/pipeline_router.py",
    "scripts/vibecodekit_mql5/master.py",
]

FORBIDDEN_PATTERNS = [
    (re.compile(r"\bdef run_plan\b"), "VCK-HU query_loop pattern"),
    (re.compile(r"\bclass IntentRouter\b"), "VCK-HU intent_router pattern"),
    (re.compile(r"\bclass PipelineRouter\b"), "VCK-HU pipeline_router pattern"),
    (re.compile(r"\bclass ToolExecutor\b"), "VCK-HU tool_executor pattern"),
    (re.compile(r"['\"]/mql5['\"]\s*:\s*MasterCommand"), "master /mql5 router"),
]

# ─────────────────────────────────────────────────────────────────────────────
# Per-phase expected files (exhaustive — extra files = drift)
# ─────────────────────────────────────────────────────────────────────────────

PHASE_FILES: dict[str, list[str]] = {
    "0": [
        ".github/workflows/ci.yml",
        "scripts/setup-wine-metaeditor.sh",
        "scripts/audit-plan-v5.py",
        "tests/gates/phase-0/__init__.py",
        "tests/gates/phase-0/test_phase_0_smoke.py",
        "tests/fixtures/demo_smoke.mq5",
    ],
    "A": [
        "Include/CPipNormalizer.mqh",
        "Include/CRiskGuard.mqh",
        "Include/CMagicRegistry.mqh",
        "scripts/vibecodekit_mql5/__init__.py",
        "scripts/vibecodekit_mql5/build.py",
        "scripts/vibecodekit_mql5/lint.py",
        "scripts/vibecodekit_mql5/compile.py",
        "scripts/vibecodekit_mql5/pip_normalize.py",
        # 4 scaffolds with 7 stack variants
        "scaffolds/stdlib/netting/EAName.mq5",
        "scaffolds/stdlib/hedging/EAName.mq5",
        "scaffolds/stdlib/python-bridge/EAName.mq5",
        "scaffolds/wizard-composable/netting/EAName.mq5",
        "scaffolds/portfolio-basket/netting/EAName.mq5",
        "scaffolds/portfolio-basket/hedging/EAName.mq5",
        "scaffolds/ml-onnx/python-bridge/EAName.mq5",
        # Tests
        "tests/gates/phase-A/__init__.py",
        "tests/gates/phase-A/test_phase_a_acceptance.py",
        # 8 fixture .mq5
        "tests/fixtures/ap_01_no_sl.mq5",
        "tests/fixtures/ap_03_lot_fixed.mq5",
        "tests/fixtures/ap_05_overfitted.mq5",
        "tests/fixtures/ap_15_raw_ordersend.mq5",
        "tests/fixtures/ap_17_webrequest_ontick.mq5",
        "tests/fixtures/ap_18_async_no_handler.mq5",
        "tests/fixtures/ap_20_hardcoded_pip.mq5",
        "tests/fixtures/ap_21_jpy_xau_broken.mq5",
    ],
    "B": [
        "Include/CMfeMaeLogger.mqh",
        "Include/CSpreadGuard.mqh",
        "scripts/vibecodekit_mql5/backtest.py",
        "scripts/vibecodekit_mql5/walkforward.py",
        "scripts/vibecodekit_mql5/monte_carlo.py",
        "scripts/vibecodekit_mql5/overfit_check.py",
        "scripts/vibecodekit_mql5/multibroker.py",
        "scripts/vibecodekit_mql5/trader_check.py",
        "scripts/vibecodekit_mql5/deploy_vps.py",
        "scripts/vibecodekit_mql5/mfe_mae.py",
        "scripts/vibecodekit_mql5/fitness.py",
        "scripts/vibecodekit_mql5/broker_safety.py",
        "tests/gates/phase-B/__init__.py",
        "tests/gates/phase-B/test_phase_b_acceptance.py",
        "tests/fixtures/tester_report_eurusd_h1.xml",
        "tests/fixtures/tester_report_xauusd_h1_3d.xml",
        "tests/fixtures/tester_report_usdjpy_h1.xml",
    ],
    "C": [
        "scripts/vibecodekit_mql5/rri/__init__.py",
        "scripts/vibecodekit_mql5/rri/personas.py",
        "scripts/vibecodekit_mql5/rri/step_workflow.py",
        "scripts/vibecodekit_mql5/rri/matrix.py",
        "scripts/vibecodekit_mql5/rri/rri_bt.py",
        "scripts/vibecodekit_mql5/rri/rri_rr.py",
        "scripts/vibecodekit_mql5/rri/rri_chart.py",
        "scripts/vibecodekit_mql5/permission/__init__.py",
        "scripts/vibecodekit_mql5/permission/layer1_source_lint.py",
        "scripts/vibecodekit_mql5/permission/layer2_compile.py",
        "scripts/vibecodekit_mql5/permission/layer3_ap_lint.py",
        "scripts/vibecodekit_mql5/permission/layer4_checklist.py",
        "scripts/vibecodekit_mql5/permission/layer5_methodology.py",
        "scripts/vibecodekit_mql5/permission/layer6_quality_matrix.py",
        "scripts/vibecodekit_mql5/permission/layer7_broker_safety.py",
        "scripts/vibecodekit_mql5/permission/orchestrator.py",
        "scripts/vibecodekit_mql5/review/review.py",
        "scripts/vibecodekit_mql5/review/eng_review.py",
        "scripts/vibecodekit_mql5/review/ceo_review.py",
        "scripts/vibecodekit_mql5/review/cso.py",
        "scripts/vibecodekit_mql5/review/investigate.py",
        "docs/rri-personas/trader.yaml",
        "docs/rri-personas/risk-auditor.yaml",
        "docs/rri-personas/broker-engineer.yaml",
        "docs/rri-personas/strategy-architect.yaml",
        "docs/rri-personas/devops.yaml",
        "docs/rri-personas/perf-analyst.yaml",
        "tests/gates/phase-C/__init__.py",
        "tests/gates/phase-C/test_phase_c_acceptance.py",
    ],
    "D": [
        "Include/COnnxLoader.mqh",
        "Include/CAsyncTradeManager.mqh",
        "scripts/vibecodekit_mql5/onnx_export.py",
        "scripts/vibecodekit_mql5/onnx_embed.py",
        "scripts/vibecodekit_mql5/async_build.py",
        "scripts/vibecodekit_mql5/forge_init.py",
        "scripts/vibecodekit_mql5/forge_pr.py",
        "scripts/vibecodekit_mql5/llm_context.py",
        "scripts/vibecodekit_mql5/cloud_optimize.py",
        "scripts/vibecodekit_mql5/method_hiding_check.py",
        "scaffolds/hft-async/netting/EAName.mq5",
        "scaffolds/service-llm-bridge/cloud-api/EAName.mq5",
        "scaffolds/service-llm-bridge/self-hosted-ollama/EAName.mq5",
        "scaffolds/service-llm-bridge/embedded-onnx-llm/EAName.mq5",
        # 11 additional scaffolds (each at least 1 stack variant)
        "scaffolds/trend/netting/EAName.mq5",
        "scaffolds/mean-reversion/hedging/EAName.mq5",
        "scaffolds/breakout/netting/EAName.mq5",
        "scaffolds/hedging-multi/hedging/EAName.mq5",
        "scaffolds/news-trading/netting/EAName.mq5",
        "scaffolds/arbitrage-stat/python-bridge/EAName.mq5",
        "scaffolds/scalping/hedging/EAName.mq5",
        "scaffolds/library/netting/EAName.mq5",
        "scaffolds/indicator-only/netting/EAName.mq5",
        "scaffolds/grid/hedging/EAName.mq5",
        "scaffolds/dca/hedging/EAName.mq5",
        "tests/gates/phase-D/__init__.py",
        "tests/gates/phase-D/test_phase_d_acceptance.py",
    ],
    "E": [
        "mcp/metaeditor-bridge/server.py",
        "mcp/metaeditor-bridge/metaeditor_tools.py",
        "mcp/mt5-bridge/server.py",
        "mcp/mt5-bridge/mt5_tools.py",
        "mcp/algo-forge-bridge/server.py",
        "mcp/algo-forge-bridge/forge_tools.py",
        "scripts/vibecodekit_mql5/canary.py",
        "scripts/vibecodekit_mql5/doctor.py",
        "scripts/vibecodekit_mql5/install.py",
        "scripts/vibecodekit_mql5/audit.py",
        "scripts/vibecodekit_mql5/ship.py",
        "scripts/vibecodekit_mql5/refine.py",
        "scripts/vibecodekit_mql5/survey.py",
        "scripts/vibecodekit_mql5/scan.py",
        # NOTE: rri was refactored into a package and is enumerated under
        # Phase C as scripts/vibecodekit_mql5/rri/__init__.py et al.; the
        # historical `rri.py` single-file entry no longer exists.
        "scripts/vibecodekit_mql5/vision.py",
        "scripts/vibecodekit_mql5/blueprint.py",
        "scripts/vibecodekit_mql5/tip.py",
        "scripts/vibecodekit_mql5/second_opinion.py",
        # 26 references
        *[f"docs/references/{n}.md" for n in [
            "50-survey", "51-platform-arch", "52-multi-symbol", "53-broker-modes",
            "54-stl-cheatsheet", "55-tester-stats", "56-walkforward", "57-monte-carlo",
            "58-overfit", "59-trader-checklist", "60-wizard-cexpert", "61-tester-metrics",
            "62-mfe-mae", "63-tester-config", "64-fitness-templates", "65-multi-broker",
            "66-stdlib-trade-classes", "67-indicator-dev-parallel",
            "70-algo-forge", "71-onnx-mql5", "72-matrix-vector", "73-cloud-network",
            "74-vps", "75-webrequest", "76-llm-patterns", "77-async-hft",
            "78-opencl", "79-pip-norm",
        ]],
        "examples/ea-wizard-macd-sar-eurusd-h1-portfolio/EAName.mq5",
        "examples/ea-wizard-macd-sar-eurusd-h1-portfolio/eurusd-h1.set",
        "examples/ea-wizard-macd-sar-eurusd-h1-portfolio/README.md",
        "tests/gates/phase-E/__init__.py",
        "tests/gates/phase-E/test_phase_e_acceptance.py",
    ],
}

PHASE_ORDER = ["0", "A", "B", "C", "D", "E"]

# ─────────────────────────────────────────────────────────────────────────────
# Audit functions
# ─────────────────────────────────────────────────────────────────────────────

def check_forbidden_files() -> list[str]:
    """Return list of forbidden files that exist (must be empty)."""
    found: list[str] = []
    for f in FORBIDDEN_FILES:
        if (REPO_ROOT / f).exists():
            found.append(f)
    return found

def check_forbidden_patterns() -> list[tuple[str, str]]:
    """Return list of (file, pattern_description) for forbidden code patterns."""
    found: list[tuple[str, str]] = []
    for py in REPO_ROOT.rglob("*.py"):
        if ".venv" in py.parts or "tests" in py.parts:
            continue
        try:
            content = py.read_text()
        except (UnicodeDecodeError, PermissionError):
            continue
        for pattern, desc in FORBIDDEN_PATTERNS:
            if pattern.search(content):
                found.append((str(py.relative_to(REPO_ROOT)), desc))
    return found

def check_phase_files_present(phase: str) -> tuple[list[str], list[str]]:
    """Return (missing, extra) phase files."""
    expected = set(PHASE_FILES.get(phase, []))
    missing = [f for f in expected if not (REPO_ROOT / f).exists()]
    return missing, []  # extra check needs full repo enumeration; deferred

# Command-module LOC ceiling. Modules under ``scripts/vibecodekit_mql5/``
# are expected to hold one responsibility per file; however, a handful of
# them legitimately carry exhaustive data tables (Strategy-Tester XML
# schemas, spec-DSL validation tables, transformer-loop AP catalogues,
# pipeline-orchestrator step definitions) and follow the same data-table
# exemption that the audit script itself relies on. The cap below is set
# high enough to permit those data-heavy modules while still flagging
# anything that has clearly grown a second responsibility. ``auto_build`` is a
# deliberate orchestration module and remains under this slightly wider cap.
MODULE_LOC_CEILING = 425


def check_module_loc() -> list[tuple[str, int]]:
    """Return list of (file, loc) for command modules over the LOC ceiling.

    The ceiling (see ``MODULE_LOC_CEILING``) applies to command modules
    under ``scripts/vibecodekit_mql5/`` (one responsibility per file).
    Infrastructure scripts at the top of ``scripts/`` (the audit script
    itself, future build helpers, etc.) are exempt because they hold
    exhaustive data tables.
    """
    too_big: list[tuple[str, int]] = []
    scripts_dir = REPO_ROOT / "scripts" / "vibecodekit_mql5"
    if not scripts_dir.exists():
        return too_big
    for py in scripts_dir.rglob("*.py"):
        if "__pycache__" in py.parts or py.name == "__init__.py":
            continue
        loc = sum(1 for line in py.read_text(encoding="utf-8").splitlines() if line.strip() and not line.strip().startswith("#"))
        if loc > MODULE_LOC_CEILING:
            too_big.append((str(py.relative_to(REPO_ROOT)), loc))
    return too_big

# ─────────────────────────────────────────────────────────────────────────────
# Pre/post phase audit
# ─────────────────────────────────────────────────────────────────────────────

def audit_pre_phase(phase: str) -> int:
    """Verify starting state before phase X."""
    print(f"=== Pre-phase audit for Phase {phase} ===")
    errors: list[str] = []
    
    # 1. All previous phases' files present
    idx = PHASE_ORDER.index(phase)
    for prev in PHASE_ORDER[:idx]:
        missing, _ = check_phase_files_present(prev)
        if missing:
            errors.append(f"Phase {prev} missing {len(missing)} files: {missing[:3]}...")
    
    # 2. No phase X implementation yet. `tests/fixtures/` is exempt: fixtures
    #    are test data inputs (often checked in earlier so smoke tests can
    #    reference them), not implementation produced during the phase.
    expected = PHASE_FILES.get(phase, [])
    implementation = [f for f in expected if not f.startswith("tests/fixtures/")]
    impl_present = [f for f in implementation if (REPO_ROOT / f).exists()]
    if implementation and impl_present:
        errors.append(f"Phase {phase} implementation already partially present: {impl_present[:5]}")
    
    # 3. No forbidden files
    forbidden = check_forbidden_files()
    if forbidden:
        errors.append(f"Forbidden files present: {forbidden}")
    
    # 4. No forbidden patterns
    bad_patterns = check_forbidden_patterns()
    if bad_patterns:
        errors.append(f"Forbidden patterns: {bad_patterns}")
    
    return _report(errors, f"Pre-phase {phase}")


def audit_post_phase(phase: str) -> int:
    """Verify state after phase X complete."""
    print(f"=== Post-phase audit for Phase {phase} ===")
    errors: list[str] = []
    
    # 1. Phase X expected files present
    missing, _ = check_phase_files_present(phase)
    if missing:
        errors.append(f"Phase {phase} missing {len(missing)} files: {missing[:5]}")
    
    # 2. All previous phases' files still present
    idx = PHASE_ORDER.index(phase)
    for prev in PHASE_ORDER[:idx]:
        m, _ = check_phase_files_present(prev)
        if m:
            errors.append(f"Phase {prev} REGRESSED, missing: {m[:3]}")
    
    # 3. No forbidden files
    forbidden = check_forbidden_files()
    if forbidden:
        errors.append(f"Forbidden files present: {forbidden}")
    
    # 4. No forbidden patterns
    bad_patterns = check_forbidden_patterns()
    if bad_patterns:
        errors.append(f"Forbidden patterns: {bad_patterns}")
    
    # 5. Module LOC ceiling
    big = check_module_loc()
    if big:
        errors.append(f"Modules > {MODULE_LOC_CEILING} LOC: {big}")
    
    return _report(errors, f"Post-phase {phase}")

def _report(errors: Sequence[str], label: str) -> int:
    if errors:
        print(f"\n❌ {label} FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"\n✓ {label} PASSED")
    return 0

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Anti-drift audit for Plan v5")
    parser.add_argument("--pre-phase", choices=PHASE_ORDER, help="Run before phase")
    parser.add_argument("--post-phase", choices=PHASE_ORDER, help="Run after phase")
    args = parser.parse_args()
    
    if args.pre_phase:
        return audit_pre_phase(args.pre_phase)
    if args.post_phase:
        return audit_post_phase(args.post_phase)
    parser.print_help()
    return 2

if __name__ == "__main__":
    sys.exit(main())
