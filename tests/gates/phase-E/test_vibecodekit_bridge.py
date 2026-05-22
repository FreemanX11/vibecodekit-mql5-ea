"""Phase E unit tests — vibecodekit-bridge MCP server.

Mirrors ``test_mcp_servers.py``. The bridge ships 4 PR-1 tools
(``spec.from_prompt``, ``spec.validate``, ``build.auto``,
``verify.permission``), 7 PR-2 verify tools (``verify.lint``,
``verify.lint_best_practice``, ``verify.method_hiding``,
``verify.trader17``, ``verify.compile``, ``verify.broker_safety``,
``verify.audit``), and 7 PR-3 runtime/statistical tools
(``verify.backtest``, ``verify.walkforward``, ``verify.montecarlo``,
``verify.multibroker``, ``verify.fitness``, ``verify.mfe_mae``,
``verify.overfit``), 5 PR-4 review/RRI tools (``review.eng``,
``review.cso``, ``review.ceo``, ``review.investigate``,
``rri.persona``), 2 PR-5 ship-stage tools (``dashboard.publish``,
``forge.pr.create``), and 4 PR-7 discovery / fix-loop helpers
(``discover.doctor``, ``discover.scan``, ``discover.llm_context``,
``verify.auto_fix``). These tests cover the JSON-RPC envelope, the
tool list shape, and a hermetic round-trip through every tool.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load_server():
    path = REPO_ROOT / "mcp" / "vibecodekit-bridge" / "server.py"
    spec = importlib.util.spec_from_file_location("vibecodekit_bridge_server", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _call(srv, name: str, arguments: dict, rid: int = 1):
    resp = srv.handle({
        "jsonrpc": "2.0", "id": rid, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert "result" in resp, resp
    return json.loads(resp["result"]["content"][0]["text"])


def _call_for_error(srv, name: str, arguments: dict, rid: int = 1) -> dict:
    """Like :func:`_call` but expects a JSON-RPC error envelope."""
    resp = srv.handle({
        "jsonrpc": "2.0", "id": rid, "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    assert "error" in resp, resp
    return resp["error"]


def test_initialize_returns_protocol_version() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    info = resp["result"]
    assert info["protocolVersion"] == "2024-11-05"
    assert info["serverInfo"]["name"] == "vibecodekit-bridge"


def test_tools_list_shape() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"spec.from_prompt", "spec.validate", "build.auto", "verify.permission"} <= names
    for tool in tools:
        assert "description" in tool and tool["description"], tool["name"]
        assert "inputSchema" in tool, tool["name"]
        assert tool["inputSchema"]["type"] == "object"


def test_unknown_method_returns_minus_32601() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 3, "method": "no/such/method"})
    assert resp["error"]["code"] == -32601


def test_unknown_tool_returns_minus_32601() -> None:
    srv = _load_server()
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 4, "method": "tools/call",
        "params": {"name": "spec.no_such_tool", "arguments": {}},
    })
    assert resp["error"]["code"] == -32601


def test_notification_returns_none() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


def test_spec_from_prompt_basic() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.from_prompt", {
        "prompt": "build EA trend EURUSD H1 risk 0.5% SL 30 TP 60 macd or sar",
    })
    assert payload["ok"] is True
    spec = payload["spec"]
    assert spec["preset"] == "trend"
    assert spec["symbol"] == "EURUSD"
    assert spec["timeframe"] == "H1"
    assert spec["risk"]["sl_pips"] == 30
    assert spec["risk"]["tp_pips"] == 60
    assert "macd" in payload["yaml"] and "sar" in payload["yaml"]


def test_spec_from_prompt_strict_flags_defaults() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.from_prompt", {"prompt": "", "strict": True})
    assert payload["ok"] is False
    assert "defaulted" in payload


def test_spec_validate_accepts_minimum_spec() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "MyEA", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
        },
    })
    assert payload["ok"] is True
    assert payload["errors"] == []
    assert payload["spec"]["mode"] == "personal"


def test_spec_validate_rejects_unknown_preset() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {"name": "X", "preset": "nonsense", "stack": "netting",
                 "symbol": "EURUSD", "timeframe": "H1"},
    })
    assert payload["ok"] is False
    assert any("nonsense" in e for e in payload["errors"])


def test_spec_validate_collects_multiple_errors_at_once() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {"spec": {"name": "X"}})
    assert payload["ok"] is False
    # At least the missing-required-fields error must be present.
    assert any("missing required fields" in e for e in payload["errors"])


def test_build_auto_renders_project_with_skips() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        payload = _call(srv, "build.auto", {
            "spec": {
                "name": "WizardEA", "preset": "wizard-composable", "stack": "netting",
                "symbol": "EURUSD", "timeframe": "H1",
            },
            "out_dir": tmp,
            "skip_compile": True,
            "skip_gate": True,
            "skip_dashboard": True,
            "force": True,
        })
        assert payload["ok"] is True
        names = [s["name"] for s in payload["stages"]]
        assert names == ["build", "lint", "compile", "gate"]
        # Lint stage must have actually run (not skipped).
        assert payload["stages"][1].get("skipped") in (False, None)
        # Compile + gate were explicitly skipped.
        assert payload["stages"][2]["skipped"] is True
        assert payload["stages"][3]["skipped"] is True
        # Verify the rendered .mq5 actually exists.
        assert (Path(tmp) / "WizardEA.mq5").is_file()


def test_build_auto_rejects_invalid_spec() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        payload = _call(srv, "build.auto", {
            "spec": {"name": "X", "preset": "bogus"},
            "out_dir": tmp,
        })
        assert payload["ok"] is False
        assert payload.get("stage") == "validate"


def test_verify_permission_runs_against_rendered_ea() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        # First render an EA we can point the permission orchestrator at.
        _call(srv, "build.auto", {
            "spec": {
                "name": "PermEA", "preset": "wizard-composable", "stack": "netting",
                "symbol": "EURUSD", "timeframe": "H1",
            },
            "out_dir": tmp,
            "skip_compile": True, "skip_gate": True, "skip_dashboard": True,
            "force": True,
        })
        mq5_path = Path(tmp) / "PermEA.mq5"
        assert mq5_path.is_file()

        payload = _call(srv, "verify.permission", {
            "source": str(mq5_path),
            "mode": "personal",
        })
        assert payload["mode"] == "personal"
        # Layers list must include layer 1 (source-lint).
        layers = payload["layers"]
        assert any(L.get("layer") == 1 for L in layers)


def test_verify_permission_missing_file() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.permission", {"source": "/tmp/does-not-exist.mq5"})
    assert payload["ok"] is False


# ─────────────────────────────────────────────────────────────────────────────
# PR-2: 7 verify tools
# ─────────────────────────────────────────────────────────────────────────────

_AP1_SOURCE = (
    "#property strict\n"
    "void OnTick(){ trade.Buy(0.1); }\n"
)


def test_tools_list_includes_pr2_verify_tools() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 20, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {
        "verify.lint", "verify.lint_best_practice", "verify.method_hiding",
        "verify.trader17", "verify.compile", "verify.broker_safety",
        "verify.audit",
    } <= names


def test_verify_lint_flags_ap1_missing_sl() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        mq5 = Path(tmp) / "ap1.mq5"
        mq5.write_text(_AP1_SOURCE, encoding="utf-8")
        payload = _call(srv, "verify.lint", {"source": str(mq5)})
        assert payload["ok"] is False
        codes = [e["code"] for e in payload["errors"]]
        assert "AP-1" in codes
        assert payload["n_errors"] >= 1


def test_verify_lint_missing_file() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.lint", {"source": "/tmp/does-not-exist.mq5"})
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_verify_lint_best_practice_returns_grouped_findings() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        mq5 = Path(tmp) / "ap1.mq5"
        mq5.write_text(_AP1_SOURCE, encoding="utf-8")
        payload = _call(srv, "verify.lint_best_practice", {"source": str(mq5)})
        # WARN-only tier: ok is informational only and stays True.
        assert payload["ok"] is True
        assert "by_code" in payload
        # All WARN-tier AP codes must appear as keys.
        for code in ("AP-2", "AP-4", "AP-6", "AP-7", "AP-8", "AP-9", "AP-10",
                     "AP-11", "AP-12", "AP-13", "AP-14", "AP-16", "AP-19",
                     "AP-22", "AP-23"):
            assert code in payload["by_code"], code


def test_verify_method_hiding_clean_file_passes() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        mq5 = Path(tmp) / "clean.mq5"
        mq5.write_text("void OnTick(){}\n", encoding="utf-8")
        payload = _call(srv, "verify.method_hiding",
                        {"source": str(mq5), "target_build": 5260})
        assert payload["ok"] is True
        assert payload["issues"] == []
        assert payload["target_build"] == 5260


def test_verify_trader17_returns_per_check_results() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        mq5 = Path(tmp) / "skel.mq5"
        mq5.write_text(_AP1_SOURCE, encoding="utf-8")
        payload = _call(srv, "verify.trader17",
                        {"source": str(mq5), "mode": "personal"})
        # Empty skeleton fails the 17-point checklist — ok is False.
        assert payload["ok"] is False
        assert payload["mode"] == "personal"
        assert "summary" in payload and "/17" in payload["summary"]
        # Every check key must have a verdict.
        for verdict in payload["checks"].values():
            assert verdict in ("PASS", "WARN", "N/A", "FAIL")


def test_verify_broker_safety_flags_missing_fields() -> None:
    srv = _load_server()
    with tempfile.TemporaryDirectory() as tmp:
        mq5 = Path(tmp) / "ap1.mq5"
        mq5.write_text(_AP1_SOURCE, encoding="utf-8")
        payload = _call(srv, "verify.broker_safety", {
            "source": str(mq5),
            "symbol_info": {"filling_modes": ["FOK"],
                            "volume_min": 0.01, "volume_step": 0.01},
        })
        # No InpLot / InpMagic / ORDER_FILLING_* declared → all flags WARN.
        assert payload["ok"] is False
        for flag in ("fill_policy_supported", "min_lot_respected",
                     "lot_step_aligned", "magic_in_range"):
            assert payload[flag] in ("PASS", "WARN", "FAIL")


def test_verify_audit_runs_kit_conformance_battery() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.audit", {})
    # The kit ships with all probes passing on main.
    assert payload["ok"] is True
    assert payload["total"] == payload["passed"]
    assert payload["total"] >= 60  # ~70 probes — defensive lower bound


def test_spec_validate_accepts_prop_firm_block() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "FundedEA", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
            "prop_firm": {"daily_dd_pct": 5.0, "max_dd_pct": 10.0,
                          "news_block_min": 30, "weekend_flat": True},
        },
    })
    assert payload["ok"] is True
    assert payload["spec"]["prop_firm"]["daily_dd_pct"] == 5.0
    assert payload["spec"]["prop_firm"]["weekend_flat"] is True


def test_spec_validate_accepts_time_exit_block() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "TimedEA", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
            "time_exit": {"close_on_friday": True, "max_trade_hours": 24,
                          "session_start_hour": 8, "session_end_hour": 20},
        },
    })
    assert payload["ok"] is True
    te = payload["spec"]["time_exit"]
    assert te["close_on_friday"] is True
    assert te["max_trade_hours"] == 24
    assert te["session_end_hour"] == 20


def test_spec_validate_accepts_stealth_block() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "StealthEA", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
            "stealth": {"randomize_slippage_pips": 2,
                        "randomize_comment_pool": ["sig-a", "sig-b"],
                        "split_orders": True},
        },
    })
    assert payload["ok"] is True
    st = payload["spec"]["stealth"]
    assert st["randomize_slippage_pips"] == 2
    assert st["randomize_comment_pool"] == ["sig-a", "sig-b"]
    assert st["split_orders"] is True


def test_spec_validate_rejects_invalid_prop_firm_value() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "X", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
            "prop_firm": {"daily_dd_pct": -1.0},
        },
    })
    assert payload["ok"] is False
    assert any("daily_dd_pct" in e for e in payload["errors"])


def test_spec_validate_rejects_unknown_extension_keys() -> None:
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "X", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
            "stealth": {"bogus_field": True},
        },
    })
    assert payload["ok"] is False
    assert any("stealth" in e and "bogus_field" in e for e in payload["errors"])


def test_spec_validate_backcompat_no_extension_blocks() -> None:
    """Specs that don't use prop_firm/time_exit/stealth must still validate."""
    srv = _load_server()
    payload = _call(srv, "spec.validate", {
        "spec": {
            "name": "Plain", "preset": "trend", "stack": "netting",
            "symbol": "EURUSD", "timeframe": "H1",
        },
    })
    assert payload["ok"] is True
    # The extension blocks should not appear in the normalised output
    # when the input doesn't supply them.
    assert "prop_firm" not in payload["spec"]
    assert "time_exit" not in payload["spec"]
    assert "stealth" not in payload["spec"]


