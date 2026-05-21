# Vibecodekit-MQL5-EA — Plan v5 (FULL)

> **v5 = v4 lean structure + restored breadth (per user request).**
>
> **History:**
> - v1 (1209 dòng) — port VCK-HU 1-1 sang domain EA
> - v2 (860 dòng) — + Mashnin Advanced book (Wizard, MFE/MAE, multi-broker)
> - v3.1 (1345 dòng) — + ONNX/Forge/VPS/Cloud Network + CPipNormalizer
> - v4 (622 dòng) — strip 70% sau audit 5 anti-patterns
> - **v5 (this doc)** — restore breadth theo yêu cầu, vẫn drop 4 dead-code/router pieces
>
> **v5 ADD BACK vs v4:**
> - 3 MCP servers (metaeditor-bridge + mt5-bridge + algo-forge-bridge)
> - 16 scaffolds × 3 stack matrix = 48 trees
> - 26 references (50-67, 70-79)
> - 22 anti-patterns (8 critical + 13 best-practice + AP-22 method-hiding)
> - 17-point Trader checklist
> - 8-step RRI methodology + 6 personas × 25 questions × 3 modes = 450 q
> - 8 quality dim × 8 axis = 64-cell matrix
> - 7-layer permission pipeline
> - Algo Forge + LLM bridge + HFT async + Cloud Network + Method-hiding linter
>
> **v5 STILL DROPS từ VCK-HU (audit findings vẫn giữ):**
> - `query_loop.py` (244 dòng) + `tool_executor.py` (587 dòng) — dead code
> - `intent_router.py` (683) + `pipeline_router.py` (273) — router pattern
> - Master `/mql5` command — single-prompt router
>
> **Triết lý v5 (4 nguyên tắc):**
> 1. **Comprehensive but direct** — kit có đủ breadth của v3.1 NHƯNG user
>    gọi command trực tiếp, không qua router/agent dispatcher.
> 2. **Domain-anchored** — mỗi command có gating question "EA dev không có
>    cái này thì work-flow break ở đâu?". RRI methodology tham khảo, KHÔNG
>    bắt buộc 450 questions cho mọi EA.
> 3. **External + Internal benchmarks hybrid** — 10 e2e external test
>    (compile + tester thật) + 60 internal probes (module load, schema)
>    thay 125 self-probes của v3.1.
> 4. **Broker-agnostic by construction** — `CPipNormalizer.mqh` flagship
>    + multi-broker stability gate cứng cho XAU/JPY/Forex.

---

## Mục lục

