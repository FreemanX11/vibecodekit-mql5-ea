"""Phase E unit tests — vibecodekit-bridge MCP server.

Mirrors ``test_mcp_servers.py``. The bridge ships 4 PR-1 tools
(``spec.from_prompt``, ``spec.validate``, ``build.auto``,
``verify.permission``) plus 7 PR-2 verify tools (``verify.lint``,
``verify.lint_best_practice``, ``verify.method_hiding``,
``verify.trader17``, ``verify.compile``, ``verify.broker_safety``,
``verify.audit``); these tests cover the JSON-RPC envelope, the
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
        # All 14 AP codes from the WARN tier must appear as keys.
        for code in ("AP-2", "AP-4", "AP-6", "AP-7", "AP-8", "AP-9", "AP-10",
                     "AP-11", "AP-12", "AP-13", "AP-14", "AP-16", "AP-19",
                     "AP-22"):
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