# ─────────────────────────────────────────────────────────────────────────────
# PR-3: 7 runtime / statistical verify tools
# ─────────────────────────────────────────────────────────────────────────────

FIXTURES = REPO_ROOT / "tests" / "fixtures"
EURUSD_XML = FIXTURES / "tester_report_eurusd_h1.xml"
USDJPY_XML = FIXTURES / "tester_report_usdjpy_h1.xml"
XAUUSD_XML = FIXTURES / "tester_report_xauusd_h1_3d.xml"


def test_tools_list_includes_pr3_runtime_tools() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 40, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {
        "verify.backtest", "verify.walkforward", "verify.montecarlo",
        "verify.multibroker", "verify.fitness", "verify.mfe_mae",
        "verify.overfit",
    } <= names
    # PR-1 + PR-2 + PR-3 = 18 tools total. Use ≤ to allow future PRs.
    assert len(names) >= 18


def test_verify_backtest_parses_eurusd_fixture() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.backtest", {"xml_report_path": str(EURUSD_XML)})
    assert payload["ok"] is True
    r = payload["report"]
    assert r["symbol"] == "EURUSD"
    assert r["profit_factor"] == 1.78
    assert r["sharpe"] == 0.42
    assert r["total_trades"] == 342


def test_verify_backtest_missing_file() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.backtest",
                    {"xml_report_path": "/tmp/does-not-exist.xml"})
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_verify_walkforward_correlates_eurusd_and_usdjpy() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.walkforward", {
        "is_xml_path":  str(EURUSD_XML),
        "oos_xml_path": str(USDJPY_XML),
    })
    assert "is_sharpe" in payload
    assert "oos_sharpe" in payload
    assert "correlation" in payload
    assert payload["verdict"] in ("PASS", "WARN", "FAIL")
    # ok mirrors verdict.
    assert payload["ok"] is (payload["verdict"] == "PASS")