1. [Triết lý v5 + delta vs v4](#1-triết-lý-v5--delta-vs-v4)
2. [Tổng quan numbers v5](#2-tổng-quan-numbers-v5)
3. [3 MCP servers](#3-3-mcp-servers)
4. [Slash commands catalog (~30)](#4-slash-commands-catalog-30)
5. [16 scaffolds × 3 stack matrix](#5-16-scaffolds-3-stack-matrix)
6. [`CPipNormalizer.mqh` — flagship](#6-cpipnormalizermqh--flagship)
7. [22 anti-patterns](#7-22-anti-patterns)
8. [Trader-17 checklist](#8-trader-17-checklist)
9. [RRI methodology — 8 step + 6 personas × 25 × 3](#9-rri-methodology--8-step--6-personas-25-3)
10. [8 quality dim × 8 axis = 64-cell matrix](#10-8-quality-dim-8-axis-64-cell-matrix)
11. [7-layer permission pipeline](#11-7-layer-permission-pipeline)
12. [Multi-broker stability protocol](#12-multi-broker-stability-protocol)
13. [Algo Forge + LLM bridge + HFT async + Cloud Network](#13-algo-forge--llm-bridge--hft-async--cloud-network)
14. [Method-hiding linter (build 5260+)](#14-method-hiding-linter-build-5260)
15. [26 references catalog](#15-26-references-catalog)
16. [Conformance: 10 e2e external + 60 internal probes](#16-conformance-10-e2e-external--60-internal-probes)
17. [Directory layout](#17-directory-layout)
18. [Phase rollout (5 phase / 14-16 tuần)](#18-phase-rollout-5-phase--14-16-tuần)
19. [Worked example: EA Wizard MACD+SAR EURUSD H1 portfolio](#19-worked-example-ea-wizard-macdsar-eurusd-h1-portfolio)
20. [Transparency: vẫn KHÔNG có gì](#20-transparency-vẫn-không-có-gì)
21. [Risk register & mitigation](#21-risk-register--mitigation)

---

## 1. Triết lý v5 + delta vs v4

### Delta v4 → v5

| Aspect | v4 | v5 | Delta | Reason |
|--------|:---:|:---:|:------:|:-------|
| MCP servers | 1 | **3** | +2 | mt5-bridge cho Python data analysis; algo-forge-bridge cho team Git workflow |
| Scaffolds | 3 | **16 × 3 = 48** | +45 | Cover full strategy taxonomy; user chọn scaffold thay tự code |
| References | 6 | **26** | +20 | Cheatsheet domain knowledge cho LLM agent; reduce hallucination |
| Anti-patterns | 8 | **22** | +14 | Best-practice gallery; AP-9..AP-19 = warn (không gate), AP-1..AP-8 + AP-20..AP-22 = critical (gate) |
| Trader checklist | 8 | **17** | +9 | EA dev enterprise audit cần đủ 17 điểm |
| RRI methodology | None | **8 step + 6 personas × 450 q** | +full | Enterprise dev workflow; personal dev có thể skip |
| Quality matrix | 4 dim | **8 dim × 8 axis** | +6 dim, +6 axis | Audit signoff matrix cho enterprise |
| Permission | 2 | **7 layer** | +5 | Defense-in-depth cho enterprise compliance |
| Phase / weeks | 3 / 5 | **5 / 14-16** | +2 phase, +9 wk | Comprehensive rollout |

### v5 KHÔNG add back (vẫn drop)

| VCK-HU module | LOC | Lý do drop |
|---------------|:---:|:----------|
| `query_loop.py` | 244 | Dead code per user audit |
| `tool_executor.py` | 587 | Dead code per user audit |
| `intent_router.py` | 683 | Router pattern user reject |
| `pipeline_router.py` | 273 | Same as intent_router |
| Master `/mql5` command | - | Single-prompt master router pattern |
| **Total dropped LOC** | **~1800** | EA dev gọi command trực tiếp |

→ Net v5 vs v3.1: vẫn lighter ~1800 dòng + 1 master command. Mọi thứ khác restore.

---

## 2. Tổng quan numbers v5

| Aspect | Value |
|--------|:-----:|
| **MCP servers** | 3 |
| **Slash commands** | ~30 (no master, no router) |
| **Sub-agents** | 8 (coordinator/scout/builder/tester/risk-auditor/reviewer/broker-safety/perf-analyst) |
| **Scaffolds** | 16 strategy × 3 stack = 48 trees |
| **References** | 26 |
| **Anti-patterns** | 22 (8 critical gate + 14 best-practice warn) |
| **Trader checklist** | 17 |
| **RRI personas** | 6 |
| **RRI questions runtime** | 450 (6 personas × 25 questions × 3 modes — opt-in cho enterprise) |
| **Quality matrix** | 8 dim × 8 axis = 64 cells |
| **Permission layers** | 7 |
| **Conformance tests** | 10 e2e + 60 internal = 70 |
| **Phases** | 5 |
| **Total weeks** | 14-16 |
| **Plan doc lines** | ~1100 (this file) |

---

## 3. 3 MCP servers

### 3.1 `metaeditor-bridge`
**Purpose:** Wrap MetaEditor CLI compile + parse log.

```python
class MetaEditorBridge:
    def compile(self, mq5_path: str) -> CompileResult:
        # Spawn metaeditor64.exe /compile:<path> /log:<path>
        # Parse log for errors, warnings, line numbers, file paths
        ...
    def parse_log(self, log_path: str) -> List[CompileMessage]:
        # Return structured errors/warnings
        ...
```

**Tools exposed:**
- `metaeditor.compile(mq5_path)` → `{success, errors[], warnings[], ex5_path}`
- `metaeditor.parse_log(log_path)` → `{errors[], warnings[]}`
- `metaeditor.includes_resolve(mq5_path)` → `[include_paths]`

### 3.2 `mt5-bridge` (Python read-only proxy)
**Purpose:** Bidirectional bridge giữa LLM agent và MT5 terminal qua Python `MetaTrader5` package. **READ-ONLY** — không expose trade methods để tránh agent tự gửi lệnh.

```python
class MT5Bridge:
    def initialize(self, login: int, password: str, server: str): ...
    def get_symbols(self) -> List[Symbol]: ...
    def get_rates(self, symbol: str, tf: str, count: int) -> np.ndarray: ...
    def get_account_info(self) -> AccountInfo: ...
    def get_positions(self) -> List[Position]: ...        # READ-ONLY
    def get_history_orders(self, from_date, to_date) -> List[Order]: ...
    # NO order_send, NO order_close, NO position_modify
```

**Tools exposed (15+):**
- `mt5.symbols.list()`, `mt5.symbol.info(symbol)`
- `mt5.rates.copy(symbol, tf, count)` → np.ndarray
- `mt5.account.info()`, `mt5.account.equity()`
- `mt5.positions.list()`, `mt5.positions.history(from, to)`
- `mt5.tick.last(symbol)`
- `mt5.market.book(symbol)` (DOM read)
- `mt5.history.deals(from, to)`
- `mt5.terminal.info()`

**Use case:** Agent analyze portfolio composition + suggest rebalance, NHƯNG human approve và run command thực tế.

### 3.3 `algo-forge-bridge`
**Purpose:** Bridge tới MetaQuotes Algo Forge (forge.mql5.io) — thay Subversion từ build 5100. Git-based workflow cho team trading firms.

```python
class AlgoForgeBridge:
    def init_repo(self, name: str, project: str) -> ForgeRepo: ...
    def clone(self, repo_url: str, dest: str): ...
    def push_pr(self, branch: str, target: str, body: str): ...
    def list_repos(self, org: Optional[str]) -> List[Repo]: ...
```

**Tools exposed:**
- `forge.init(name, description)`
- `forge.clone(repo_url, dest)`
- `forge.commit(repo, msg, files)`
- `forge.pr.create(branch, target, title, body)`
- `forge.pr.list(repo, state)`
- `forge.repo.list(org)`

**Use case:** EA dev enterprise team review code through PR workflow trên Algo Forge platform; integration với CI runner trên cloud.

---

## 4. Slash commands catalog (~30)

**Phân nhóm theo workflow phase. NO master `/mql5` router — user gọi trực tiếp.**

### 4.1 Discovery (4)
- `/mql5-scan` — read-only scout: list .mq5, check kit setup
- `/mql5-survey` — survey strategy taxonomy + match scaffold
- `/mql5-doctor` — health check kit installation + dependencies
- `/mql5-audit` — run 70 conformance tests (10 e2e + 60 internal)

### 4.2 Plan/Design (4)
- `/mql5-rri` — open RRI requirements matrix template (8-step methodology)
- `/mql5-vision` — open Vision template (contractor proposal)
- `/mql5-blueprint` — open blueprint template
- `/mql5-tip` — TIP (technical implementation plan) template

### 4.3 Build (8)
- `/mql5-build <preset>` — emit .mq5 từ scaffold (16 strategy × 3 stack)
- `/mql5-wizard` — CExpert composable scaffold (signal + trailing + money-mgmt)
- `/mql5-pip-normalize` — audit + auto-refactor hardcoded pip → CPipNormalizer
- `/mql5-async-build` — emit OrderSendAsync HFT scaffold
- `/mql5-onnx-export` — Python PyTorch → ONNX
- `/mql5-onnx-embed` — embed `.onnx` vào EA via #resource
- `/mql5-llm-context` — wire LLM bridge (cloud/ollama/embedded-onnx)
- `/mql5-forge-init` — init Algo Forge repo

### 4.4 Verify (8)
- `/mql5-compile` — MetaEditor CLI wrapper
- `/mql5-lint` — 22 AP detector
- `/mql5-method-hiding-check` — build 5260+ inheritance lint
- `/mql5-backtest <set>` — Strategy Tester wrapper + XML parser
- `/mql5-walkforward` — Forward 1/4 mode + IS/OOS Sharpe
- `/mql5-monte-carlo` — bootstrap simulation
- `/mql5-overfit-check` — out-of-sample correlation gate
- `/mql5-multibroker` — orchestrate ≥1 broker mỗi digits class
- `/mql5-fitness` — OnTester custom fitness templates (5 templates)
- `/mql5-mfe-mae` — MFE/MAE per-trade logger

### 4.5 RRI methodology (3)
- `/mql5-rri-bt` — RRI Backtest (5 personas × 7 dim × 8 axis)
- `/mql5-rri-rr` — RRI Risk & Robustness (lieu thay RRI-UX)
- `/mql5-rri-chart` — RRI Chart (optional, for indicator-dev)

### 4.6 Review (5)
- `/mql5-review` — adversarial multi-specialist (7 perspective)
- `/mql5-eng-review` — engineering review (architecture + state machine + invariants)
- `/mql5-ceo-review` — CEO mode (4 mode: SCOPE-EXPANSION/SELECTIVE/HOLD/REDUCTION)
- `/mql5-cso` — security audit (OWASP-equivalent for EA: secrets, broker-creds, WebRequest leak)
- `/mql5-investigate` — root-cause debug (NO-FIX-WITHOUT-INVESTIGATION)
- `/mql5-second-opinion` — secondary CLI/agent review

### 4.7 Deploy (3)
- `/mql5-deploy-vps` — 17-point checklist + MetaQuotes VPS migration guide
- `/mql5-cloud-optimize` — distribute optimization qua MQL5 Cloud Network
- `/mql5-canary` — post-deploy 30-min canary (health, error rate, slippage)

### 4.8 Ship (3)
- `/mql5-forge-pr` — push PR to Algo Forge
- `/mql5-ship` — git tag + push (no PR pipeline)
- `/mql5-refine` — refine ticket (step 8/8 of 8-step methodology)

### 4.9 Other (3)
- `/mql5-broker-safety` — Layer 7 broker-safety pre-deploy gate
- `/mql5-trader-check` — run 17-point checklist
- `/mql5-office-hours` — YC-style 6-question interrogation
- `/mql5-install` — reconcile-install kit overlay

**Total: ~30 commands**, mỗi cái 1 trách nhiệm rõ ràng. KHÔNG có master command — user gõ command name trực tiếp.

---

## 5. 16 scaffolds × 3 stack matrix

### Strategy presets (16)

| # | Preset | Mô tả | Default stack |
|---|--------|-------|:-------------:|
| 1 | `stdlib` | Default greenfield: CExpert + CTrade + CPipNormalizer | netting |
| 2 | `wizard-composable` | MQL5 Wizard pattern: signal + trailing + money-mgmt slot | netting |
| 3 | `trend` | Trend-following (MA cross, ATR breakout) | netting |
| 4 | `mean-reversion` | RSI/Bollinger/Keltner reversion | hedging |
| 5 | `breakout` | Range breakout (Asian session, donchian) | netting |
| 6 | `hedging-multi` | Multi-direction hedge | hedging |
| 7 | `news-trading` | Calendar-driven entries | netting |
| 8 | `arbitrage-stat` | Pairs trading, cointegration | python-bridge |
| 9 | `scalping` | M1/M5 quick-in-out | hedging |
| 10 | `ml-onnx` | PyTorch → ONNX → EA inference | python-bridge |
| 11 | `library` | Reusable .mqh library, no entry logic | (any) |
| 12 | `indicator-only` | Indicator dev (Mashnin parallel branch) | (any) |
| 13 | `hft-async` | OrderSendAsync + OnTradeTransaction handler | netting |
| 14 | `service-llm-bridge` | Service program + WebRequest LLM | python-bridge |
| 15 | `portfolio-basket` | Multi-symbol map<string, CPipNormalizer> | netting |
| 16 | `grid` | Grid trading (with daily-loss cap mandatory) | hedging |
| 17 | `dca` | Dollar-cost-averaging accumulation | hedging |

### 3 stack matrix

| Stack | Description | Use case |
|-------|-------------|----------|
| **netting** | Single position per symbol (US-style) | Simple EA, retail forex broker |
| **hedging** | Multi-position per symbol (MT5 hedging mode) | Grid, DCA, multi-direction |
| **python-bridge** | EA + Python sidecar via WebRequest/MetaTrader5 | ONNX, LLM, advanced analytics |

**Total: 17 strategy × 3 stack = 51 trees** — user chọn 1 khi `/mql5-build`.

(Note: vài combination vô nghĩa, e.g. `library × netting` = same as `library × hedging`. Kit ship 48 thực tế combinations.)

### Scaffold tree example: `wizard-composable × netting`

```
ea-wizard-composable-netting/
├── EAName.mq5                       # CExpert template, signal/trailing/money slot
├── Include/
│   ├── (ref to kit Include/)
│   └── EAName_Signal_MACD.mqh       # signal module slot
│   └── EAName_Trailing_FixedStep.mqh
│   └── EAName_Money_FixRisk.mqh
├── Sets/
│   ├── default.set
│   └── eurusd-h1.set
└── README.md
```

---

## 6. `CPipNormalizer.mqh` — flagship

(Identical to v4. Module duy nhất kit MUST ship đúng nghĩa "kit's IP".)

```cpp
class CPipNormalizer {
private:
   string m_symbol;
   int    m_digits;
   double m_point, m_pip, m_pip_in_points;
   double m_tick_size, m_tick_value, m_pip_value_per_lot;
   long   m_stops_level, m_freeze_level;

public:
   bool   Init(const string symbol = NULL);
   double Pips(int pips) const;
   double PriceToPips(double dist) const;
   double PipValue(int pips, double lots) const;
   double LotForRisk(double risk_$, int sl_pips) const;
   bool   IsValidSLDistance(int sl_pips) const;
   int    ClampSLPips(int desired) const;
};
```

**Truth table chính thức (reference 79):**

| Digits | Symbol example | Point | Pip | Note |
|:------:|----------------|-------|-----|------|
| 5 | EURUSD 1.23456 | 0.00001 | 0.0001 | Forex modern |
| 4 | EURUSD 1.2345 | 0.0001 | 0.0001 | Forex legacy |
| 3 | USDJPY 151.xxx | 0.001 | 0.01 | JPY 3d |
| 3 | XAUUSD 4589.xxx (Exness) | 0.001 | **0.1** | XAU 3d (metal ×10) |
| 2 | XAUUSD 4567.xx (IC) | 0.01 | **0.1** | XAU 2d (metal ×10) |
| 2 | Indices (non-metal) | 0.01 | 0.01 | Indices 2d |
| 1 | US30 35000.x | 0.1 | 1.0 | Indices (rare) |

**Quy tắc canonical:**
1. `pip = (digits ∈ {3,5}) ? 10*point : 1*point`
2. **Metals (XAU/XAG):** pip ×10 extra → 1 USD = 10 pips convention.

---

## 7. 22 anti-patterns

### Critical (8) — gate, must-fix

| Code | Tên | Detector |
|------|-----|----------|
| AP-1 | No-SL | OrderSend/CTrade.Buy không set sl |
| AP-3 | Lot-fixed | hardcoded `lot = 0.01` |
| AP-5 | Optimizer-overfitted | tester-set > 6 input + > 100k pass |
| AP-15 | Raw-OrderSend (skip CTrade) | direct `OrderSend()` |
| AP-17 | WebRequest-in-OnTick | `WebRequest()` in OnTick/OnTimer |
| AP-18 | OrderSendAsync-no-handler | Async without OnTradeTransaction |
| AP-20 | Hardcoded-pip-no-normalization | regex `\* 0\.000?1?`, `\* _Point` |
| AP-21 | JPY-XAU-digits-broken | EA tested < 2 broker digits classes |

### Best-practice (13) — warn, không gate

| Code | Tên | Detector |
|------|-----|----------|
| AP-2 | SL-too-tight | SL < stops_level * 1.5 |
| AP-4 | Martingale-no-cap | Lot doubling without max_lot |
| AP-6 | Curve-fitted | walk-forward IS/OOS correlation < 0.5 |
| AP-7 | Hardcoded-magic | magic = literal int (not registry) |
| AP-8 | No-spread-guard | OrderSend without spread check |
| AP-9 | Multi-entry-same-bar | OrderSend in same Bars(_Symbol, _Period) |
| AP-10 | OrderSend-no-check | not check ResultRetcode |
| AP-11 | Mode-blind | Not respect netting/hedging mode |
| AP-12 | Leak-handle | iCustom/iMA without IndicatorRelease |
| AP-13 | Broker-coupled | EA hard-coded broker name string |
| AP-14 | No-MFE-MAE | Missing per-trade MFE/MAE log |
| AP-16 | Reinvent-stdlib | Custom CTrade-equivalent wrapper |
| AP-19 | ONNX-no-tester-validation | Model deploy without tester run |

### Build-specific (1) — warn, build 5260+ only

| Code | Tên | Detector |
|------|-----|----------|
| AP-22 | Method-hiding-build-5260+ | Derived class hides base method (sửa từ build 5260) |

(See §14 cho method-hiding linter detail.)

---

## 8. Trader-17 checklist

**Restore từ v3.1, EA-domain version của VN-12 checklist của VCK-HU.**

| # | Key | Pass khi… |
|---|-----|-----------|
| 1 | `sl_set_every_trade` | AP-1 không vi phạm |
| 2 | `lot_risk_based` | Lot tính qua `CPipNormalizer.LotForRisk` |
| 3 | `magic_reserved_unique` | `CMagicRegistry` đăng ký + collision check |
| 4 | `spread_guarded` | OrderSend có spread check (AP-8) |
| 5 | `daily_loss_capped` | `CRiskGuard.DailyLossLimit` enforced |
| 6 | `news_session_guarded` | Calendar/session filter active |
| 7 | `pip_normalized_via_kit` | `CPipNormalizer.Init` log trong journal |
| 8 | `multi_broker_tested` | ≥1 broker mỗi digits class |
| 9 | `walkforward_passed` | IS/OOS correlation ≥ 0.5 |
| 10 | `monte_carlo_validated` | DD percentile 95th ≤ 1.5x reported |
| 11 | `overfit_checked` | OOS Sharpe ≥ 70% IS Sharpe |
| 12 | `mfe_mae_logged` | CSV file written each trade |
| 13 | `journal_observable` | OnInit + OnDeinit log structure |
| 14 | `external_dependency_fallback` | LLM/ONNX/WebRequest có rule-based fallback |
| 15 | `vps_deployed` | EA chạy trên MetaQuotes Native VPS hoặc broker VPS, không desktop |
| 16 | `llm_fallback_defined` | Nếu dùng LLM, có timeout + fallback rule |
| 17 | `pip_normalized_across_brokers` | Multi-broker journal verified pip math correct |

---

## 9. RRI methodology — 8 step + 6 personas × 25 × 3

### 8-step workflow

```
1. SCAN          — read repo, identify pain points, list .mq5 files
2. RRI           — fill Requirements Matrix (R0..R7 dimensions)
3. VISION        — Contractor proposal: scope + cost + timeline + risk
4. BLUEPRINT     — Architecture diagram + state machine + invariants
5. TIP           — Technical Implementation Plan (modules + interface)
6. BUILD         — emit code from scaffold + custom (via /mql5-build/wizard)
7. VERIFY        — compile + lint + backtest + walkforward + multibroker + RRI-bt
8. REFINE        — refine ticket: classify diff against v5 refine envelope
```

### 6 RRI personas

| Persona | Mô tả | Domain expertise |
|---------|-------|------------------|
| **trader** | End-user trader | UX, risk perception |
| **risk-auditor** | Risk officer | DD, VAR, stress test |
| **broker-engineer** | Broker liquidity engineer | Fill quality, slippage |
| **strategy-architect** | Quant/strategist | Signal logic, expectancy |
| **devops** | Deployment engineer | VPS, observability |
| **perf-analyst** | Backtest analyst | Tester reports, optimizer |

### 25 questions × 3 modes (= 75/persona, 450 total)

Mỗi persona có 25 câu chuẩn × 3 mode (PERSONAL / TEAM / ENTERPRISE).

**Personal mode** — dùng 5 câu critical/persona (= 30 questions total, ~30 phút audit).
**Team mode** — dùng 12 câu/persona (= 72 questions, ~2-3 giờ).
**Enterprise mode** — full 25 câu/persona (= 450 questions, ~1-2 ngày audit cho compliance).

**Default scope:** PERSONAL. Enterprise opt-in via `/mql5-rri --mode=enterprise`.

### Persona × Step matrix (8 × 6 = 48 cells)

|           | SCAN | RRI | VISION | BLUEPRINT | TIP | BUILD | VERIFY | REFINE |
|-----------|:----:|:---:|:------:|:---------:|:---:|:-----:|:------:|:------:|
| trader    | x | x | x | - | - | - | x | x |
| risk-auditor | - | x | x | x | x | - | x | x |
| broker-engineer | - | x | x | x | - | - | x | - |
| strategy-architect | x | x | x | x | x | x | x | x |
| devops | - | - | x | x | x | x | x | - |
| perf-analyst | - | - | - | x | x | - | x | x |

x = persona involved in step. - = skip.

---

## 10. 8 quality dim × 8 axis = 64-cell matrix

**Restore từ v3.1. Audit signoff matrix cho enterprise.**

### 8 quality dims

| Dim | Mô tả |
|-----|-------|
| `d_correctness` | Compile clean, lint pass, no AP-1/3/5/15/17/18/20/21 |
| `d_risk` | SL set, lot risk-based, daily-loss capped, spread guarded |
| `d_robustness` | Walk-forward + Monte Carlo + overfit OOS check |
| `d_perf` | Backtest PF/Sharpe/MaxDD acceptable, exec latency p95 |
| `d_maintainability` | Stdlib reuse, magic registered, modular |
| `d_observability` | Journal structured, MFE/MAE CSV, OnInit/OnDeinit log |
| `d_broker-safety` | Multi-broker tested, pip-normalized, broker-mode aware |
| `d_inference` | (ONNX scaffold only) Model versioned, inference latency p95 < 1ms, fallback rule |

### 8 axis

```
1. design       — pre-implementation review
2. implement    — code review pass
3. unit-test    — module-level test
4. integration  — multi-module test
5. backtest     — Strategy Tester pass
6. walk-forward — IS/OOS pass
7. multi-broker — protocol B-1/B-2/B-3 pass
8. live-canary  — 30-min post-deploy
```

### 64-cell audit matrix

Each cell = (dim, axis) → status: PASS / WARN / FAIL / N/A.

EA ships v1.0 khi: ≥56/64 PASS, 0 FAIL, ≤8 WARN.
Enterprise compliance: ≥60/64 PASS, 0 FAIL, ≤4 WARN.

---

## 11. 7-layer permission pipeline

**Restore từ v3.1. Defense-in-depth cho enterprise compliance.**

```
Layer 1: SOURCE-LINT       — pre-commit hook: format, syntax pre-check
Layer 2: COMPILE-GATE      — MetaEditor 0 errors required (warnings allowed)
Layer 3: AP-LINT           — 8 critical AP must pass; 14 warn allowed
Layer 4: CHECKLIST-GATE    — Trader-17 checklist ≥15/17 pass
Layer 5: METHODOLOGY-GATE  — RRI 8-step completed (mode-dependent)
Layer 6: QUALITY-MATRIX    — 64-cell audit ≥56 PASS
Layer 7: BROKER-SAFETY     — multi-broker stability + pip-norm verified
```

**Enforcement:** Each layer là 1 script. CI runs in sequence; fail at any layer = block ship.

**Personal mode:** Layer 1, 2, 3, 4, 7 enforced. Layer 5, 6 opt-in.
**Enterprise mode:** Layer 1-7 mandatory.

---

## 12. Multi-broker stability protocol

(Identical to v4. Cốt lõi của broker-safety layer.)

### Protocol B-1: Cross-digits-class test

| Symbol class | Required broker digit class | Suggested |
|--------------|------------------------------|-----------|
| XAU/Indices | ≥1 broker 3d **+** ≥1 broker 2d | Exness (3d) + ICMarkets (2d) |
| JPY pairs | ≥1 broker 3d | FxPro (3d) |
| Major forex | ≥1 broker 5d | Most modern |
| Crypto/exotic | optional | (skip) |

### Protocol B-2: Stability tolerance

```
PF_stdev / PF_mean ≤ 0.30
Sharpe_stdev ≤ 0.20
DD_max - DD_min ≤ 5%
```

### Protocol B-3: Pip-normalizer log verification

Journal MUST có:

```
[PipNorm] <SYMBOL>: digits=<2|3|5> point=<...> pip=<...> ...
```

Một line/symbol/broker.

---

## 13. Algo Forge + LLM bridge + HFT async + Cloud Network

### 13.1 Algo Forge integration (build 5100+, 06/2025)

**Background:** MetaQuotes thay Subversion bằng Git-based platform tại `forge.mql5.io`. Toàn bộ MetaQuotes tools (MetaEditor) đã hỗ trợ Git native.

**Kit components:**
- `algo-forge-bridge` MCP (xem §3.3)
- `/mql5-forge-init` — init repo trên forge.mql5.io
- `/mql5-forge-pr` — push PR
- Reference 70: `algo-forge.md` — workflow guide

**Workflow:**
```
EA dev local → git commit → /mql5-forge-pr → forge.mql5.io PR review → merge → CI runner
```

### 13.2 LLM bridge scaffold (`service-llm-bridge`)

**Purpose:** EA gọi LLM (cloud/local) để decide trade context. Service program pattern (build 5320+).

**3 sub-pattern:**

| Sub-pattern | Description | Reference |
|-------------|-------------|-----------|
| `cloud-api` | WebRequest → OpenAI/Claude/Gemini | 76 |
| `self-hosted-ollama` | WebRequest → localhost:11434 (Ollama) | 76 |
| `embedded-onnx-llm` | Embed Phi-3 mini ONNX trực tiếp | 76 |

**Fallback rule mandatory** (Trader-17 #14, #16): timeout 5s → fall back rule-based logic.

**Anti-pattern enforced:**
- AP-17: WebRequest-in-OnTick → DROP, dùng OnTimer hoặc service program
- New: WebRequest secret leak → secrets via terminal common variables, not hardcoded

### 13.3 HFT async scaffold (`hft-async`)

**Purpose:** Sub-millisecond order execution cho scalping/arbitrage.

**Pattern:**
```cpp
// OrderSendAsync + OnTradeTransaction handler mandatory
void OnTick() {
    if (signal && !pending_order_id) {
        MqlTradeRequest req = {...};
        MqlTradeResult res = {...};
        OrderSendAsync(req, res);
        pending_order_id = res.request_id;
    }
}

void OnTradeTransaction(const MqlTradeTransaction &trans, ...) {
    if (trans.type == TRADE_TRANSACTION_REQUEST) {
        if (trans.order == pending_order_id) {
            // Track fill, log latency
        }
    }
}
```

**Reference 77: `async-hft.md`** — full pattern + latency benchmark.

**Anti-pattern enforced:** AP-18 — OrderSendAsync without OnTradeTransaction handler.

### 13.4 Cloud Network distributed optimize

**Background:** MQL5 Cloud Network = thousands of CPU agents worldwide. 100k+ pass GA optimization in hours.

**Kit components:**
- `/mql5-cloud-optimize` — wrapper for Strategy Tester cloud mode
- Reference 73: `cloud-network.md` — cost estimation + setup

**Cost gate:** Default DENY for personal mode (avoid surprise bills). Enterprise mode opt-in with budget cap.

---

## 14. Method-hiding linter (build 5260+)

**Background:** MetaQuotes build 5260 (09/2025) introduced new rule: derived class hides base class method by default. Breaking change cho EA dev có deep inheritance.

**Linter detector:**

```python
def check_method_hiding(mq5_path: str) -> List[Issue]:
    """
    Detect: derived class method với same name as base class method,
    không có explicit `using BaseClass::method`.
    """
    ...
```

**Severity:**
- **Build < 5260:** WARN (không break, but future-proof)
- **Build ≥ 5260:** ERROR (compile fail without explicit using)

**Kit auto-detect target build via `MQLInfoInteger(MQL_PROGRAM_TYPE)` + version check.**

**Reference:** Reference 50 (survey) + reference 53 (broker-modes) cite build versions.

---

## 15. 26 references catalog

### MQL5 fundamentals (10)

| # | File | Pages | Source |
|---|------|-------|--------|
| 50 | `survey.md` | 1-page kit overview | v5 plan |
| 51 | `platform-arch.md` | MT5 architecture, terminal/server | mql5book + mql5 ref |
| 52 | `multi-symbol.md` | Multi-symbol patterns | mql5book ch 11 |
| 53 | `broker-modes.md` | Netting/hedging, account types | mql5 ref |
| 54 | `stl-cheatsheet.md` | Standard library (CExpert, CTrade, CArray, CHashMap) | Mashnin |
| 55 | `tester-stats.md` | Tester core statistics | Mashnin |
| 56 | `walkforward.md` | Walk-forward methodology | Korotky |
| 57 | `monte-carlo.md` | Monte Carlo simulation | Korotky |
| 58 | `overfit.md` | Overfit detection patterns | Korotky |
| 59 | `trader-checklist.md` | Trader-17 deep dive | v5 plan |

### Mashnin Advanced book delta (8)

| # | File | Source |
|---|------|--------|
| 60 | `wizard-cexpert.md` | MQL5 Wizard composable pattern | Mashnin ch 5-7 |
| 61 | `tester-metrics.md` | 14 canonical metrics (PF, RF, Sharpe, GHPR, AHPR, EP, LR Corr/StdErr, MFE/MAE corr) | Mashnin |
| 62 | `mfe-mae.md` | MFE/MAE per-trade logging | Mashnin |
| 63 | `tester-config.md` | Tester .ini, period, model, deposit | Mashnin |
| 64 | `fitness-templates.md` | OnTester custom fitness (5 templates) | Mashnin |
| 65 | `multi-broker.md` | Multi-broker stability protocol | v5 plan |
| 66 | `stdlib-trade-classes.md` | CTrade/CPositionInfo/COrderInfo deep dive | Mashnin |
| 67 | `indicator-dev-parallel.md` | Indicator dev workflow | Mashnin |

### MQL5 2024-2025 updates (10)

| # | File | Source |
|---|------|--------|
| 70 | `algo-forge.md` | Build 5100+ Git platform | MetaQuotes news |
| 71 | `onnx-mql5.md` | ONNX runtime 1.14, embed pattern | MetaQuotes |
| 72 | `matrix-vector.md` | Matrix/vector first-class types, BLAS | Build 4620-5430 |
| 73 | `cloud-network.md` | MQL5 Cloud Network optimize | mql5.com |
| 74 | `vps.md` | MetaQuotes Native VPS 0-5ms | mql5.com/vps |
| 75 | `webrequest.md` | WebRequest patterns, secret handling | mql5 ref |
| 76 | `llm-patterns.md` | Cloud/Ollama/embedded-ONNX LLM | v5 plan |
| 77 | `async-hft.md` | OrderSendAsync + OnTradeTransaction | mql5 ref |
| 78 | `opencl.md` | GPU compute for neural net training | MetaQuotes |
| 79 | `pip-norm.md` | Cross-broker pip math (flagship doc) | v5 plan |

**Total: 26 references, ~80-100KB compressed knowledge cho LLM agent context.**

---

## 16. Conformance: 10 e2e external + 60 internal probes

### 10 e2e external (from v4)

(See v4 §10 — same 10 tests.)

### 60 internal probes (lighter than v3.1's 125+)

```
probes_modules/      (15 probes)  - module load, schema, version sync
probes_scaffolds/    (15 probes)  - 16 scaffold tree validity, default .set valid
probes_references/   (10 probes)  - 26 references exist, frontmatter valid
probes_methodology/  (10 probes)  - RRI personas defined, 8-step config
probes_governance/   (10 probes)  - VERSION mirror, SBOM, license
```

**Total: 70 conformance tests (10 e2e + 60 internal)** — vs v3.1's 125+ self-probes.

---

## 17. Directory layout

```
vibecodekit-mql5-ea/
├── README.md
├── VERSION
├── pyproject.toml
├── LICENSE
│
├── Include/                                 # MQL5 shared libs
│   ├── CPipNormalizer.mqh                   # flagship
│   ├── CRiskGuard.mqh
│   ├── CMagicRegistry.mqh
│   ├── COnnxLoader.mqh
│   ├── CAsyncTradeManager.mqh               # OrderSendAsync helper
│   └── CSpreadGuard.mqh
│
├── scripts/
│   └── vibecodekit_mql5/
│       ├── __init__.py
│       ├── build.py                         # /mql5-build
│       ├── wizard.py                        # /mql5-wizard
│       ├── lint.py                          # /mql5-lint (22 AP)
│       ├── method_hiding_check.py            # /mql5-method-hiding-check
│       ├── compile.py                       # /mql5-compile
│       ├── pip_normalize.py                 # /mql5-pip-normalize
│       ├── async_build.py                   # /mql5-async-build
│       ├── backtest.py                      # /mql5-backtest
│       ├── walkforward.py                   # /mql5-walkforward
│       ├── monte_carlo.py                   # /mql5-monte-carlo
│       ├── overfit_check.py                 # /mql5-overfit-check
│       ├── multibroker.py                   # /mql5-multibroker
│       ├── fitness.py                       # /mql5-fitness
│       ├── mfe_mae.py                       # /mql5-mfe-mae
│       ├── onnx_export.py                   # /mql5-onnx-export
│       ├── onnx_embed.py                    # /mql5-onnx-embed
│       ├── llm_context.py                   # /mql5-llm-context
│       ├── forge_init.py                    # /mql5-forge-init
│       ├── forge_pr.py                      # /mql5-forge-pr
│       ├── deploy_vps.py                    # /mql5-deploy-vps
│       ├── cloud_optimize.py                # /mql5-cloud-optimize
│       ├── canary.py                        # /mql5-canary
│       ├── ship.py                          # /mql5-ship
│       ├── trader_check.py                  # /mql5-trader-check
│       ├── broker_safety.py                 # /mql5-broker-safety (Layer 7)
│       ├── audit.py                         # /mql5-audit (run 70 conformance tests)
│       ├── doctor.py                        # /mql5-doctor
│       ├── install.py                       # /mql5-install
│       ├── rri/
│       │   ├── personas.py                  # 6 personas × 25 q × 3 modes
│       │   ├── step_workflow.py             # 8-step engine
│       │   ├── matrix.py                    # 8 dim × 8 axis
│       │   ├── rri_bt.py                    # /mql5-rri-bt
│       │   ├── rri_rr.py                    # /mql5-rri-rr
│       │   └── rri_chart.py                 # /mql5-rri-chart
│       ├── permission/
│       │   ├── layer1_source_lint.py
│       │   ├── layer2_compile.py
│       │   ├── layer3_ap_lint.py
│       │   ├── layer4_checklist.py
│       │   ├── layer5_methodology.py
│       │   ├── layer6_quality_matrix.py
│       │   └── layer7_broker_safety.py
│       └── conformance/
│           ├── e2e/                         # 10 external tests
│           ├── probes_modules.py            # 15 probes
│           ├── probes_scaffolds.py          # 15 probes
│           ├── probes_references.py         # 10 probes
│           ├── probes_methodology.py        # 10 probes
│           └── probes_governance.py         # 10 probes
│
├── scaffolds/                                # 17 strategy × 3 stack
│   ├── stdlib/  {netting, hedging, python-bridge}
│   ├── wizard-composable/
│   ├── trend/
│   ├── mean-reversion/
│   ├── breakout/
│   ├── hedging-multi/
│   ├── news-trading/
│   ├── arbitrage-stat/
│   ├── scalping/
│   ├── ml-onnx/
│   ├── library/
│   ├── indicator-only/
│   ├── hft-async/
│   ├── service-llm-bridge/
│   ├── portfolio-basket/
│   ├── grid/
│   └── dca/
│
├── references/                               # 26 cheatsheets
│   ├── 50-survey.md
│   ├── 51-platform-arch.md
│   ├── 52-multi-symbol.md
│   ├── 53-broker-modes.md
│   ├── 54-stl-cheatsheet.md
│   ├── 55-tester-stats.md
│   ├── 56-walkforward.md
│   ├── 57-monte-carlo.md
│   ├── 58-overfit.md
│   ├── 59-trader-checklist.md
│   ├── 60-wizard-cexpert.md
│   ├── 61-tester-metrics.md
│   ├── 62-mfe-mae.md
│   ├── 63-tester-config.md
│   ├── 64-fitness-templates.md
│   ├── 65-multi-broker.md
│   ├── 66-stdlib-trade-classes.md
│   ├── 67-indicator-dev-parallel.md
│   ├── 70-algo-forge.md
│   ├── 71-onnx-mql5.md
│   ├── 72-matrix-vector.md
│   ├── 73-cloud-network.md
│   ├── 74-vps.md
│   ├── 75-webrequest.md
│   ├── 76-llm-patterns.md
│   ├── 77-async-hft.md
│   ├── 78-opencl.md
│   └── 79-pip-norm.md
│
├── tests/
│   ├── e2e/                                  # 10 external (real MetaEditor + tester)
│   ├── unit/                                 # per-module unit
│   └── fixtures/                             # sample .mq5, .xml reports
│
├── mcp/
│   ├── metaeditor-bridge/
│   │   └── server.py
│   ├── mt5-bridge/                           # Python read-only proxy
│   │   └── server.py
│   └── algo-forge-bridge/
│       └── server.py
│
└── examples/
    └── ea-wizard-macd-sar-eurusd-h1-portfolio/   # worked example
        ├── EAName.mq5
        ├── eurusd-h1.set
        └── README.md
```

---

## 18. Phase rollout (5 phase / 14-16 tuần)

| Phase | Weeks | Goal | Deliverable | Acceptance gate |
|-------|-------|------|-------------|-----------------|
| **A — Core Foundation** | 3 | CPipNormalizer + CRiskGuard + CMagicRegistry + 8 critical AP lint + 4 core scaffolds (stdlib, wizard, portfolio, ml-onnx) + /mql5-build, /mql5-lint, /mql5-compile, /mql5-pip-normalize | v0.1.0 | e2e test 1, 2, 3 pass |
| **B — Test & Validation** | 3 | Strategy Tester + walkforward + monte_carlo + overfit + multibroker + Trader-17 + /mql5-deploy-vps | v0.2.0 | e2e 4, 5, 6, 7, 8, 9 pass |
| **C — Methodology** | 3 | 6 RRI personas + 8-step + 8×8 quality matrix + 7-layer permission + 13 best-practice AP | v0.3.0 | RRI engine load + matrix populates |
| **D — Tech Updates 2024-2025** | 3-4 | ONNX scaffold + HFT async + Algo Forge + LLM bridge + Cloud Network + VPS + Method-hiding linter | v0.5.0 | e2e 10 pass + Algo Forge integration test |
| **E — Polish & Ship** | 2-3 | Worked example + 26 references full content + docs + 3 MCP servers + canary | v1.0.0 | 70 conformance tests pass |

**Total: 14-16 tuần** (vs v3.1: 20 tuần, vs v4: 5 tuần).

---

## 19. Worked example: EA Wizard MACD+SAR EURUSD H1 portfolio

8-step workflow demonstration:

### Step 1: SCAN
```
$ /mql5-scan
✓ Project workspace clean
✓ Kit installed: vibecodekit-mql5-ea v1.0.0
✓ MetaTrader path: C:\Program Files\MetaTrader 5
✓ MetaEditor build: 5430
```

### Step 2: RRI
```
$ /mql5-rri --mode=team
[Opens template, 6 personas × 12 questions = 72 q]
✓ R0 (functional): EA must signal MACD + Parabolic SAR confluence on EURUSD H1
✓ R3 (risk): max DD 15%, daily loss 5%, lot 1% risk
✓ R5 (broker): test on FxPro 5d + Exness 3d
✓ R7 (deploy): MetaQuotes Native VPS, 24/7
[saved to docs/rri.md]
```

### Step 3: VISION
```
$ /mql5-vision
[Contractor proposal]
- Scope: Wizard composable EA, MACD + SAR signal slot
- Effort: 8 TIPs
- Risk: methodology + broker-coupled (mitigated by multi-broker test)
- Cost (cloud-optimize): est. 10-20 USD
```

### Step 4: BLUEPRINT
```
$ /mql5-blueprint
[Architecture diagram + state machine]
EAName.mq5 → CExpert
              ├── CExpertSignal_MACD
              ├── CExpertSignal_SAR  
              ├── CExpertTrailing_FixedStep
              └── CExpertMoney_FixRisk → CPipNormalizer.LotForRisk
[saved to docs/blueprint.md]
```

### Step 5: TIP
```
$ /mql5-tip
[8 TIPs]
TIP-1: scaffold wizard-composable
TIP-2: implement Signal_MACD + Signal_SAR confluence
TIP-3: wire CPipNormalizer in OnInit
TIP-4: implement Trailing_FixedStep
TIP-5: implement Money_FixRisk (SL int pips)
TIP-6: backtest 2023-2024
TIP-7: walkforward + monte carlo + multi-broker
TIP-8: VPS deploy + canary
```

### Step 6: BUILD
```
$ /mql5-wizard --name EAMacdSar --symbol EURUSD --tf H1 \
  --signal MACD,SAR --trailing FixedStep --money FixRisk \
  --stack netting
✓ Created EAMacdSar/{EAMacdSar.mq5, Sets/, Include/, README.md}
✓ CPipNormalizer wired in OnInit
✓ Magic registered: 70042
```

### Step 7: VERIFY (multi-stage)
```
$ /mql5-compile EAMacdSar/EAMacdSar.mq5
✓ 0 errors, 0 warnings → EAMacdSar.ex5

$ /mql5-lint EAMacdSar/EAMacdSar.mq5
✓ 8/8 critical AP pass; 13/13 best-practice pass
✓ Method-hiding check (build 5430): pass

$ /mql5-backtest EAMacdSar/EAMacdSar.ex5 EAMacdSar/Sets/eurusd-h1.set \
                  --period 2023.01.01-2024.12.31
✓ PF 1.78, Sharpe 0.42, MaxDD 8.2%

$ /mql5-walkforward EAMacdSar/EAMacdSar.ex5 EAMacdSar/Sets/eurusd-h1.set
✓ IS Sharpe 0.45, OOS Sharpe 0.38, correlation 0.78 (≥ 0.5)

$ /mql5-monte-carlo EAMacdSar/EAMacdSar.ex5 --iterations 1000
✓ DD percentile 95th: 11.2% (≤ 1.5x reported 8.2% → 12.3%)

$ /mql5-overfit-check EAMacdSar/EAMacdSar.ex5
✓ OOS/IS Sharpe ratio: 0.84 (≥ 70%)

$ /mql5-multibroker EAMacdSar/EAMacdSar.ex5 EAMacdSar/Sets/eurusd-h1.set \
                     --brokers fxpro-5d,exness-3d
✓ FxPro 5d:  PF 1.78, Sharpe 0.42, MaxDD 8.2%
✓ Exness 3d: PF 1.74, Sharpe 0.40, MaxDD 8.5%
✓ PF stdev/mean = 0.011 (≤ 0.30) → PASS

$ /mql5-trader-check EAMacdSar/EAMacdSar.ex5
✓ 17/17 checklist pass

$ /mql5-rri-bt --personas all  # backtest review 5 persona × 7 dim × 8 axis
✓ 56/64 PASS, 0 FAIL, 8 WARN → quality matrix gate pass

$ /mql5-broker-safety EAMacdSar/EAMacdSar.ex5  # Layer 7 final
✓ Pip math verified across 2 broker classes
✓ Magic 70042 unique
✓ Daily loss cap = 5% USD enforced
✓ All 7 permission layers pass
```

### Step 8: REFINE + ship
```
$ /mql5-deploy-vps EAMacdSar/EAMacdSar.ex5
✓ 17/17 checklist pass
✓ Migration guide: docs/MIGRATE-VPS.md

$ /mql5-canary EAMacdSar/EAMacdSar.ex5 --duration=30m
[Live monitor 30 min on VPS]
✓ 0 errors, slippage p95 = 0.4 pips (acceptable)
✓ MFE/MAE log written: 12 entries

$ /mql5-refine
[Diff vs v5 envelope]
✓ Refine ticket: 2 new module + 1 update + 0 delete

$ /mql5-ship --tag v1.0.0
✓ git tag v1.0.0 + git push
$ /mql5-forge-pr (optional, enterprise team flow)
✓ PR #42 created on forge.mql5.io
```

**Total turnaround: ~4-6 hours từ scaffold → live canary** (enterprise mode + RRI methodology). Personal mode skip RRI/quality-matrix → ~1-2 hours.

---

## 20. Transparency: vẫn KHÔNG có gì

**v5 KHÔNG kế thừa từ VCK-HU (so vẫn lighter v3.1 ~1800 dòng Python):**

| VCK-HU module | LOC | Status v5 | Lý do |
|---------------|:---:|-----------|-------|
| `query_loop.py` | 244 | **DROP** | Dead code per audit; user gọi command trực tiếp |
| `tool_executor.py` | 587 | **DROP** | Dead code; Python script per command thay generic executor |
| `intent_router.py` | 683 | **DROP** | Router pattern; user gõ command name |
| `pipeline_router.py` | 273 | **DROP** | Same |
| Master `/mql5` command | - | **DROP** | Single-prompt master router |
| 33 hook lifecycle events | ~400 | **PARTIAL DROP** | Giữ pre-commit (Layer 1) + post-deploy (canary). Drop 31 events khác |
| Approval contract appr-<16hex> | ~200 | **DROP** | Default opt-in cho enterprise mode only |
| 3-tier memory hierarchy | ~300 | **DROP** | EA workspace = 1 dir |
| Dream tasks / cost ledger | ~400 | **DROP** | YAGNI |
| Embedding backend / sentence-transformers | ~500 | **DROP** | YAGNI |

**Total still-dropped LOC: ~3600 từ VCK-HU.**

Nếu anh/chị muốn add thêm bất kỳ piece nào trên, báo và tôi sẽ port:
- Command-router (master `/mql5` + intent_router) — 956 dòng
- Generic tool executor (tool_executor) — 587 dòng
- Plan executor (query_loop) — 244 dòng
- Hook system (33 events) — 400 dòng
- Approval contract — 200 dòng
- 3-tier memory — 300 dòng

---

## 21. Risk register & mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|:----------:|:------:|------------|
| **Re-introduces over-engineering** (v3.1 trap) | Medium | High | 4 nguyên tắc triết lý làm gating; mỗi command pass "không có thì work-flow break ở đâu" |
| **17 scaffold quá nhiều, maintain burden** | Medium | Medium | Phase A ship 4 core; Phase D ship 13 còn lại as "community-maintained tier" |
| **450 RRI questions overwhelming for personal dev** | High | Medium | Default mode = PERSONAL (30 q); Enterprise opt-in |
| **64-cell matrix quá detail cho EA basic** | Medium | Low | Personal mode = 16 cell (4 dim × 4 axis); Enterprise = 64 |
| **7-layer permission overlap** | Medium | Low | Each layer có distinct concern (lint vs compile vs methodology vs broker-safety) |
| **3 MCP servers maintenance** | Low | Medium | mt5-bridge READ-ONLY (no trade methods); algo-forge-bridge depends on MetaQuotes API stability |
| **Method-hiding linter false positive** (build 5260+) | Medium | Low | Allow `// vck-mql5: hiding-ok` comment opt-out |
| **Cloud Network surprise bills** | Medium | High | Personal mode default DENY; Enterprise budget cap mandatory |
| **Algo Forge API changes** | Medium | Medium | Bridge MCP isolated; can replace impl without changing kit interface |
| **LLM bridge prompt injection** | Medium | High | Embedded-ONNX preferred over cloud-API; secret via terminal common variables |

---

## Đính kèm: Verdict v5 vs 5 audit anti-patterns

| Anti-pattern (audit) | v3.1 | v4 | **v5** |
|----------------------|:----:|:--:|:------:|
| Over-engineering | YES | NO | **PARTIAL** (comprehensive but each feature gating-justified) |
| Conformance audit self-referential | YES | NO | **PARTIAL** (10 e2e external + 60 internal hybrid) |
| God Module | YES | NO | **NO** (mỗi script.py < 200 LOC + 1 trách nhiệm) |
| Dead code (query_loop + tool_executor) | YES | NO | **NO** (still dropped) |
| Intent router | YES | NO | **NO** (still dropped, no master command) |

**v5 = comprehensive kit cho enterprise + personal, vẫn tránh 3/5 critical anti-patterns. Over-engineering + self-referential audit là PARTIAL — mitigation qua gating + external test layer.**

---

*Plan v5 hoàn chỉnh. v1, v2, v3.1, v4 vẫn lưu làm reference (không phải implement target). Sau approve, Phase A start với 4 core scaffold + CPipNormalizer + 8 critical AP lint + 4 core commands (Week 1-3).*
