# vibecodekit-bridge

JSON-RPC 2.0 over stdio. Exposes the kit's high-level prompt → spec →
build → permission-gate loop to any MCP-aware AI coding agent
(Codex CLI, Claude Code, Cursor, Devin, Claude Desktop, …).

This is the 4th MCP server in the kit, joining `metaeditor-bridge`,
`mt5-bridge`, and `algo-forge-bridge`. Same wire format — same
`initialize` / `tools/list` / `tools/call` envelope.

## Tool set (18)

### PR-1: prompt → spec → build → permission-gate (4 tools)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `spec.from_prompt`  | `vibecodekit_mql5.spec_from_prompt.parse` | Free-text → validated `ea-spec.yaml`. |
| `spec.validate`     | `vibecodekit_mql5.spec_schema.validate`   | Schema-check a spec dict; collects every error. |
| `build.auto`        | `vibecodekit_mql5.auto_build.run_pipeline` | scan → render → lint → compile → permission gate → dashboard. |
| `verify.permission` | `vibecodekit_mql5.permission.orchestrator.run` | 7-layer fail-fast gate (modes: personal/team/enterprise). |

### PR-2: verify suite + spec schema extension (7 tools)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `verify.lint`               | `vibecodekit_mql5.lint.lint_file`                    | 8 critical-tier AP detectors (AP-1/3/5/15/17/18/20/21). |
| `verify.lint_best_practice` | `vibecodekit_mql5.lint_best_practice.BEST_PRACTICE_DETECTORS` | 14 WARN-tier AP detectors (AP-2/4/6/7/8/9/10/11/12/13/14/16/19/22). |
| `verify.method_hiding`      | `vibecodekit_mql5.method_hiding_check.check_method_hiding` | CExpert-subclass-without-`using` (ERROR ≥ build 5260). |
| `verify.trader17`           | `vibecodekit_mql5.trader_check.evaluate` + `verdict` | 17-point reliability checklist; verdict by mode. |
| `verify.compile`            | `vibecodekit_mql5.compile.compile_mq5`               | MetaEditor compile (Wine on Linux) — convenience over `metaeditor.compile`. |
| `verify.broker_safety`      | `vibecodekit_mql5.broker_safety.evaluate`            | fill-policy / lot-step / min-lot / magic-range against a symbol-info JSON. |
| `verify.audit`              | `vibecodekit_mql5.audit.run_audit`                   | Kit conformance battery (~70 probes). |

### PR-3: runtime / statistical verify suite (7 tools)

| Tool | Wraps | One-line purpose |
|------|-------|------------------|
| `verify.backtest`     | `vibecodekit_mql5.backtest.parse_xml_report_file`   | Parse an MT5 tester XML report into a structured dict. |
| `verify.walkforward`  | `vibecodekit_mql5.walkforward.evaluate`             | OOS/IS Sharpe correlation + PASS/WARN/FAIL verdict (thresholds 0.5/0.3). |
| `verify.montecarlo`   | `vibecodekit_mql5.monte_carlo.evaluate`             | Bootstrap DD p50/p75/p95 + PASS/FAIL verdict (p95 ≤ 1.5× reported_dd). |
| `verify.multibroker`  | `vibecodekit_mql5.multibroker.evaluate`             | PF CV / Sharpe stdev / DD diff across N broker reports. |
| `verify.fitness`      | `vibecodekit_mql5.fitness.get` / `list_templates`   | Look up an `OnTester()` template (sharpe/sortino/profit-dd/expectancy/walkforward). |
| `verify.mfe_mae`      | `vibecodekit_mql5.mfe_mae.parse_csv` + `compute_stats` | Trade CSV → mean MFE/MAE + Pearson corr with profit. |
| `verify.overfit`      | `vibecodekit_mql5.overfit_check.evaluate`           | Standalone IS/OOS Sharpe ratio verdict (no XML needed). |

### `ea-spec.yaml` schema additions (PR-2)

Three optional, back-compat blocks were added so AI agents can talk
about prop-firm constraints, time-based exits, and broker-stealth
toggles without round-tripping through free-text comments:

| Block | What it captures |
|-------|------------------|
| `prop_firm` | `daily_dd_pct`, `max_dd_pct`, `profit_target_pct`, `news_block_min`, `weekend_flat`, `copy_trading_lock`. |
| `time_exit` | `close_on_friday`, `friday_close_hour`, `max_trade_hours`, `session_start_hour`, `session_end_hour`. |
| `stealth`   | `randomize_slippage_pips`, `randomize_comment_pool`, `randomize_lot_jitter_pct`, `split_orders`, `avoid_round_numbers`. |

Specs that don't supply these blocks validate unchanged — the kit's
existing scaffolds continue to render exactly as before. Templates
that *do* want to consume these blocks can read them from the
normalised `EaSpec` dataclass.

Future PRs will extend `DISPATCH` with the remaining review / ship
tools (`review.eng`, `review.cso`, `review.ceo`, `review.investigate`,
`rri.persona`, `dashboard.publish`, `forge.pr.create`, …). The wire
format does not change.

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