def test_verify_walkforward_missing_file() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.walkforward", {
        "is_xml_path":  "/tmp/missing-is.xml",
        "oos_xml_path": str(USDJPY_XML),
    })
    assert payload["ok"] is False
    assert "is_xml_path" in payload["error"]


def test_verify_montecarlo_inline_returns_seeded() -> None:
    srv = _load_server()
    returns = [10.0, -5.0, 8.0, -3.0, 12.0, -7.0, 6.0] * 10
    payload = _call(srv, "verify.montecarlo", {
        "returns": returns, "reported_dd": 30.0,
        "n_sims": 200, "seed": 42,
    })
    # Verdict depends on bootstrap distribution vs threshold; ok mirrors it.
    assert payload["verdict"] in ("PASS", "FAIL")
    assert payload["n_sims"] == 200
    assert payload["p95_dd"] >= payload["p50_dd"]
    assert payload["ok"] is (payload["verdict"] == "PASS")


def test_verify_montecarlo_requires_returns_source() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.montecarlo", {"reported_dd": 10.0})
    assert payload["ok"] is False
    assert "returns" in payload["error"]


def test_verify_montecarlo_rejects_both_sources() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.montecarlo", {
        "returns": [1.0, -1.0], "returns_csv_path": "/tmp/x.csv",
        "reported_dd": 5.0,
    })
    assert payload["ok"] is False
    assert "mutually exclusive" in payload["error"]


def test_verify_montecarlo_rejects_non_numeric_returns() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.montecarlo", {
        "returns": [1.0, "bad"], "reported_dd": 5.0,
    })
    assert payload["ok"] is False
    assert "list of numbers" in payload["error"]


def test_verify_multibroker_three_fixtures() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.multibroker", {
        "report_paths": [str(EURUSD_XML), str(USDJPY_XML), str(XAUUSD_XML)],
    })
    for key in ("pf_mean", "pf_stdev", "pf_cv", "sharpe_mean", "sharpe_stdev",
                "dd_diff", "verdict"):
        assert key in payload, key
    assert payload["verdict"] in ("PASS", "FAIL")
    assert payload["ok"] is (payload["verdict"] == "PASS")


def test_verify_multibroker_requires_at_least_two_paths() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.multibroker", {
        "report_paths": [str(EURUSD_XML)],
    })
    assert payload["ok"] is False
    assert "at least 2" in payload["error"]


def test_verify_multibroker_rejects_missing_file() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.multibroker", {
        "report_paths": [str(EURUSD_XML), "/tmp/bogus.xml"],
    })
    assert payload["ok"] is False
    assert "not found" in payload["error"]


def test_verify_fitness_lists_when_no_template() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.fitness", {})
    assert payload["ok"] is True
    # Kit ships 5 templates today; assert all five are present.
    for name in ("sharpe", "sortino", "profit-dd", "expectancy", "walkforward"):
        assert name in payload["templates"], name


def test_verify_fitness_returns_expression_for_named_template() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.fitness", {"template": "sharpe"})
    assert payload["ok"] is True
    assert payload["template"] == "sharpe"
    assert "TesterStatistics" in payload["expression"]
    assert "STAT_SHARPE_RATIO" in payload["expression"]


def test_verify_fitness_unknown_template() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.fitness", {"template": "no_such_template"})
    assert payload["ok"] is False
    assert "unknown" in payload["error"]
    assert "sharpe" in payload["available"]


def test_verify_mfe_mae_from_inline_csv() -> None:
    srv = _load_server()
    csv_text = (
        "profit,mfe,mae\n"
        "10,15,2\n-5,3,8\n8,12,3\n-2,4,5\n6,10,4\n"
    )
    payload = _call(srv, "verify.mfe_mae", {"csv_text": csv_text})
    assert payload["ok"] is True
    assert payload["n_trades"] == 5
    assert -1.0 <= payload["mfe_profit_corr"] <= 1.0
    assert -1.0 <= payload["mae_profit_corr"] <= 1.0


def test_verify_mfe_mae_requires_one_source() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.mfe_mae", {})
    assert payload["ok"] is False
    assert "required" in payload["error"]


def test_verify_mfe_mae_rejects_both_sources() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.mfe_mae", {
        "csv_path": "/tmp/x.csv", "csv_text": "profit,mfe,mae\n1,2,3\n",
    })
    assert payload["ok"] is False
    assert "mutually exclusive" in payload["error"]


def test_verify_mfe_mae_rejects_bad_header() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.mfe_mae", {
        "csv_text": "wrong,header,here\n1,2,3\n",
    })
    assert payload["ok"] is False
    assert "expected header" in payload["error"]


def test_verify_overfit_pass_threshold() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.overfit", {
        "is_sharpe": 1.0, "oos_sharpe": 0.8,
    })
    assert payload["ratio"] == 0.8
    assert payload["verdict"] == "PASS"
    assert payload["ok"] is True


def test_verify_overfit_fail_threshold() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.overfit", {
        "is_sharpe": 1.0, "oos_sharpe": 0.1,
    })
    assert payload["verdict"] == "FAIL"
    assert payload["ok"] is False


