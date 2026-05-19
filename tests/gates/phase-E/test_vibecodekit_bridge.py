"""Phase E unit tests — vibecodekit-bridge MCP server.

Mirrors ``test_mcp_servers.py``. The bridge ships four tools in PR-1
(``spec.from_prompt``, ``spec.validate``, ``build.auto``,
``verify.permission``); these tests cover the JSON-RPC envelope, the
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
