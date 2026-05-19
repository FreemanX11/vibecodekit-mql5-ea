"""Phase E unit tests — MCP server invariants."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _load(dir_name: str):
    path = REPO_ROOT / "mcp" / dir_name / "server.py"
    spec = importlib.util.spec_from_file_location(f"{dir_name}_server", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_metaeditor_bridge_tools_list_shape() -> None:
    srv = _load("metaeditor-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 10, "method": "tools/list"})
    tools = resp["result"]["tools"]
    assert len(tools) == 3
    for tool in tools:
        assert "name" in tool and "description" in tool and "inputSchema" in tool


def test_mt5_bridge_tools_list_shape() -> None:
    srv = _load("mt5-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 11, "method": "tools/list"})
    assert len(resp["result"]["tools"]) == 10


def test_algo_forge_bridge_tools_list_shape() -> None:
    srv = _load("algo-forge-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 12, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"forge.init", "forge.pr.create", "forge.repo.list"} <= names


def test_vibecodekit_bridge_tools_list_shape() -> None:
    srv = _load("vibecodekit-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 17, "method": "tools/list"})
    names = {t["name"] for t in resp["result"]["tools"]}
    assert {"spec.from_prompt", "spec.validate",
            "build.auto", "verify.permission"} <= names


def test_unknown_method_returns_error() -> None:
    srv = _load("metaeditor-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "id": 13, "method": "no/such/method"})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_unknown_tool_returns_error() -> None:
    srv = _load("mt5-bridge")
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 14, "method": "tools/call",
        "params": {"name": "mt5.no_such_tool", "arguments": {}},
    })
    assert "error" in resp


def test_notification_returns_none() -> None:
    srv = _load("metaeditor-bridge")
    resp = srv.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp is None


def test_mt5_bridge_account_info_stub() -> None:
    srv = _load("mt5-bridge")
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 15, "method": "tools/call",
        "params": {"name": "mt5.account.info", "arguments": {}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    # Stub values, but the schema must include the canonical keys.
    for key in ("login", "balance", "equity", "leverage", "currency"):
        assert key in payload


def test_algo_forge_clone_returns_dest() -> None:
    srv = _load("algo-forge-bridge")
    resp = srv.handle({
        "jsonrpc": "2.0", "id": 16, "method": "tools/call",
        "params": {"name": "forge.clone",
                   "arguments": {"repo_url": "https://forge.mql5.io/x.git",
                                 "dest": "/tmp/x"}},
    })
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["cloned"] is True