def test_verify_overfit_rejects_non_numeric() -> None:
    srv = _load_server()
    payload = _call(srv, "verify.overfit", {
        "is_sharpe": "not-a-number", "oos_sharpe": 0.5,
    })
    assert payload["ok"] is False
    assert "must be numbers" in payload["error"]


# ─────────────────────────────────────────────────────────────────────────────
# PR-4: review personas + generic RRI
# ─────────────────────────────────────────────────────────────────────────────


def test_tools_list_includes_pr4_review_tools() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 100, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {
        "review.eng", "review.cso", "review.ceo",
        "review.investigate", "rri.persona",
    } <= names
    # PR-1 + PR-2 + PR-3 + PR-4 = 23 tools total. Use >= to allow future PRs.
    assert len(names) >= 23


def test_review_eng_default_steps_and_personas() -> None:
    srv = _load_server()
    payload = _call(srv, "review.eng", {"mode": "personal"})
    assert payload["ok"] is True
    assert payload["mode"] == "personal"
    assert payload["personas"] == ["broker-engineer", "devops"]
    assert payload["steps"] == ["build", "verify"]
    md = payload["markdown"]
    assert "# Engineering review" in md
    assert "broker-engineer" in md
    assert "## Step templates" in md


def test_review_eng_custom_steps() -> None:
    srv = _load_server()
    payload = _call(srv, "review.eng", {"mode": "team", "steps": ["verify"]})
    assert payload["ok"] is True
    assert payload["steps"] == ["verify"]
    assert payload["mode"] == "team"


def test_review_eng_rejects_unknown_mode() -> None:
    srv = _load_server()
    payload = _call(srv, "review.eng", {"mode": "godmode"})
    assert payload["ok"] is False
    assert "mode must be one of" in payload["error"]


def test_review_eng_rejects_unknown_step() -> None:
    srv = _load_server()
    payload = _call(srv, "review.eng", {"steps": ["scan", "warp-drive"]})
    assert payload["ok"] is False
    assert "warp-drive" in payload["error"]


def test_review_cso_single_persona() -> None:
    srv = _load_server()
    payload = _call(srv, "review.cso", {"mode": "enterprise"})
    assert payload["ok"] is True
    assert payload["personas"] == ["risk-auditor"]
    assert payload["mode"] == "enterprise"
    assert payload["steps"] == ["rri", "verify"]
    assert "Chief Safety Officer review" in payload["markdown"]


def test_review_ceo_default_steps() -> None:
    srv = _load_server()
    payload = _call(srv, "review.ceo", {})  # all defaults
    assert payload["ok"] is True
    assert payload["mode"] == "personal"
    assert payload["personas"] == ["trader", "strategy-architect"]
    assert payload["steps"] == ["vision", "refine"]


def test_review_investigate_default_steps() -> None:
    srv = _load_server()
    payload = _call(srv, "review.investigate", {"mode": "team"})
    assert payload["ok"] is True
    assert payload["personas"] == ["perf-analyst", "strategy-architect"]
    assert payload["steps"] == ["scan", "rri"]
    assert "## Hypotheses" in payload["markdown"]


def test_rri_persona_lists_available_when_omitted() -> None:
    srv = _load_server()
    payload = _call(srv, "rri.persona", {})
    assert payload["ok"] is True
    assert "trader" in payload["available_personas"]
    assert len(payload["available_personas"]) == 6
    assert "verify" in payload["available_steps"]
    assert len(payload["available_steps"]) == 8
    assert payload["available_modes"] == ["personal", "team", "enterprise"]


def test_rri_persona_renders_trader_verify_personal() -> None:
    srv = _load_server()
    payload = _call(srv, "rri.persona", {
        "persona": "trader", "step": "verify", "mode": "personal",
    })
    assert payload["ok"] is True
    assert payload["persona"] == "trader"
    assert payload["step"] == "verify"
    assert payload["mode"] == "personal"
    md = payload["markdown"]
    assert "persona: trader" in md
    assert "step: verify" in md
    assert "## Step template" in md


def test_rri_persona_defaults_step_to_verify() -> None:
    srv = _load_server()
    payload = _call(srv, "rri.persona", {"persona": "risk-auditor"})
    assert payload["ok"] is True
    assert payload["step"] == "verify"
    assert payload["mode"] == "personal"


def test_rri_persona_rejects_unknown_persona() -> None:
    srv = _load_server()
    payload = _call(srv, "rri.persona", {"persona": "ceo"})
    assert payload["ok"] is False
    assert "unknown persona" in payload["error"]


def test_rri_persona_rejects_unknown_step() -> None:
    srv = _load_server()
    payload = _call(srv, "rri.persona", {"persona": "trader", "step": "warp"})
    assert payload["ok"] is False
    assert "unknown step" in payload["error"]


def test_rri_persona_enterprise_has_more_questions_than_personal() -> None:
    srv = _load_server()
    personal = _call(srv, "rri.persona", {
        "persona": "trader", "mode": "personal",
    })["markdown"]
    enterprise = _call(srv, "rri.persona", {
        "persona": "trader", "mode": "enterprise",
    })["markdown"]
    # enterprise mode = 25 q vs personal = 5 q per persona
    assert enterprise.count("- [ ] **") > personal.count("- [ ] **")


# ─────────────────────────────────────────────────────────────────────────────
# PR-5: dashboard.publish + forge.pr.create chaining
# ─────────────────────────────────────────────────────────────────────────────


def test_tools_list_includes_pr5_ship_tools() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 200, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"dashboard.publish", "forge.pr.create"} <= names
    # PR-1 + PR-2 + PR-3 + PR-4 + PR-5 = 25 tools total.
    assert len(names) >= 25


