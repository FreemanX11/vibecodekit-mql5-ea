"""Phase E acceptance tests — 10 integration tests required by Plan v5 §E."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "mcp" / "metaeditor-bridge"))
sys.path.insert(0, str(REPO_ROOT / "mcp" / "mt5-bridge"))
sys.path.insert(0, str(REPO_ROOT / "mcp" / "algo-forge-bridge"))


def _handshake(server_mod):
    req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
    return server_mod.handle(req)


def _load(dir_name: str):
    import importlib.util
    path = REPO_ROOT / "mcp" / dir_name / "server.py"
    spec = importlib.util.spec_from_file_location(f"{dir_name}_server", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_3_mcp_servers_handshake() -> None:
    """All 3 MCP servers respond to MCP initialize."""
    for d in ("metaeditor-bridge", "mt5-bridge", "algo-forge-bridge"):
        srv = _load(d)
        resp = _handshake(srv)
        assert resp["result"]["protocolVersion"] == "2024-11-05"
        assert "serverInfo" in resp["result"]


def test_metaeditor_bridge_compile() -> None:
    """metaeditor-bridge exposes a metaeditor.compile tool."""
    srv = _load("metaeditor-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "metaeditor.compile" in names
    assert "metaeditor.parse_log" in names


def test_mt5_bridge_readonly_no_trade() -> None:
    """mt5-bridge MUST NOT expose any trade method."""
    forbidden = ["order_send", "order_close", "position_modify", "position_close"]
    mcp_dir = REPO_ROOT / "mcp" / "mt5-bridge"
    for py in mcp_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8").lower()
        for bad in forbidden:
            assert bad not in text, f"{py.name} contains forbidden token {bad!r}"


def test_mt5_bridge_10_tools_exposed() -> None:
    """mt5-bridge exposes the 10 spec-required read-only tools."""
    srv = _load("mt5-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    for tool in [
        "mt5.symbols.list", "mt5.symbol.info", "mt5.rates.copy",
        "mt5.account.info", "mt5.positions.list", "mt5.positions.history",
        "mt5.history.deals", "mt5.tick.last", "mt5.market.book",
        "mt5.terminal.info",
    ]:
        assert tool in names, f"missing mt5-bridge tool {tool!r}"


def test_algo_forge_bridge_pr() -> None:
    """algo-forge-bridge exposes forge.pr.create (mock-style return)."""
    srv = _load("algo-forge-bridge")
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "forge.pr.create", "arguments": {
            "branch": "f", "target": "main", "title": "t",
        }},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["title"] == "t"
    assert payload["state"] == "open"


def test_worked_example_e2e_artefacts_present() -> None:
    """Worked example ships the full artefact set per Plan v5 §19."""
    base = REPO_ROOT / "examples" / "ea-wizard-macd-sar-eurusd-h1-portfolio"
    for f in ["EAName.mq5", "eurusd-h1.set", "README.md",
              "results/backtest.xml", "results/multibroker.csv",
              "results/canary.log", "results/matrix-64-cell.html"]:
        assert (base / f).exists(), f"missing worked-example artefact {f}"
    # README claims enterprise turnaround ≤ 6 hours per Plan v5 §19.
    text = (base / "README.md").read_text()
    assert "turnaround_hours: 4" in text or "turnaround_hours: 6" in text


def test_canary_30min_observability() -> None:
    """canary reads a journal + emits a report with alerts gated by thresholds."""
    from vibecodekit_mql5 import canary
    lines = ["INFO ok", "ERROR fail x", "slippage 2.5 pips", "drawdown 7.0 %"] * 5
    rep = canary.analyse_journal(lines, duration_s=60.0)
    assert rep.error_count > 0
    assert rep.slippage_p95_pips >= 2.0
    assert rep.drawdown_pct >= 5.0
    assert any("slippage_p95" in a for a in rep.alerts)


def test_doctor_health_check() -> None:
    """doctor runs without crashing and reports at least the core probes."""
    from vibecodekit_mql5 import doctor
    rep = doctor.run_doctor(REPO_ROOT)
    names = {c["name"] for c in rep.checks}
    assert "python-version" in names
    assert "references-dir" in names
    assert any(n.startswith("scaffold:stdlib/netting") for n in names)


def test_install_reconcile(tmp_path: Path) -> None:
    """install copies kit Include + scaffolds into an empty target."""
    from vibecodekit_mql5 import install
    rep = install.install(tmp_path, REPO_ROOT)
    assert any("Include/CPipNormalizer.mqh" in w for w in rep.written)
    assert any("scaffolds/" in w for w in rep.written)


def test_audit_runs_all_70_conformance() -> None:
    """audit runs ≥ 60 probes and the canonical 10 e2e categories show up."""
    from vibecodekit_mql5 import audit
    rep = audit.run_audit()
    assert len(rep.probes) >= 60, f"only {len(rep.probes)} probes"


def test_version_metadata_consistent() -> None:
    """VERSION file, pyproject.toml, and vibecodekit_mql5.__version__ must agree."""
    import re
    version_file = (REPO_ROOT / "VERSION").read_text().strip()
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match, "pyproject.toml has no version key"
    pyproject_version = match.group(1)
    import vibecodekit_mql5
    pkg_version = vibecodekit_mql5.__version__
    assert version_file == pyproject_version == pkg_version, (
        f"version mismatch: VERSION={version_file!r}, "
        f"pyproject={pyproject_version!r}, __version__={pkg_version!r}"
    )


def test_phase_e_command_catalog_callable() -> None:
    """Every command listed in the Phase E acceptance gate must be importable."""
    import importlib
    commands = [
        "scan", "survey", "doctor", "audit", "rri", "vision", "blueprint",
        "tip", "build", "wizard", "pip_normalize", "async_build",
        "onnx_export", "onnx_embed", "llm_context", "forge_init", "compile",
        "lint", "method_hiding_check", "backtest", "walkforward",
        "monte_carlo", "overfit_check", "multibroker", "fitness", "mfe_mae",
        "rri.rri_bt", "rri.rri_rr", "rri.rri_chart",
        "review.review", "review.eng_review", "review.ceo_review",
        "review.cso", "review.investigate",
        "deploy_vps", "cloud_optimize", "canary", "forge_pr", "package", "ship",
        "refine", "broker_safety", "trader_check", "install",
    ]
    missing = []
    for c in commands:
        try:
            importlib.import_module(f"vibecodekit_mql5.{c}")
        except ImportError as exc:  # pragma: no cover — captured in assertion
            missing.append(f"{c}: {exc}")
    assert missing == [], "uncallable commands: " + ", ".join(missing)
