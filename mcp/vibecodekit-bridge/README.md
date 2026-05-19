# vibecodekit-bridge

JSON-RPC 2.0 over stdio. Exposes the kit's high-level prompt → spec →
build → permission-gate loop to any MCP-aware AI coding agent
(Codex CLI, Claude Code, Cursor, Devin, Claude Desktop, …).

This is the 4th MCP server in the kit, joining `metaeditor-bridge`,
`mt5-bridge`, and `algo-forge-bridge`. Same wire format — same
`initialize` / `tools/list` / `tools/call` envelope.

## PR-1 tool set (4)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `spec.from_prompt`  | `vibecodekit_mql5.spec_from_prompt.parse` | Free-text → validated `ea-spec.yaml`. |
| `spec.validate`     | `vibecodekit_mql5.spec_schema.validate`   | Schema-check a spec dict; collects every error. |
| `build.auto`        | `vibecodekit_mql5.auto_build.run_pipeline` | scan → render → lint → compile → permission gate → dashboard. |
| `verify.permission` | `vibecodekit_mql5.permission.orchestrator.run` | 7-layer fail-fast gate (modes: personal/team/enterprise). |

Future PRs will extend `DISPATCH` with the remaining verify / review /
backtest tools (`verify.lint`, `verify.trader17`, `verify.backtest`,
`verify.walkforward`, `verify.montecarlo`, `verify.multibroker`,
`review.eng`, `review.cso`, `review.ceo`, `review.investigate`,
`rri.persona`, `dashboard.publish`, …). The wire format does not change.

## Launch directly

```bash
python mcp/vibecodekit-bridge/server.py < requests.ndjson
```

Each line of stdin is one JSON-RPC request; each line of stdout is one
JSON-RPC response. Notifications (`notifications/*`) produce no output.

## Smoke test

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
  | python mcp/vibecodekit-bridge/server.py
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python mcp/vibecodekit-bridge/server.py
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"spec.from_prompt","arguments":{"prompt":"build EA trend EURUSD H1 risk 0.5%"}}}' \
  | python mcp/vibecodekit-bridge/server.py
```

## Tests

Hermetic pytest cases (no Wine / MetaTrader5 needed):

```bash
pytest tests/gates/phase-E/test_vibecodekit_bridge.py -v
```

## Client configuration

See [`docs/ENV-SETUP-vi.md`](../../docs/ENV-SETUP-vi.md) for ready-to-paste
configs for Codex CLI, Claude Code, Cursor, and Codex Desktop. The
1-line summary is the same as the other bridges: add a
`command: python` + `args: [.../mcp/vibecodekit-bridge/server.py]`
entry to the client's MCP config.