def test_dashboard_publish_renders_and_returns_file_uri(tmp_path: Path) -> None:
    srv = _load_server()
    payload = _call(srv, "dashboard.publish", {
        "name": "TestEA",
        "ok": True,
        "stages": [
            {"name": "build",   "ok": True,  "skipped": False},
            {"name": "lint",    "ok": True,  "skipped": False},
            {"name": "compile", "ok": True,  "skipped": True},
            {"name": "gate",    "ok": True,  "skipped": False},
        ],
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is True
    assert payload["public_url"].startswith("file://")
    assert payload["public_url"].endswith("/quality-matrix.html")
    assert payload["error"] is None
    assert payload["command"] is None
    assert Path(payload["local_path"]).is_file()


def test_dashboard_publish_with_html_path_skips_render(tmp_path: Path) -> None:
    srv = _load_server()
    html = tmp_path / "preexisting.html"
    html.write_text("<html><body>cached</body></html>", encoding="utf-8")
    payload = _call(srv, "dashboard.publish", {"html_path": str(html)})
    assert payload["ok"] is True
    assert payload["public_url"] == html.as_uri()
    assert payload["local_path"] == str(html)


def test_dashboard_publish_invokes_publish_cmd(tmp_path: Path) -> None:
    srv = _load_server()
    html = tmp_path / "x.html"
    html.write_text("<html></html>", encoding="utf-8")
    # printf-based stub: emit a URL on the last stdout line.
    cmd = "sh -c 'echo https://cdn.example.com/$(basename \"$1\")' --"
    payload = _call(srv, "dashboard.publish", {
        "html_path": str(html),
        "publish_cmd": cmd,
    })
    assert payload["ok"] is True
    assert payload["public_url"] == "https://cdn.example.com/x.html"
    assert payload["command"] == cmd


def test_dashboard_publish_rejects_missing_name(tmp_path: Path) -> None:
    srv = _load_server()
    payload = _call(srv, "dashboard.publish", {
        "stages": [{"name": "build", "ok": True, "skipped": False}],
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is False
    assert "name is required" in payload["error"]


def test_dashboard_publish_rejects_missing_stages(tmp_path: Path) -> None:
    srv = _load_server()
    payload = _call(srv, "dashboard.publish", {
        "name": "X",
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is False
    assert "stages" in payload["error"]


def test_dashboard_publish_rejects_missing_out_dir() -> None:
    srv = _load_server()
    payload = _call(srv, "dashboard.publish", {
        "name": "X",
        "stages": [{"name": "build", "ok": True, "skipped": False}],
    })
    assert payload["ok"] is False
    assert "out_dir is required" in payload["error"]


def test_forge_pr_create_dry_run_without_token(monkeypatch) -> None:
    monkeypatch.delenv("MQL5_FORGE_TOKEN", raising=False)
    srv = _load_server()
    payload = _call(srv, "forge.pr.create", {
        "repo":  "me/strategy",
        "head":  "devin/feat",
        "base":  "main",
        "title": "EA build",
        "body":  "Dashboard: https://example.com/dashboard.html",
    })
    assert payload["ok"] is False
    assert payload["dry_run"] is True
    assert "no MQL5_FORGE_TOKEN" in payload["reason"]
    assert payload["endpoint"].endswith("/repos/me/strategy/pulls")
    assert payload["planned_payload"]["title"] == "EA build"
    assert payload["planned_payload"]["base"] == "main"


def test_forge_pr_create_explicit_dry_run_flag(monkeypatch) -> None:
    monkeypatch.setenv("MQL5_FORGE_TOKEN", "fake-token")
    srv = _load_server()
    payload = _call(srv, "forge.pr.create", {
        "repo":   "owner/repo",
        "head":   "feat/x",
        "title":  "feat: x",
        "dry_run": True,
    })
    assert payload["ok"] is False
    assert payload["dry_run"] is True
    assert payload["reason"] == "dry_run=true"


def test_forge_pr_create_defaults_base_to_main(monkeypatch) -> None:
    monkeypatch.delenv("MQL5_FORGE_TOKEN", raising=False)
    srv = _load_server()
    payload = _call(srv, "forge.pr.create", {
        "repo":  "me/strategy",
        "head":  "devin/x",
        "title": "x",
    })
    assert payload["planned_payload"]["base"] == "main"


def test_forge_pr_create_rejects_missing_repo() -> None:
    """PR-13: missing required keys now surface as JSON-RPC -32602."""
    srv = _load_server()
    err = _call_for_error(srv, "forge.pr.create", {"head": "x", "title": "y"})
    assert err["code"] == -32602
    assert "repo" in err["message"]
    assert "forge.pr.create" in err["message"]


def test_forge_pr_create_rejects_missing_head() -> None:
    srv = _load_server()
    err = _call_for_error(srv, "forge.pr.create", {"repo": "a/b", "title": "y"})
    assert err["code"] == -32602
    assert "head" in err["message"]


def test_forge_pr_create_rejects_missing_title() -> None:
    srv = _load_server()
    err = _call_for_error(srv, "forge.pr.create", {"repo": "a/b", "head": "x"})
    assert err["code"] == -32602
    assert "title" in err["message"]


def test_pr5_chain_dashboard_url_into_forge_pr_body(
    tmp_path: Path, monkeypatch
) -> None:
    """End-to-end MCP chain: dashboard.publish -> forge.pr.create.

    Demonstrates the exact pattern the plan β rút gọn roadmap envisaged —
    an AI agent gets the public dashboard URL from the first tool and
    feeds it into the PR body of the second.
    """
    monkeypatch.delenv("MQL5_FORGE_TOKEN", raising=False)
    srv = _load_server()
    dash = _call(srv, "dashboard.publish", {
        "name": "MeanReversion",
        "ok": True,
        "stages": [
            {"name": "build", "ok": True, "skipped": False},
            {"name": "lint",  "ok": True, "skipped": False},
            {"name": "gate",  "ok": True, "skipped": False},
        ],
        "out_dir": str(tmp_path),
    })
    assert dash["ok"] is True
    pr_body = f"Quality matrix dashboard: {dash['public_url']}"
    pr = _call(srv, "forge.pr.create", {
        "repo":  "trader/mean-rev",
        "head":  "devin/build-1",
        "title": "MeanReversion EA build",
        "body":  pr_body,
    })
    assert pr["dry_run"] is True
    assert pr["planned_payload"]["body"] == pr_body
    assert dash["public_url"] in pr["planned_payload"]["body"]


# ─────────────────────────────────────────────────────────────────────────────
# PR-7 — discovery / fix-loop helpers
# (discover.doctor, discover.scan, discover.llm_context, verify.auto_fix)
# ─────────────────────────────────────────────────────────────────────────────


def test_tools_list_includes_pr7_discovery_tools() -> None:
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 7, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {
        "discover.doctor",
        "discover.scan",
        "discover.llm_context",
        "verify.auto_fix",
    } <= names
    # PR-1 (4) + PR-2 (7) + PR-3 (7) + PR-4 (5) + PR-5 (2) + PR-7 (4) + PR-19 (1)
    assert len(names) == 30


def test_discover_doctor_returns_checks_list() -> None:
    srv = _load_server()
    result = _call(srv, "discover.doctor", {})
    assert "ok" in result
    assert isinstance(result.get("checks"), list)
    assert result["checks"], "doctor should always report at least one check"
    # Each check is a dict with a 'name' field (kit's run_doctor contract).
    first = result["checks"][0]
    assert isinstance(first, dict) and "name" in first


def test_discover_scan_inventories_workspace(tmp_path: Path) -> None:
    (tmp_path / "main.mq5").write_text("// EA\nvoid OnTick(){}\n", encoding="utf-8")
    (tmp_path / "helper.mqh").write_text("// include\n", encoding="utf-8")
    (tmp_path / "model.onnx").write_bytes(b"\x00\x01\x02")
    sub = tmp_path / "tester"
    sub.mkdir()
    (sub / "params.set").write_text("k=v\n", encoding="utf-8")
    srv = _load_server()
    result = _call(srv, "discover.scan", {"root": str(tmp_path)})
    assert result["ok"] is True
    counts = result["counts"]
    assert counts.get("ea-source") == 1
    assert counts.get("include") == 1
    assert counts.get("onnx-model") == 1
    assert counts.get("tester-set") == 1
    # All four classified files should appear in the inventory.
    kinds = {f["kind"] for f in result["files"]}
    assert {"ea-source", "include", "onnx-model", "tester-set"} <= kinds


def test_discover_scan_defaults_to_cwd_when_root_omitted(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "ea.mq5").write_text("// EA", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    srv = _load_server()
    result = _call(srv, "discover.scan", {})
    assert result["ok"] is True
    assert result["counts"].get("ea-source") == 1


def test_discover_scan_rejects_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    srv = _load_server()
    result = _call(srv, "discover.scan", {"root": str(missing)})
    assert result["ok"] is False
    assert "does not exist" in result["error"]


def test_discover_scan_accepts_single_mq5_file_as_root(tmp_path: Path) -> None:
    """PR-21 regression: agents that pass a single downloaded ``.mq5``
    file as ``root`` (e.g. ``Thanos EA Source Code.mq5``) used to be
    rejected with ``"root is not a directory"``. The bridge now mirrors
    ``mql5-scan`` CLI and produces a 1-entry inventory with ``root``
    normalised to the parent directory so the chain pattern
    ``Path(root) / files[i].path`` works in both single-file and
    directory mode.
    """
    src = tmp_path / "Thanos EA Source Code.mq5"
    src.write_text("// single-file EA\nvoid OnTick(){}\n", encoding="utf-8")
    srv = _load_server()
    result = _call(srv, "discover.scan", {"root": str(src)})
    assert result["ok"] is True
    assert result["counts"].get("ea-source") == 1
    assert len(result["files"]) == 1
    entry = result["files"][0]
    assert entry["path"] == "Thanos EA Source Code.mq5"
    assert entry["kind"] == "ea-source"
    # Chain pattern: <root> / <path> resolves back to the original file.
    assert Path(result["root"]) / entry["path"] == src.resolve()


def test_discover_llm_context_wires_cloud_api(tmp_path: Path) -> None:
    mq5 = tmp_path / "TrendEA.mq5"
    mq5.write_text(
        "//+------------------------------------------------------------------+\n"
        "//| TrendEA.mq5                                                      |\n"
        "//+------------------------------------------------------------------+\n"
        "void OnInit() { }\n"
        "void OnTick() { }\n",
        encoding="utf-8",
    )
    srv = _load_server()
    result = _call(srv, "discover.llm_context", {
        "mq5_path": str(mq5),
        "pattern": "cloud-api",
    })
    assert result["ok"] is True
    assert result["pattern"] == "cloud-api"
    # The wirer reports what it changed; at least one of include/global/init
    # should be added on a virgin EA file.
    assert (
        result["added_include"]
        or result["added_global"]
        or result["added_init"]
    )
    # File on disk should reflect the wirings.
    after = mq5.read_text(encoding="utf-8")
    assert "cloud-api" in after.lower() or "#include" in after


def test_discover_llm_context_rejects_unknown_pattern(tmp_path: Path) -> None:
    mq5 = tmp_path / "ea.mq5"
    mq5.write_text("void OnTick(){}\n", encoding="utf-8")
    srv = _load_server()
    result = _call(srv, "discover.llm_context", {
        "mq5_path": str(mq5),
        "pattern": "totally-fake",
    })
    assert result["ok"] is False
    assert "unknown pattern" in result["error"]


def test_discover_llm_context_rejects_missing_file(tmp_path: Path) -> None:
    srv = _load_server()
    result = _call(srv, "discover.llm_context", {
        "mq5_path": str(tmp_path / "nope.mq5"),
        "pattern": "cloud-api",
    })
    assert result["ok"] is False
    assert "does not exist" in result["error"]


_AUTOFIX_SRC = (
    "//+------------------------------------------------------------------+\n"
    "//| demo.mq5                                                         |\n"
    "//| digits-tested: 5                                                 |\n"
    "//+------------------------------------------------------------------+\n"
    "#include <Trade/Trade.mqh>\n"
    "CTrade trade;\n"
    "CPipNormalizer pip;\n"
    "void OnTick() {\n"
    "    double sl = 30 * 0.0001;\n"
    "    trade.Buy(0.10);\n"
    "}\n"
)


def test_verify_auto_fix_in_memory_source_does_not_write_file() -> None:
    srv = _load_server()
    result = _call(srv, "verify.auto_fix", {
        "source": _AUTOFIX_SRC,
        "label": "demo.mq5",
    })
    assert result["ok"] is True
    assert result["wrote_changes"] is False
    assert result["path"] == "demo.mq5"
    assert isinstance(result["mutations"], list)
    assert isinstance(result["annotations"], list)
    assert isinstance(result["findings_before"], list)
    assert isinstance(result["findings_after"], list)
    assert "fixed_text" in result


def test_verify_auto_fix_rewrites_file_on_disk(tmp_path: Path) -> None:
    mq5 = tmp_path / "demo.mq5"
    mq5.write_text(_AUTOFIX_SRC, encoding="utf-8")
    srv = _load_server()
    result = _call(srv, "verify.auto_fix", {"path": str(mq5)})
    assert result["ok"] is True
    # AP-20 should rewrite hardcoded 0.0001 pip math to pip.Pip().
    fixed = mq5.read_text(encoding="utf-8")
    if result["wrote_changes"]:
        assert "0.0001" not in fixed or "pip.Pip()" in fixed
    # At minimum, the path is echoed back as the resolved abs path.
    assert result["path"].endswith("demo.mq5")


def test_verify_auto_fix_requires_path_or_source() -> None:
    srv = _load_server()
    result = _call(srv, "verify.auto_fix", {})
    assert result["ok"] is False
    assert "path" in result["error"] and "source" in result["error"]


def test_verify_auto_fix_rejects_missing_path(tmp_path: Path) -> None:
    srv = _load_server()
    result = _call(srv, "verify.auto_fix", {
        "path": str(tmp_path / "absent.mq5"),
    })
    assert result["ok"] is False
    assert "does not exist" in result["error"]


def test_pr7_chain_scan_into_auto_fix(tmp_path: Path) -> None:
    """End-to-end PR-7 pattern: discover.scan -> verify.auto_fix.

    An agent walks a workspace with discover.scan, picks an ea-source
    file (paths are scan-root relative — kit contract), and feeds the
    fully-qualified path back into verify.auto_fix.
    """
    target = tmp_path / "TrendEA.mq5"
    target.write_text(_AUTOFIX_SRC, encoding="utf-8")
    srv = _load_server()
    inv = _call(srv, "discover.scan", {"root": str(tmp_path)})
    assert inv["ok"] is True
    ea_sources = [f for f in inv["files"] if f["kind"] == "ea-source"]
    assert len(ea_sources) == 1
    chosen = Path(inv["root"]) / ea_sources[0]["path"]
    fix = _call(srv, "verify.auto_fix", {"path": str(chosen)})
    assert fix["ok"] is True
    assert fix["path"].endswith("TrendEA.mq5")


def test_verify_auto_fix_handles_non_utf8_bytes(tmp_path: Path) -> None:
    """MQL5 sources from MetaEditor on Windows often carry Windows-1252
    bytes (©, ®, em-dash, accented identifiers). The kit's own
    ``auto_fix.fix_file`` reads them with ``errors='replace'``; the
    bridge tool must mirror that so an unhandled ``UnicodeDecodeError``
    never reaches the JSON-RPC envelope.
    """
    mq5 = tmp_path / "WinEdited.mq5"
    # Mix a Windows-1252 copyright sign (0xA9) and an em-dash (0x97)
    # into an otherwise-valid EA — neither byte is legal UTF-8.
    mq5.write_bytes(
        b"//+------------------------------------------------------------------+\n"
        b"//| Copyright \xa9 2025 Broker \x97 example.com                    |\n"
        b"//+------------------------------------------------------------------+\n"
        b"#include <Trade/Trade.mqh>\n"
        b"CPipNormalizer pip;\n"
        b"void OnTick() { double sl = 30 * 0.0001; }\n"
    )
    srv = _load_server()
    result = _call(srv, "verify.auto_fix", {"path": str(mq5)})
    # Must not crash and must still round-trip the standard shape.
    assert result["ok"] is True, result
    assert result["path"].endswith("WinEdited.mq5")
    assert isinstance(result["mutations"], list)
    assert isinstance(result["findings_before"], list)
    assert isinstance(result["findings_after"], list)


# ─────────────────────────────────────────────────────────────────────────────
# PR-13 (gap G2) — JSON-RPC strict validation of inputSchema.required
# ─────────────────────────────────────────────────────────────────────────────
#
# The smoke-test report flagged that the bridge previously let tool calls
# through with missing required keys, leaving each handler to fail
# gracefully on its own. PR-13 moves that validation into the JSON-RPC
# dispatcher so the surface is consistent across all 29 tools and the
# error envelope matches the MCP / JSON-RPC 2.0 spec (-32602 Invalid
# params). The tests below pin that contract.


def test_pr13_required_lookup_built_from_tool_schemas() -> None:
    """The lookup must cover every tool that declares ``required`` keys."""
    srv = _load_server()
    lookup = srv._REQUIRED_BY_TOOL
    # Spot-check a handful from each PR.
    assert lookup["spec.from_prompt"] == ["prompt"]
    assert lookup["spec.validate"] == ["spec"]
    assert set(lookup["build.auto"]) == {"spec", "out_dir"}
    assert lookup["discover.llm_context"] == ["mq5_path", "pattern"]
    assert lookup["verify.backtest"] == ["xml_report_path"]
    # Tools that have no required keys are still in the lookup with [].
    assert lookup["discover.doctor"] == []


def test_pr13_llm_context_missing_pattern_returns_minus_32602() -> None:
    """The exact gap G2 from the smoke-test report.

    Before PR-13: arguments={'mq5_path': '/tmp/x.mq5'} would hit
    ``_tool_discover_llm_context`` with ``pattern=None`` → returned a
    tool-local ``{ok: false, error: 'unknown pattern None'}`` envelope.
    After PR-13: the server rejects the call before dispatch with a
    proper JSON-RPC -32602 error.
    """
    srv = _load_server()
    err = _call_for_error(
        srv, "discover.llm_context", {"mq5_path": "/tmp/whatever.mq5"},
    )
    assert err["code"] == -32602
    assert "pattern" in err["message"]
    assert "discover.llm_context" in err["message"]


def test_pr13_llm_context_missing_mq5_path_returns_minus_32602() -> None:
    srv = _load_server()
    err = _call_for_error(
        srv, "discover.llm_context", {"pattern": "cloud-api"},
    )
    assert err["code"] == -32602
    assert "mq5_path" in err["message"]


def test_pr13_llm_context_missing_both_lists_both() -> None:
    srv = _load_server()
    err = _call_for_error(srv, "discover.llm_context", {})
    assert err["code"] == -32602
    # Order matches the schema's ``required`` list.
    assert "mq5_path" in err["message"]
    assert "pattern" in err["message"]


def test_pr13_explicit_null_value_treated_as_missing() -> None:
    """JSON ``null`` for a required key counts as missing.

    JSON-RPC callers often send explicit ``null`` to indicate "no value"
    — the dispatcher must catch this so the tool body never sees ``None``
    for a declared-required field.
    """
    srv = _load_server()
    err = _call_for_error(
        srv, "spec.from_prompt", {"prompt": None},
    )
    assert err["code"] == -32602
    assert "prompt" in err["message"]


def test_pr13_empty_string_is_valid_for_required_field() -> None:
    """Empty strings / zeros / empty lists are intentional values, not missing.

    Only ``None`` / absent keys are treated as missing — empty values
    are legitimate inputs some tools genuinely accept.
    """
    srv = _load_server()
    # spec.from_prompt with prompt="" should still dispatch through;
    # the parser handles blank prompts deterministically.
    payload = _call(srv, "spec.from_prompt", {"prompt": ""})
    # The parser opts into all-defaults for a blank prompt.
    assert payload["ok"] is True
    assert payload["spec"]["preset"] == "stdlib"


def test_pr13_optional_keys_remain_optional() -> None:
    """Required-key enforcement must not break optional arguments.

    ``discover.scan`` declares no required keys at all, so calls with
    zero arguments must continue to dispatch successfully (subject to
    whatever the underlying tool does on disk).
    """
    srv = _load_server()
    # Just need to confirm the dispatcher doesn't bail with -32602.
    # The tool itself may still error on a missing workspace; we only
    # care that the bridge layer accepted the call.
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "discover.scan", "arguments": {}},
    })
    # Either a result (happy path) or a non--32602 tool error envelope.
    if "error" in resp:
        assert resp["error"]["code"] != -32602
    else:
        assert "result" in resp


def test_pr13_unknown_tool_still_returns_minus_32601() -> None:
    """The required-key check must not shadow the unknown-tool path."""
    srv = _load_server()
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "made.up.tool", "arguments": {}},
    })
    assert resp["error"]["code"] == -32601
    assert "made.up.tool" in resp["error"]["message"]


# ─────────────────────────────────────────────────────────────────────────────
# PR-19 — docs.ea_render: MCP exposure of the EA docs renderer
# ─────────────────────────────────────────────────────────────────────────────


_MIN_DOCS_SPEC = {
    "name": "MinDocsEA",
    "preset": "trend",
    "stack": "netting",
    "symbol": "EURUSD",
    "timeframe": "H1",
}


_MQ5_FIXTURE = """\
//+------------------------------------------------------------------+
//|                                                       MinDocsEA  |
//+------------------------------------------------------------------+
#property strict
input int    InpMagic    = 12345;       // Magic number
input double InpRiskPct  = 0.5;         // Risk percent per trade
input int    InpSlPips   = 25;          // Stop loss (pips)

void OnTick() {}
"""


def test_tools_list_includes_docs_ea_render() -> None:
    """``tools/list`` must surface the PR-19 docs tool as #30."""
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in resp["result"]["tools"]]
    assert "docs.ea_render" in names
    # Tool count must have grown by exactly one (PR-19 invariant).
    assert len(names) == 30, f"expected 30 tools after PR-19, got {len(names)}: {names}"


