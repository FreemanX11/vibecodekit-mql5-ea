---
id: usage-en
title: vibecodekit-mql5-ea v1.0.1 Usage Guide (English)
applicable_phase: E
audience: end_user, dev_team
---

# `vibecodekit-mql5-ea` v1.0.1 Usage Guide

End-to-end walkthrough of all 50 commands, from idea to live shipping.
Suitable for both new users and dev teams.

> 📚 Vietnamese version: [USAGE-vi.md](USAGE-vi.md)
> 🛠️ Per-IDE / CLI integration: [ENV-SETUP-vi.md](ENV-SETUP-vi.md)
> 💬 Chat-driven build (prompt → spec → pipeline): [devin-chat-driven-build.md](devin-chat-driven-build.md)

## Contents

1. [Environment setup](#1-environment-setup)
2. [The 8-step build philosophy](#2-the-8-step-build-philosophy)
3. [Commands by stage](#3-commands-by-stage)
4. [End-to-end example: MACD+SAR EURUSD H1](#4-end-to-end-example)
5. [Integrating the 4 MCP servers](#5-integrating-the-4-mcp-servers)
6. [23 anti-pattern detectors](#6-23-anti-pattern-detectors)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Environment setup

### 1.1. Requirements

| Component | Version |
|-----------|---------|
| Python | ≥ 3.10 |
| Wine | 8.0.2 (Linux/macOS) — MetaEditor is native on Windows |
| MetaEditor | build ≥ 5260 (so method-hiding lint stays at ERROR) |
| ONNX runtime | 1.14 (Phase D ONNX e2e) |
| Xvfb | optional — needed only on headless Linux CI |

### 1.2. Linux (Ubuntu 22.04+)

```bash
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea

./scripts/setup-wine-metaeditor.sh        # ~3 min
python -m venv .venv && source .venv/bin/activate
pip install -e .

python -m vibecodekit_mql5.doctor         # every probe must show ok: true
```

### 1.3. macOS

Wine on macOS runs but is not officially supported by MetaQuotes.
Recommend a Devin VM or Linux VM. If you must run locally:

```bash
brew install --cask wine-stable
# Then same as Linux
```

### 1.4. Windows

MetaEditor is native, no Wine needed. PowerShell:

```powershell
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m vibecodekit_mql5.doctor
```

> ⚠️ `setup-wine-metaeditor.sh` is bash-only — on Windows simply set
> `METAEDITOR_BIN` env var to your `metaeditor64.exe` path and skip
> the Wine step.

---

## 2. The 8-step build philosophy

Plan v5 splits the entire EA lifecycle into 8 steps. Each step has a
markdown template in `docs/rri-templates/` and a dedicated command:

| Step | Name | Open template | Output |
|------|------|---------------|--------|
| 1 | **SCAN** | `python -m vibecodekit_mql5.scan <dir>` | Project tree |
| 2 | **RRI** (Research / Risk / Robustness) | `python -m vibecodekit_mql5.rri --mode {personal,team,enterprise}` | `docs/rri-report.md` |
| 3 | **VISION** | `python -m vibecodekit_mql5.vision` | `docs/vision.md` |
| 4 | **BLUEPRINT** | `python -m vibecodekit_mql5.blueprint` | `docs/blueprint.md` |
| 5 | **TIP** (8 Technical Implementation Points) | `python -m vibecodekit_mql5.tip` | `docs/tip.md` |
| 6 | **BUILD** | `python -m vibecodekit_mql5.build <archetype>` or `wizard`, `async-build` | `.mq5` from scaffold |
| 7 | **VERIFY** | 10 commands from `compile` → `multibroker` | XML report + 64-cell matrix |
| 8 | **REFINE + SHIP** | `python -m vibecodekit_mql5.refine` + `ship` | Git tag + push |

### Mode breakdown

| Mode | RRI questions | Permission layers | Audience |
|------|---------------|-------------------|----------|
| `personal` | 5 q/persona × 6 = 30 | 1, 2, 3, 4, 7 | Solo trader |
| `team` | 12 q/persona × 6 = 72 | 1-5, 7 | 2–5-dev team |
| `enterprise` | 25 q/persona × 6 = 150 | 1-7 (full) | Org / fund |

---

## 3. Commands by stage

### 3.1. Discovery (4)

```bash
python -m vibecodekit_mql5.scan ~/projects/eurusd-portfolio
python -m vibecodekit_mql5.survey "MA cross strategy H1 trend following"
python -m vibecodekit_mql5.doctor
python -m vibecodekit_mql5.audit
```

### 3.2. Plan — template openers (4)

```bash
python -m vibecodekit_mql5.rri --mode team
python -m vibecodekit_mql5.vision
python -m vibecodekit_mql5.blueprint
python -m vibecodekit_mql5.tip
```

### 3.3. Build (12)

```bash
# Scaffolds + patchers
python -m vibecodekit_mql5.build stdlib --name MyEA --symbol EURUSD --tf H1
python -m vibecodekit_mql5.wizard --name MyWizardEA --symbol EURUSD --tf H1
python -m vibecodekit_mql5.async_build --name MyHftEA --symbol EURUSD --tf M1
python -m vibecodekit_mql5.pip_normalize MyEA.mq5
python -m vibecodekit_mql5.onnx_export model.pt --output model.onnx --opset 14
python -m vibecodekit_mql5.onnx_embed MyEA.mq5 --model model.onnx
python -m vibecodekit_mql5.llm_context MyEA.mq5 --pattern cloud-api
python -m vibecodekit_mql5.forge_init MyEA
```

Available archetypes for `build`: `stdlib`, `trend`, `mean-reversion`,
`breakout`, `scalping`, `hedging-multi`, `news-trading`,
`arbitrage-stat`, `library`, `indicator-only`, `grid`, `dca`,
`portfolio-basket`, `wizard-composable`, `hft-async`, `ml-onnx`,
`service-llm-bridge`.

LLM patterns: `cloud-api` | `self-hosted-ollama` | `embedded-onnx-llm`.

#### 3.3a. One-shot auto-build pipeline

The four CLIs below close the gap between "I want an EA that does X"
and a green-CI pull request. Each command is deterministic, regex-only
(no LLM call), and produces a structured JSON or YAML artifact you can
feed into the next stage.

```bash
# Free-text → schema-valid ea-spec.yaml (use --explain to see what
# was inferred vs defaulted; --strict to fail if any required field
# isn't recognisable in the prompt).
mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5% macd or sar" \
    --out ea-spec.yaml --explain

# Single-shot pipeline: scan → build → lint → compile → permission-gate
# → dashboard. Writes auto-build-report.json (idempotent).
mql5-auto-build --spec ea-spec.yaml --out-dir build/MyEA

# Apply the 8-AP transformer loop to an existing .mq5 (AP-1, 3, 5, 15,
# 17, 18, 20, 21). Re-runs the lint after each pass.
mql5-auto-fix MyEA.mq5

# Render + (optionally) publish the 64-cell RRI quality matrix HTML.
# Reads MQL5_DASHBOARD_PUBLISH_CMD or --publish-cmd; falls back to
# file:// if no hook is configured.
mql5-dashboard --metrics metrics.json --out quality-matrix.html
```

Flags worth knowing:

* `mql5-auto-build --no-compile` skips the Wine + MetaEditor stage (useful
  on a Windows-less CI runner or when the focus is lint/gate alone).
* `mql5-auto-build --no-gate` skips the 7-layer permission orchestrator.
* `mql5-auto-build --force` re-renders the scaffold even when the
  `out_dir` is non-empty.
* `mql5-auto-build --publish-cmd <cmd>` overrides the dashboard
  publish hook for that one run.

Schema reference for `ea-spec.yaml` (risk / signals / filters / hooks /
stack overrides) lives at `scripts/vibecodekit_mql5/spec_schema.py`;
recognisers for `mql5-spec-from-prompt` are tabulated in
[`devin-chat-driven-build.md`](devin-chat-driven-build.md#what-the-parser-understands).

### 3.4. Verify (11)

```bash
# Code-quality (run anytime; no XML needed)
python -m vibecodekit_mql5.compile             MyEA.mq5
python -m vibecodekit_mql5.lint                MyEA.mq5
python -m vibecodekit_mql5.method_hiding_check MyEA.mq5 --build 5260

# Parse Strategy Tester XML report (run backtest manually first, then parse)
python -m vibecodekit_mql5.backtest MyEA.ex5 inputs.set \
    --period H1 --symbol EURUSD --report tester.xml > metrics.json

# End-to-end Strategy Tester run (drives terminal64.exe via Wine + parses XML)
# Requires $MQL5_TERMINAL_PATH (exported by scripts/setup-wine-metaeditor.sh).
python -m vibecodekit_mql5.tester_run MyEA.ex5 \
    --symbol EURUSD --period H1 --from 2024-01-01 --to 2024-06-01 \
    --out tester.xml > metrics.json

# Walk-forward / overfit / monte-carlo take POSITIONAL XML/CSV inputs
python -m vibecodekit_mql5.walkforward   is.xml oos.xml      > walkforward.json
python -m vibecodekit_mql5.overfit_check is.xml oos.xml      > overfit.json
python -m vibecodekit_mql5.monte_carlo   returns.csv --reported-dd 5.4 \
                                         --n-sims 1000 --seed 42 > montecarlo.json

# Multi-broker: comma-separated XML report paths
python -m vibecodekit_mql5.multibroker --reports a.xml,b.xml,c.xml

# Custom fitness template (positional; omit to list 5 templates)
python -m vibecodekit_mql5.fitness sharpe > OnTester.mq5

# MFE/MAE: CSV must have columns deal_id,open_time,close_time,magic,
# type,profit,mfe,mae (exact, as emitted by CMfeMaeLogger.SaveToCsv())
python -m vibecodekit_mql5.mfe_mae mfe.csv
```

> **Note:** `backtest`, `walkforward`, `overfit_check`, `multibroker` only
> **parse** XML reports — they do NOT drive the Strategy Tester. Run the
> backtest yourself via MetaTrader 5 (or automate it with
> `terminal64.exe /config:tester.ini`), capture the XML, then feed it in.
> `cloud_optimize` only emits the `tester.ini` you upload to MetaQuotes
> Cloud Network.

### 3.5. RRI methodology (3)

```bash
# BT review — 5 personas × 7 dims × 8 axes (needs metrics JSON from backtest)
python -m vibecodekit_mql5.rri.rri_bt \
    --metrics metrics.json --mode enterprise --output rri-bt.html

# R&R review — needs 4 JSON inputs
python -m vibecodekit_mql5.rri.rri_rr \
    --trader-check trader-check.json --walkforward walkforward.json \
    --monte-carlo  montecarlo.json   --overfit     overfit.json \
    --mode enterprise --output rri-rr.html

# Indicator-only review
python -m vibecodekit_mql5.rri.rri_chart \
    --metrics metrics.json --mode personal --output rri-chart.html
```

### 3.6. Review openers (5)

```bash
python -m vibecodekit_mql5.review.review
python -m vibecodekit_mql5.review.eng_review
python -m vibecodekit_mql5.review.ceo_review
python -m vibecodekit_mql5.review.cso
python -m vibecodekit_mql5.review.investigate
```

### 3.7. Deploy (3)

```bash
python -m vibecodekit_mql5.deploy_vps      MyEA --out MIGRATE-VPS.md --mode personal
python -m vibecodekit_mql5.cloud_optimize  MyEA --symbol EURUSD --period H1 \
                                           --passes 1000 --budget-usd 50 --mode enterprise
python -m vibecodekit_mql5.canary          MyEA.ex5 --duration 30m  # or --journal mt5.log
```

### 3.8. Ship (3)

```bash
python -m vibecodekit_mql5.forge_pr feature-branch --target main
python -m vibecodekit_mql5.ship --tag v1.0.1 --dry-run
python -m vibecodekit_mql5.ship --tag v1.0.1
python -m vibecodekit_mql5.refine --diff change.patch
```

### 3.9. Other (4)

```bash
python -m vibecodekit_mql5.broker_safety MyEA.mq5
python -m vibecodekit_mql5.trader_check  MyEA.mq5
python -m vibecodekit_mql5.install       ~/existing-mt5-project
python -m vibecodekit_mql5.second_opinion MyEA.mq5
```

---

## 4. End-to-end example

The full worked example lives at
`examples/ea-wizard-macd-sar-eurusd-h1-portfolio/`. It demonstrates a
**4-hour enterprise turnaround** on a Devin VM.

### Step 1 — SCAN (5 min)
```bash
python -m vibecodekit_mql5.scan ~/projects/eurusd-portfolio
```

### Step 2 — RRI (90 min, enterprise mode)
```bash
python -m vibecodekit_mql5.rri.step_workflow --mode enterprise
# 6 personas × 25 questions = 150 questions
# → docs/rri-report.md
```

### Step 3 — VISION (15 min)
Fill `docs/rri-templates/step-3-vision.md.tmpl`:
- Hypothesis: MACD signal cross gated by Parabolic-SAR flip
- Scope: EURUSD H1 netting account
- Out of scope: hedging, multi-symbol, news filter

### Step 4 — BLUEPRINT (30 min)
Pick:
- Archetype: `wizard-composable/netting`
- Includes: `CPipNormalizer`, `CRiskGuard`, `CMagicRegistry`, `CMfeMaeLogger`
- Magic: 5001

### Step 5 — TIP (8 TIPs, ~30 min)
8 Technical Implementation Points covering SL/TP, risk per trade,
filters, trailing, kill switch, slippage limit, news blackout, weekly
DD cap.

### Step 6 — BUILD (10 min)
```bash
python -m vibecodekit_mql5.wizard \
    --name EAMacdSarPortfolio \
    --symbol EURUSD --tf H1 \
    --output ~/projects/eurusd-portfolio
```

### Step 7 — VERIFY (multi-stage, ~60 min)
```bash
# Code-quality first (no XML required)
python -m vibecodekit_mql5.compile             EAMacdSarPortfolio.mq5
python -m vibecodekit_mql5.lint                EAMacdSarPortfolio.mq5
python -m vibecodekit_mql5.method_hiding_check EAMacdSarPortfolio.mq5

# Run Strategy Tester manually via MT5 GUI, capture XML reports, then:
python -m vibecodekit_mql5.backtest      EAMacdSarPortfolio.ex5 default.set \
    --period H1 --symbol EURUSD --report tester.xml > metrics.json
python -m vibecodekit_mql5.walkforward   is.xml oos.xml      > walkforward.json
python -m vibecodekit_mql5.monte_carlo   returns.csv --reported-dd 5.4 \
                                         --n-sims 1000        > montecarlo.json
python -m vibecodekit_mql5.overfit_check is.xml oos.xml      > overfit.json
python -m vibecodekit_mql5.multibroker   --reports a.xml,b.xml,c.xml
python -m vibecodekit_mql5.trader_check  EAMacdSarPortfolio.mq5 > trader-check.json

python -m vibecodekit_mql5.rri.rri_bt    --metrics metrics.json \
                                         --mode enterprise --output rri-bt.html
python -m vibecodekit_mql5.rri.rri_rr    --trader-check trader-check.json \
    --walkforward walkforward.json --monte-carlo montecarlo.json \
    --overfit overfit.json --mode enterprise --output rri-rr.html
```

### Step 8 — REFINE + SHIP (~10 min)
```bash
python -m vibecodekit_mql5.refine --diff change.patch
python -m vibecodekit_mql5.ship --tag v1.0.0 --dry-run
python -m vibecodekit_mql5.ship --tag v1.0.0
```

Resulting artefacts in `results/`:
`EAMacdSarPortfolio.ex5`, `.set` file, 64-cell matrix HTML, backtest
XML, MFE/MAE report, canary log.

---

## 5. Integrating the 4 MCP servers

All four speak JSON-RPC 2.0 over stdio per the MCP spec. Usable from
any MCP client (Claude Desktop, Claude Code, Cursor, Codex, Devin, ...).

### 5.1. metaeditor-bridge

3 tools: `metaeditor.compile`, `metaeditor.parse_log`,
`metaeditor.includes_resolve`.

```bash
python mcp/metaeditor-bridge/server.py
```

### 5.2. mt5-bridge (READ-ONLY)

10 **read-only** tools (NO `order_send`, `order_close`, or
`position_modify` — enforced by `test_mt5_bridge_readonly_no_trade`):

- `mt5.symbols.list`, `mt5.symbol.info`
- `mt5.rates.copy`, `mt5.tick.last`
- `mt5.account.info`, `mt5.terminal.info`
- `mt5.positions.list`, `mt5.positions.history`
- `mt5.history.deals`, `mt5.market.book`

```bash
python mcp/mt5-bridge/server.py
```

> ⚠️ **Platform note:** the `MetaTrader5` Python package only installs
> on **Windows** (or a Wine-hosted MT5 desktop via `winetricks`). On a
> plain Linux VM the import fails and every tool returns a
> deterministic **stub payload** (empty symbol list, zero bars,
> hardcoded `digits=5, point=0.00001` for `mt5.symbol.info`).  The
> stubs keep the MCP contract testable hermetically but they are
> **not live data**.  Run this server on Windows or under Wine MT5
> when you need real account / market data.

### 5.3. algo-forge-bridge

6 tools: `forge.init`, `forge.clone`, `forge.commit`, `forge.pr.create`,
`forge.pr.list`, `forge.repo.list`. Requires `ALGO_FORGE_API_KEY`.

```bash
ALGO_FORGE_API_KEY=xxx python mcp/algo-forge-bridge/server.py
```

### 5.4. vibecodekit-bridge

23 tools across four PRs. Lets an AI coding agent (Codex CLI / Claude
Code / Cursor / Devin / Claude Desktop) drive the full `prompt → spec
→ build → verify → permission-gate` loop via JSON-RPC. The wire format
is stable across PRs — future ones extend `DISPATCH` without breaking
clients.

**PR-1 (prompt → spec → build → permission-gate):**
`spec.from_prompt`, `spec.validate`, `build.auto`, `verify.permission`.

**PR-2 (static-analysis verify suite):** `verify.lint` (8 critical AP),
`verify.lint_best_practice` (14 WARN AP), `verify.method_hiding`,
`verify.trader17`, `verify.compile`, `verify.broker_safety`,
`verify.audit`.

**PR-3 (runtime / statistical verify suite):** `verify.backtest`
(MT5 tester XML report parser), `verify.walkforward` (OOS/IS Sharpe
correlation + verdict), `verify.montecarlo` (bootstrap DD stress
test), `verify.multibroker` (N-broker stability — PF CV / Sharpe
stdev / DD diff), `verify.fitness` (lookup tester `OnTester()`
template), `verify.mfe_mae` (excursion CSV stats), `verify.overfit`
(IS/OOS Sharpe ratio verdict — no XML required).

**PR-4 (review / RRI suite):** `review.eng` (broker-engineer + devops),
`review.cso` (risk-auditor), `review.ceo` (trader + strategy-architect),
`review.investigate` (perf-analyst + strategy-architect), plus the
generic `rri.persona` for ad-hoc 1-persona x 1-step x 1-mode drills.
Each tool returns markdown ready to drop into a PR description or a
`review.md` artefact.

**Spec schema additions (PR-2):** three optional, back-compat blocks
on `ea-spec.yaml` — `prop_firm` (FTMO/MFF DD limits + news block +
weekend-flat), `time_exit` (Friday close, max trade duration, session
windows), `stealth` (slippage / comment / lot-jitter randomisation,
split orders). Specs that don't supply them validate unchanged.

```bash
python mcp/vibecodekit-bridge/server.py
```

### 5.5. MCP client configuration

See [docs/ENV-SETUP-vi.md](ENV-SETUP-vi.md) for ready-to-paste configs
for Claude Desktop, Cursor, Codex, and Devin.

---

## 6. 23 anti-pattern detectors

Lint is split across two tiers:

### 6.1. Critical APs — ERROR, block ship (8)

| ID | Description | Detector |
|----|-------------|----------|
| AP-1 | `OrderSend` without SL | `lint.py` |
| AP-3 | Fixed lot size, not risk-based | `lint.py` |
| AP-5 | EA overfit (in-sample only) | `lint.py` |
| AP-15 | Raw `OrderSend` (no `CTrade`) | `lint.py` |
| AP-17 | `WebRequest` inside `OnTick` | `lint.py` |
| AP-18 | `OrderSendAsync` without `OnTradeTransaction` | `lint.py` |
| AP-20 | Hard-coded pip (`* 0.0001`, `* _Point`) | `lint.py` |
| AP-21 | JPY/XAU digits broken | `lint.py` |

### 6.2. Best-practice APs — WARN (14)

| ID | Description | Detector |
|----|-------------|----------|
| AP-2 | SL too tight | `lint_best_practice.py` |
| AP-4 | Martingale without cap | `lint_best_practice.py` |
| AP-6 | Curve-fitted optimisation | `lint_best_practice.py` |
| AP-7 | Hard-coded magic number | `lint_best_practice.py` |
| AP-8 | No spread guard | `lint_best_practice.py` |
| AP-9 | Multi-entry on same bar | `lint_best_practice.py` |
| AP-10 | `OrderSend` return not checked | `lint_best_practice.py` |
| AP-11 | EA mode-blind | `lint_best_practice.py` |
| AP-12 | Indicator handle leak | `lint_best_practice.py` |
| AP-13 | Broker-coupled EA | `lint_best_practice.py` |
| AP-14 | No MFE/MAE logging | `lint_best_practice.py` |
| AP-16 | Reinvent stdlib | `lint_best_practice.py` |
| AP-19 | ONNX without Strategy-Tester validation | `lint_best_practice.py` |
| AP-22 | `OnTick` reaches no order-placing call (placeholder signal) | `lint_best_practice.py` |

### 6.3. Method-hiding (1, build-aware)

MetaEditor build ≥ 5260 reports ERROR when a `CExpert` subclass has a
method with the same name as a base method without a
`using BaseClass::method;` directive. Build < 5260 only WARNs.

```bash
python -m vibecodekit_mql5.method_hiding_check MyEA.mq5 --build 5260
```

---

## 7. Troubleshooting

### "wine: command not found"
- Linux: `./scripts/setup-wine-metaeditor.sh` failed silently.
- macOS: `brew install --cask wine-stable`.
- Windows: set `METAEDITOR_BIN=C:\Path\To\metaeditor64.exe`.

### `doctor` reports "metaeditor-bin: not found"
```bash
export METAEDITOR_BIN=~/.wine/drive_c/Program\ Files/MetaTrader\ 5/metaeditor64.exe
```

### ONNX e2e test fails — torch not installed
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install onnx onnxscript
```

### `audit-plan-v5.py --post-phase=E` reports missing scaffold
- Check `git status` for untracked scaffold files.
- Verify `.gitignore` isn't excluding artefacts:
  ```bash
  git check-ignore -v examples/**/results/canary.log
  ```

### mt5-bridge "MetaTrader5 not installed"
```bash
pip install MetaTrader5  # Windows or Wine MT5 desktop only
```

### `forge_init` returns 401 Unauthorized
```bash
export ALGO_FORGE_API_KEY=your_key_here
```

### Linguist classifies the repo as MQL4 instead of MQL5
- Fixed in `.gitattributes` (PR #17). After commit, wait ~10 min for
  GitHub to re-run Linguist.

---

## Further resources

- [`docs/COMMANDS.md`](COMMANDS.md) — 43-command reference card
- [`docs/references/`](references/) — 28 technical cheatsheets (50-survey → 79-pip-norm)
- [`docs/PLAN-v5.md`](PLAN-v5.md) — Original 1089-line spec
- [`docs/anti-patterns-AVOID.md`](anti-patterns-AVOID.md) — VCK-HU anti-patterns to avoid
- [`docs/rri-personas/`](rri-personas/) — 6 YAML × 25 q each
- [`docs/rri-templates/`](rri-templates/) — 8 step-by-step markdown templates
- [`examples/ea-wizard-macd-sar-eurusd-h1-portfolio/`](../examples/ea-wizard-macd-sar-eurusd-h1-portfolio/) — 4-hour worked example

Questions / bugs → open an issue at
https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea/issues