def test_docs_ea_render_schema_advertises_required_inputs() -> None:
    """Required keys: spec + out_dir. lang defaults to vi; mq5_source/mq5_path optional."""
    srv = _load_server()
    resp = srv.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    tool = next(t for t in resp["result"]["tools"] if t["name"] == "docs.ea_render")
    schema = tool["inputSchema"]
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"spec", "out_dir"}
    assert schema["properties"]["lang"]["default"] == "vi"
    assert schema["properties"]["lang"]["enum"] == ["vi", "en"]
    assert "html" in schema["properties"]["formats"]["items"]["enum"]
    assert "md" in schema["properties"]["formats"]["items"]["enum"]
    assert "pdf" in schema["properties"]["formats"]["items"]["enum"]


def test_docs_ea_render_writes_vietnamese_md_and_html_by_default(tmp_path: Path) -> None:
    """Default render produces .docs.md + .docs.html in Vietnamese."""
    srv = _load_server()
    # Use a richer spec (prop_firm block) so the notes section is populated
    # and the ``Lưu ý quan trọng`` header gets emitted alongside the other
    # three that always appear from a fixture EA's overview/strategy/inputs.
    spec = dict(_MIN_DOCS_SPEC)
    spec["prop_firm"] = {
        "daily_dd_pct": 5.0,
        "max_dd_pct": 10.0,
        "profit_target_pct": 8.0,
    }
    payload = _call(srv, "docs.ea_render", {
        "spec": spec,
        "mq5_source": _MQ5_FIXTURE,
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is True
    assert payload["lang"] == "vi"
    md_path = Path(payload["outputs"]["md"])
    html_path = Path(payload["outputs"]["html"])
    assert md_path.exists() and md_path.name == "MinDocsEA.docs.md"
    assert html_path.exists() and html_path.name == "MinDocsEA.docs.html"
    # Vietnamese default headers must be present in BOTH files.
    md_text = md_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")
    for header in (
        "Kiến trúc hệ thống",
        "Chu trình chiến lược",
        "Tham số EA",
        "Lưu ý quan trọng",
    ):
        assert header in md_text, header
        assert header in html_text, header
    # Project-default identifiers MUST survive verbatim — code names are
    # not translated regardless of lang.
    assert "InpRiskPct" in md_text


def test_docs_ea_render_lang_en_opts_back_to_english(tmp_path: Path) -> None:
    payload = _call(_load_server(), "docs.ea_render", {
        "spec": _MIN_DOCS_SPEC,
        "mq5_source": _MQ5_FIXTURE,
        "out_dir": str(tmp_path),
        "lang": "en",
    })
    assert payload["ok"] is True
    assert payload["lang"] == "en"
    md_text = Path(payload["outputs"]["md"]).read_text(encoding="utf-8")
    assert "## EA Inputs" in md_text
    assert "## System Architecture" in md_text
    # Vietnamese must NOT leak into the English variant.
    assert "Tham số EA" not in md_text


def test_docs_ea_render_accepts_mq5_path(tmp_path: Path) -> None:
    """When mq5_source is absent, mq5_path on disk must be read."""
    mq5 = tmp_path / "src.mq5"
    mq5.write_text(_MQ5_FIXTURE, encoding="utf-8")
    payload = _call(_load_server(), "docs.ea_render", {
        "spec": _MIN_DOCS_SPEC,
        "mq5_path": str(mq5),
        "out_dir": str(tmp_path / "out"),
        "formats": ["md"],
    })
    assert payload["ok"] is True
    assert "md" in payload["outputs"]
    # Only md format was requested.
    assert "html" not in payload["outputs"]


def test_docs_ea_render_rejects_missing_mq5_source_and_path(tmp_path: Path) -> None:
    """Calling without either mq5_source or mq5_path returns ok=false."""
    payload = _call(_load_server(), "docs.ea_render", {
        "spec": _MIN_DOCS_SPEC,
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is False
    assert "mq5_source" in payload["error"]
    assert "mq5_path" in payload["error"]


def test_docs_ea_render_rejects_unreadable_mq5_path(tmp_path: Path) -> None:
    payload = _call(_load_server(), "docs.ea_render", {
        "spec": _MIN_DOCS_SPEC,
        "mq5_path": str(tmp_path / "does-not-exist.mq5"),
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is False
    assert "failed to read mq5_path" in payload["error"]


def test_docs_ea_render_invalid_spec_returns_validate_stage(tmp_path: Path) -> None:
    payload = _call(_load_server(), "docs.ea_render", {
        "spec": {"name": "Broken"},  # missing required fields
        "mq5_source": _MQ5_FIXTURE,
        "out_dir": str(tmp_path),
    })
    assert payload["ok"] is False
    assert payload["stage"] == "validate"
    assert any("missing required fields" in e for e in payload["errors"])


def test_docs_ea_render_missing_required_fields_returns_minus_32602(tmp_path: Path) -> None:
    """JSON-RPC strict validation (PR-13) covers docs.ea_render too."""
    err = _call_for_error(_load_server(), "docs.ea_render", {
        # spec omitted — required by schema
        "out_dir": str(tmp_path),
    })
    assert err["code"] == -32602
    assert "spec" in err["message"]
