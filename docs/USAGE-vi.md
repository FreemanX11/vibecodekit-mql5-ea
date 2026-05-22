---
id: usage-vi
title: Hướng dẫn sử dụng vibecodekit-mql5-ea v1.0.1 (Tiếng Việt)
applicable_phase: E
audience: end_user, dev_team
---

# Hướng dẫn sử dụng `vibecodekit-mql5-ea` v1.0.1

Tài liệu này hướng dẫn từng bước cách dùng toàn bộ 50 lệnh để build một
Expert Advisor MQL5 hoàn chỉnh, từ ý tưởng đến ship live. Phù hợp cho cả
người mới và dev team.

> 📚 Phiên bản tiếng Anh: [USAGE-en.md](USAGE-en.md)
> 🛠️ Tích hợp IDE / CLI (Devin, Codex, Claude Code, Cursor, …): [ENV-SETUP-vi.md](ENV-SETUP-vi.md)
> 💬 Build theo prompt (chat → spec → pipeline): [devin-chat-driven-build.md](devin-chat-driven-build.md)

## Mục lục

1. [Cài đặt môi trường](#1-cài-đặt-môi-trường)
2. [Triết lý: 8 bước build EA](#2-triết-lý-8-bước-build-ea)
3. [Lệnh theo từng giai đoạn](#3-lệnh-theo-từng-giai-đoạn)
4. [Ví dụ hoàn chỉnh: MACD+SAR EURUSD H1](#4-ví-dụ-hoàn-chỉnh-macdsar-eurusd-h1)
5. [Tích hợp 4 MCP server](#5-tích-hợp-4-mcp-server)
6. [23 anti-pattern detector](#6-23-anti-pattern-detector)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Cài đặt môi trường

### 1.1. Yêu cầu

| Thành phần | Phiên bản |
|-----------|-----------|
| Python | ≥ 3.10 |
| Wine | 8.0.2 (Linux/macOS) — MetaEditor là native trên Windows |
| MetaEditor | build ≥ 5260 (để method-hiding linter ở mức ERROR thay vì WARN) |
| ONNX runtime | 1.14 (Phase D ONNX e2e) |
| Xvfb | tuỳ — cần nếu chạy headless trên CI Linux |

### 1.2. Linux (Ubuntu 22.04+)

```bash
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea

# Cài Wine + MetaEditor headless qua wineboot (~3 phút)
./scripts/setup-wine-metaeditor.sh

# Tạo venv riêng cho kit
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Health check — mọi probe phải là ok: true
python -m vibecodekit_mql5.doctor
```

### 1.3. macOS

Wine trên macOS chạy được nhưng MetaQuotes không support chính thức.
Khuyến nghị dùng Devin VM hoặc Linux VM. Nếu vẫn muốn local:

```bash
brew install --cask wine-stable
# Sau đó các bước giống Linux
```

### 1.4. Windows

MetaEditor là native nên không cần Wine. Dùng PowerShell:

```powershell
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m vibecodekit_mql5.doctor
```

> ⚠️ Một số script `setup-wine-metaeditor.sh` là bash-only — trên Windows
> chỉ cần chỉ định path MetaEditor qua env var `METAEDITOR_BIN` rồi bỏ
> qua bước Wine.

---

## 2. Triết lý: 8 bước build EA

Plan v5 chia toàn bộ vòng đời EA thành 8 bước. Mỗi bước có template
markdown trong `docs/rri-templates/` và lệnh chuyên dụng để mở nó:

| Bước | Tên | Lệnh mở template | Output |
|------|-----|------------------|--------|
| 1 | **SCAN** | `python -m vibecodekit_mql5.scan <thư mục>` | Liệt kê tree project |
| 2 | **RRI** (Research / Risk / Robustness) | `python -m vibecodekit_mql5.rri --mode {personal,team,enterprise}` | `docs/rri-report.md` |
| 3 | **VISION** | `python -m vibecodekit_mql5.vision` | `docs/vision.md` |
| 4 | **BLUEPRINT** | `python -m vibecodekit_mql5.blueprint` | `docs/blueprint.md` |
| 5 | **TIP** (8 Technical Implementation Points) | `python -m vibecodekit_mql5.tip` | `docs/tip.md` |
| 6 | **BUILD** | `python -m vibecodekit_mql5.build <archetype>` hoặc `wizard`, `async-build` | Mã `.mq5` từ scaffold |
| 7 | **VERIFY** | 10 lệnh từ `compile` → `multibroker` | XML report + ma trận 64 ô |
| 8 | **REFINE + SHIP** | `python -m vibecodekit_mql5.refine` + `ship` | Tag git + push |

### Phân loại 3 mode

| Mode | Số câu RRI | Lớp permission chạy | Đối tượng |
|------|----------|---------------------|----------|
| `personal` | 5 q/persona × 6 = 30 | 1, 2, 3, 4, 7 | Solo trader |
| `team` | 12 q/persona × 6 = 72 | 1-5, 7 | Team 2-5 dev |
| `enterprise` | 25 q/persona × 6 = 150 | 1-7 (đầy đủ) | Tổ chức / quỹ |

---

## 3. Lệnh theo từng giai đoạn

### 3.1. Discovery (4 lệnh)

```bash
# Quét cây thư mục project, phân loại artefact
python -m vibecodekit_mql5.scan ~/projects/eurusd-portfolio

# Match mô tả tự do → scaffold archetype
python -m vibecodekit_mql5.survey "MA cross strategy H1 trend following"
# → primary: trend, variant: netting

# Health check môi trường kit
python -m vibecodekit_mql5.doctor

# Chạy 70-test conformance battery
python -m vibecodekit_mql5.audit
```

### 3.2. Plan — mở template (4 lệnh)

```bash
python -m vibecodekit_mql5.rri --mode team    # mở rri-template + chấm điểm
python -m vibecodekit_mql5.vision             # mở step-3-vision template
python -m vibecodekit_mql5.blueprint          # mở step-4-blueprint
python -m vibecodekit_mql5.tip                # mở step-5-tip (8 TIP)
```

### 3.3. Build (12 lệnh)

```bash
# 1. Render scaffold tổng quát — chọn archetype + variant
python -m vibecodekit_mql5.build stdlib --name MyEA --symbol EURUSD --tf H1
# Archetype có sẵn: stdlib, trend, mean-reversion, breakout, scalping,
# hedging-multi, news-trading, arbitrage-stat, library, indicator-only,
# grid, dca, portfolio-basket, wizard-composable, hft-async, ml-onnx,
# service-llm-bridge

# 2. Wizard composable (CExpert + signal + trailing + money-mgmt)
python -m vibecodekit_mql5.wizard --name MyWizardEA --symbol EURUSD --tf H1

# 3. HFT async — OrderSendAsync + OnTradeTransaction handler
python -m vibecodekit_mql5.async_build --name MyHftEA --symbol EURUSD --tf M1

# 4. Patch EA hiện có dùng CPipNormalizer
python -m vibecodekit_mql5.pip_normalize MyEA.mq5

# 5. Export PyTorch / TF → ONNX (opset ≥ 14)
python -m vibecodekit_mql5.onnx_export model.pt --output model.onnx --opset 14

# 6. Embed file .onnx vào .mq5 qua #resource + COnnxLoader
python -m vibecodekit_mql5.onnx_embed MyEA.mq5 --model model.onnx

# 7. Wire LLM bridge vào EA hiện có
python -m vibecodekit_mql5.llm_context MyEA.mq5 --pattern cloud-api
# Pattern: cloud-api | self-hosted-ollama | embedded-onnx-llm

# 8. Khởi tạo repo trên Algo Forge
python -m vibecodekit_mql5.forge_init MyEA
```

#### 3.3a. Pipeline auto-build 1 lệnh

4 CLI dưới đây lấp khoảng trống giữa "tôi muốn EA làm X" và PR
xanh CI. Mỗi lệnh deterministic, chỉ dùng regex (không gọi LLM), output
JSON hoặc YAML để feed sang stage kế tiếp.

```bash
# Free-text → ea-spec.yaml hợp lệ (--explain để xem field nào suy ra từ
# prompt, field nào lấy default; --strict để fail nếu thiếu).
mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5% macd or sar" \
    --out ea-spec.yaml --explain

# Pipeline 1-lệnh: scan → build → lint → compile → permission-gate →
# dashboard. Ghi auto-build-report.json (idempotent).
mql5-auto-build --spec ea-spec.yaml --out-dir build/MyEA

# Áp transformer loop 8 AP nghiêm trọng cho file .mq5 cũ
# (AP-1, 3, 5, 15, 17, 18, 20, 21). Re-lint sau mỗi pass.
mql5-auto-fix MyEA.mq5

# Render + (tuỳ chọn) publish ma trận chất lượng 64 ô ra HTML.
# Đọc MQL5_DASHBOARD_PUBLISH_CMD hoặc --publish-cmd; fallback file://.
mql5-dashboard --metrics metrics.json --out quality-matrix.html
```

Các flag cần nhớ:

* `mql5-auto-build --no-compile` — bỏ qua stage Wine + MetaEditor (hữu ích
  khi CI không có Wine hoặc chỉ muốn chạy lint/gate).
* `mql5-auto-build --no-gate` — bỏ qua orchestrator 7 lớp.
* `mql5-auto-build --force` — render lại scaffold ngay cả khi `out_dir`
  đã có file.
* `mql5-auto-build --publish-cmd <cmd>` — override hook publish
  dashboard cho lần chạy đó.

Schema của `ea-spec.yaml` (risk / signals / filters / hooks / stack
overrides) nằm ở `scripts/vibecodekit_mql5/spec_schema.py`. Bảng
recogniser của `mql5-spec-from-prompt` có ở
[`devin-chat-driven-build.md`](devin-chat-driven-build.md#what-the-parser-understands).

### 3.4. Verify (12 lệnh)

```bash
# 1. Compile qua MetaEditor (Wine trên Linux)
python -m vibecodekit_mql5.compile MyEA.mq5

# 2. Lint 8 anti-pattern nghiêm trọng (ERROR-level, block ship)
python -m vibecodekit_mql5.lint MyEA.mq5

# 3. Method-hiding linter (build ≥ 5260 → ERROR; build < 5260 → WARN)
python -m vibecodekit_mql5.method_hiding_check MyEA.mq5 --build 5260

# 4. Parse Strategy Tester XML report → 14 canonical metrics JSON
#    Chạy MetaEditor backtest tay trước, lưu XML, rồi parse:
python -m vibecodekit_mql5.backtest MyEA.ex5 inputs.set \
    --period H1 --symbol EURUSD --report tester.xml > metrics.json

# 4b. Chạy Strategy Tester end-to-end (drive terminal64.exe qua Wine
#     + parse XML). Cần $MQL5_TERMINAL_PATH (export bởi
#     scripts/setup-wine-metaeditor.sh).
python -m vibecodekit_mql5.tester_run MyEA.ex5 \
    --symbol EURUSD --period H1 --from 2024-01-01 --to 2024-06-01 \
    --out tester.xml > metrics.json

# 4c. Chạy optimization end-to-end (drive terminal64.exe + parse opt XML
#     → top-N parameter set). File .set phải có flag optimize=true kèm
#     start/step/stop; mql5-optimize-run không tự sinh range.
python -m vibecodekit_mql5.optimize_run MyEA.ex5 default.set \
    --symbol EURUSD --period 2024.01.01-2024.12.31 --tf H1 \
    --mode genetic --criterion sharpe-max --top 10 > top-sets.json

# CI / hermetic: parse opt XML có sẵn, không launch MT5
python -m vibecodekit_mql5.optimize_run MyEA.ex5 default.set \
    --period 2024.01.01-2024.12.31 \
    --from-xml /path/to/opt-results.xml --criterion sharpe-max

# 5. Walk-forward IS/OOS (cần 2 XML report đã chạy IS và OOS riêng)
python -m vibecodekit_mql5.walkforward is.xml oos.xml > walkforward.json

# 6. Monte-Carlo bootstrap DD (CSV 1 return / dòng, có header tuỳ chọn)
python -m vibecodekit_mql5.monte_carlo returns.csv \
    --reported-dd 5.4 --n-sims 1000 --seed 42 > montecarlo.json

# 7. Overfit check (Sharpe OOS/IS sanity)
python -m vibecodekit_mql5.overfit_check is.xml oos.xml > overfit.json

# 8. Multi-broker stability (3 XML report tách dấu phẩy)
python -m vibecodekit_mql5.multibroker \
    --reports brokerA.xml,brokerB.xml,brokerC.xml

# 9. Custom fitness emitter (positional; bỏ trống để list 5 template)
python -m vibecodekit_mql5.fitness sharpe > OnTester.mq5

# 10. MFE/MAE per-trade analyser (CSV 8 cột: deal_id,open_time,
#     close_time,magic,type,profit,mfe,mae — emit từ CMfeMaeLogger.mqh)
python -m vibecodekit_mql5.mfe_mae mfe.csv
```

> **Lưu ý:** `mql5-backtest`, `mql5-walkforward`, `mql5-overfit_check`,
> `mql5-multibroker` chỉ **parse** XML report — KHÔNG tự chạy Strategy
> Tester. Bạn vẫn phải chạy backtest qua MetaTrader 5 (hoặc tự automate
> bằng `terminal64.exe /config:tester.ini`), lưu HTML/XML report, rồi
> feed vào các lệnh này. Lệnh `cloud_optimize` chỉ sinh `tester.ini` cho
> bạn copy lên Cloud Network của MetaQuotes.

> **CSV schema cho `mfe_mae`** — cột bắt buộc đúng thứ tự:
> `deal_id,open_time,close_time,magic,type,profit,mfe,mae` (xuất từ
> `CMfeMaeLogger.SaveToCsv()`; xem `Include/CMfeMaeLogger.mqh`).

### 3.5. RRI methodology (3 lệnh review chuyên dụng)

```bash
# Backtest review — 5 persona × 7 dim × 8 axis (yêu cầu JSON metrics
# từ `mql5-backtest`)
python -m vibecodekit_mql5.rri.rri_bt \
    --metrics metrics.json --mode enterprise --output rri-bt.html

# Risk & Robustness review (cần 4 JSON: trader-check, walkforward,
# monte-carlo, overfit)
python -m vibecodekit_mql5.rri.rri_rr \
    --trader-check trader-check.json \
    --walkforward  walkforward.json \
    --monte-carlo  montecarlo.json \
    --overfit      overfit.json \
    --mode personal --output rri-rr.html

# Indicator-dev RRI (chỉ áp dụng cho strategy indicator-only)
python -m vibecodekit_mql5.rri.rri_chart \
    --metrics metrics.json --mode personal --output rri-chart.html
```

### 3.6. Review opener (5 lệnh)

5 lệnh này mở template markdown để bạn (hoặc reviewer) điền:

```bash
python -m vibecodekit_mql5.review.review       # review tổng quát
python -m vibecodekit_mql5.review.eng_review   # engineering review
python -m vibecodekit_mql5.review.ceo_review   # leadership / CEO review
python -m vibecodekit_mql5.review.cso          # strategy review
python -m vibecodekit_mql5.review.investigate  # incident investigation
```

### 3.7. Deploy (3 lệnh)

```bash
# Sinh checklist MIGRATE-VPS.md cho VPS deployment
python -m vibecodekit_mql5.deploy_vps MyEA --out MIGRATE-VPS.md --mode personal

# Sinh tester.ini cho MetaQuotes Cloud Network optimization
# Mode PERSONAL bị reject (quá đắt); team/enterprise phải có budget cap
python -m vibecodekit_mql5.cloud_optimize MyEA \
    --symbol EURUSD --period H1 --passes 1000 --budget-usd 50 \
    --mode enterprise --output-ini tester.ini

# Canary live monitor 30 phút sau deploy
# Đọc journal MT5 qua mt5-bridge MCP; alert nếu error_rate > 1/min,
# slippage_p95 > 1 pip, hoặc DD > 5%
# (Có thể dùng --journal <file.log> thay vì poll real-time.)
python -m vibecodekit_mql5.canary MyEA.ex5 --duration 30m
```

### 3.8. Ship (4 lệnh)

```bash
# Push PR sang Algo Forge
python -m vibecodekit_mql5.forge_pr feature-branch --target main

# Đóng gói output của mql5-auto-build thành manifest + ship.zip
python -m vibecodekit_mql5.package --out-dir ./dist --spec ea-spec.yaml
# Hoặc bật trực tiếp trong pipeline build (chỉ chạy khi build xanh):
python -m vibecodekit_mql5.auto_build --spec ea-spec.yaml --out-dir ./dist --package

# Git tag + push (dry-run trước cho an toàn)
python -m vibecodekit_mql5.ship --tag v1.0.1 --dry-run
python -m vibecodekit_mql5.ship --tag v1.0.1

# Phân loại diff thành tweak / patch / rework
python -m vibecodekit_mql5.refine --diff change.patch
# Output: { "classification": "tweak", "files_touched": ["set.set"], ... }
```

**Nội dung file ship `.zip`.** `mql5-package` (và
`mql5-auto-build --package`) duyệt `--out-dir`, phân loại file qua
`scripts/vibecodekit_mql5/package.py::classify_artifact`, ghi
`manifest.json` (SHA-256 + group index) rồi đóng gói thành
`<out-dir>/<name>-ship.zip`. Các nhóm trong gói:

| Group     | File                                                                | Mục đích                                                       |
|-----------|---------------------------------------------------------------------|----------------------------------------------------------------|
| `runtime` | `*.ex5`, `Sets/*.set`                                               | Copy vào MT5 để chạy EA / Strategy Tester preset               |
| `source`  | `*.mq5`, `*.mqh`, `README.md` của scaffold                          | Recompile, audit source, review scaffold                       |
| `review`  | `auto-build-report.json`, `quality-matrix.html`, `*.docs.*`, `*.log` | Verdict build / lint / compile / gate + tài liệu EA (`.docs.html` / `.docs.md` chứa **Chi tiết từng tham số** + **Cách EA chạy** narrative) |
| `repro`   | `*spec*.yaml/yml/json`, `*.onnx`, `*.csv`                           | Tái tạo build từ spec + side-input ML / dataset                |
| _(root)_  | `manifest.json`                                                     | SHA-256 inventory + group index của toàn bộ zip                |

File ngoài bảng phân loại (`.txt` rời, file IDE, chính file `.zip`,
`manifest.json` cũ) bị bỏ qua. Bản `auto-build-report.json` trong zip
là snapshot build-side (build / lint / compile / gate / docs /
dashboard); bản trên disk được ghi lại sau bước package nên có thêm
`report.package.ok` + `report.package.groups` để CI grep được.

### 3.9. Other (4 lệnh)

```bash
# Verify pip-norm + multi-broker
python -m vibecodekit_mql5.broker_safety MyEA.mq5

# Trader-17 checklist (17 mục, pass threshold 15/17)
python -m vibecodekit_mql5.trader_check MyEA.mq5

# Reconcile-install kit overlay vào project có sẵn
python -m vibecodekit_mql5.install ~/existing-mt5-project

# One-shot lint + Trader-17 second opinion (optional)
python -m vibecodekit_mql5.second_opinion MyEA.mq5
```

---

## 4. Ví dụ hoàn chỉnh: MACD+SAR EURUSD H1

Worked example đầy đủ ở `examples/ea-wizard-macd-sar-eurusd-h1-portfolio/`.
Đây là turnaround **4 tiếng ở chế độ enterprise** trên Devin VM.

### Bước 1 — SCAN (5 phút)
```bash
python -m vibecodekit_mql5.scan ~/projects/eurusd-portfolio
# Kết quả: cây trống
```

### Bước 2 — RRI (90 phút, enterprise)
```bash
python -m vibecodekit_mql5.rri.step_workflow --mode enterprise
# 6 persona × 25 câu = 150 câu hỏi
# Output: docs/rri-report.md
```

### Bước 3 — VISION (15 phút)
Mở template `docs/rri-templates/step-3-vision.md.tmpl` và điền:
- Hypothesis: MACD signal cross gated by Parabolic-SAR flip
- Scope: EURUSD H1 netting account
- Out of scope: hedging, multi-symbol, news filter

### Bước 4 — BLUEPRINT (30 phút)
Mở `step-4-blueprint.md.tmpl`. Quyết định:
- Archetype: `wizard-composable/netting`
- Includes cần dùng: `CPipNormalizer`, `CRiskGuard`, `CMagicRegistry`, `CMfeMaeLogger`
- Magic number: 5001

### Bước 5 — TIP (8 TIP, ~30 phút)
8 Technical Implementation Points — chi tiết về SL/TP, risk per trade,
filter, trailing, kill switch, slippage limit, news blackout, weekly DD cap.

### Bước 6 — BUILD (10 phút)
```bash
python -m vibecodekit_mql5.wizard \
    --name EAMacdSarPortfolio \
    --symbol EURUSD --tf H1 \
    --output ~/projects/eurusd-portfolio
```

### Bước 7 — VERIFY (multi-stage, ~60 phút)
```bash
# Code-quality (chạy ngay, không cần XML report)
python -m vibecodekit_mql5.compile             EAMacdSarPortfolio.mq5
python -m vibecodekit_mql5.lint                EAMacdSarPortfolio.mq5
python -m vibecodekit_mql5.method_hiding_check EAMacdSarPortfolio.mq5

# Chạy Strategy Tester (manual / qua MT5 GUI), thu XML report sau đó:
python -m vibecodekit_mql5.backtest      EAMacdSarPortfolio.ex5 default.set \
    --period H1 --symbol EURUSD --report tester.xml > metrics.json
python -m vibecodekit_mql5.walkforward   is.xml oos.xml      > walkforward.json
python -m vibecodekit_mql5.monte_carlo   returns.csv --reported-dd 5.4 \
                                         --n-sims 1000        > montecarlo.json
python -m vibecodekit_mql5.overfit_check is.xml oos.xml      > overfit.json
python -m vibecodekit_mql5.multibroker   --reports a.xml,b.xml,c.xml
python -m vibecodekit_mql5.trader_check  EAMacdSarPortfolio.mq5 > trader-check.json

# Quality matrix + RRI review
python -m vibecodekit_mql5.rri.rri_bt    --metrics metrics.json \
                                         --mode enterprise --output rri-bt.html
python -m vibecodekit_mql5.rri.rri_rr    --trader-check trader-check.json \
    --walkforward walkforward.json --monte-carlo montecarlo.json \
    --overfit overfit.json --mode enterprise --output rri-rr.html
```

### Bước 8 — REFINE + SHIP (~10 phút)
```bash
python -m vibecodekit_mql5.refine --diff change.patch
python -m vibecodekit_mql5.ship --tag v1.0.0 --dry-run
python -m vibecodekit_mql5.ship --tag v1.0.0
```

Kết quả: EA `EAMacdSarPortfolio.ex5` + `.set` file + ma trận 64 ô +
backtest XML + MFE/MAE report + canary log — đầy đủ 5 artefact ở
`examples/ea-wizard-macd-sar-eurusd-h1-portfolio/results/`.

---

## 5. Tích hợp 4 MCP server

Kit ship 4 MCP server theo chuẩn JSON-RPC 2.0 over stdio. Dùng được
từ bất kỳ MCP client nào (Claude Desktop, Cursor, Codex, Devin, …).

### 5.1. metaeditor-bridge

3 tool: `metaeditor.compile`, `metaeditor.parse_log`, `metaeditor.includes_resolve`

Khởi động:
```bash
python mcp/metaeditor-bridge/server.py
```

### 5.2. mt5-bridge (READ-ONLY)

10 tool **chỉ-đọc** (KHÔNG có `order_send`, `order_close`, hay
`position_modify` — được enforce bằng test `test_mt5_bridge_readonly_no_trade`):

- `mt5.symbols.list`, `mt5.symbol.info`
- `mt5.rates.copy`, `mt5.tick.last`
- `mt5.account.info`, `mt5.terminal.info`
- `mt5.positions.list`, `mt5.positions.history`
- `mt5.history.deals`, `mt5.market.book`

Khởi động:
```bash
python mcp/mt5-bridge/server.py
```

> ⚠️ **Lưu ý platform:** package `MetaTrader5` chỉ cài được trên
> **Windows** (hoặc Wine MT5 desktop qua `winetricks`). Trên Linux VM
> thuần, import fail và mọi tool trả **stub payload** cố định
> (symbol list rỗng, 0 bar, `digits=5, point=0.00001` hardcoded cho
> `mt5.symbol.info`). Stub giữ MCP contract test hermetic được nhưng
> **không phải data thật**. Để có market/account data live, chạy
> server này trên Windows hoặc Wine MT5.

### 5.3. algo-forge-bridge

6 tool: `forge.init`, `forge.clone`, `forge.commit`, `forge.pr.create`,
`forge.pr.list`, `forge.repo.list`. Cần `ALGO_FORGE_API_KEY` env var.

Khởi động:
```bash
ALGO_FORGE_API_KEY=xxx python mcp/algo-forge-bridge/server.py
```

### 5.4. vibecodekit-bridge

29 tool qua 6 PR. Cho phép AI coding agent (Codex CLI / Claude Code /
Cursor / Devin / Claude Desktop) gọi thẳng vào pipeline `prompt → spec
→ build → verify → review → ship` qua JSON-RPC. Wire format ổn định
giữa các PR — PR sau chỉ mở rộng `DISPATCH`.

**PR-1 (prompt → spec → build → permission gate):**
`spec.from_prompt`, `spec.validate`, `build.auto`, `verify.permission`.

**PR-2 (static-analysis verify suite):** `verify.lint` (8 AP critical),
`verify.lint_best_practice` (17 AP WARN), `verify.method_hiding`,
`verify.trader17`, `verify.compile`, `verify.broker_safety`,
`verify.audit`.

**PR-3 (runtime / statistical verify suite):** `verify.backtest`
(parser XML report của MT5 tester), `verify.walkforward` (tương quan
Sharpe OOS/IS + verdict), `verify.montecarlo` (stress test DD theo
bootstrap), `verify.multibroker` (ổn định N-broker: PF CV / Sharpe
stdev / DD diff), `verify.fitness` (tra cứu template `OnTester()`),
`verify.mfe_mae` (thống kê excursion từ CSV), `verify.overfit` (verdict
Sharpe IS/OOS — không cần XML).

**PR-4 (review / RRI suite):** `review.eng` (broker-engineer + devops),
`review.cso` (risk-auditor), `review.ceo` (trader + strategy-architect),
`review.investigate` (perf-analyst + strategy-architect), và
`rri.persona` (generic 1-persona x 1-step x 1-mode). Mỗi tool trả về
markdown sẵn sàng dán vào PR description hoặc file `review.md`.

**PR-5 (ship-stage tools):** `dashboard.publish` render dashboard
quality-matrix 64 cell từ pipeline digest và publish qua command tùy
chọn (fallback `file://` URI khi không cấu hình command). `forge.pr.create`
mở PR trên MQL5 Algo Forge — gọi HTTP thật khi có `MQL5_FORGE_TOKEN`,
không thì trả về dry-run payload (kèm `endpoint` + `planned_payload`).
Chain hai tool này để nhúng URL dashboard public vào body của Forge PR.

**Schema `ea-spec.yaml` mở rộng (PR-2 + PR-8):** thêm 8 block optional,
full back-compat. PR-2 cho 3 block đầu — `prop_firm` (DD limits + news
block + weekend-flat cho FTMO/MFF), `time_exit` (close on Friday, max
trade hours, session windows), `stealth` (random slippage / comment
pool / lot jitter, split orders). PR-8 thêm 5 block: `trailing`
(trailing-stop kiểu fixed / ATR / parabolic), `partial_close` (scale-
out nhiều mức + move-SL-về-breakeven sau mức đầu), `correlation` (max
vị thế correlated, ngưỡng Pearson, symbol group, block-on-correlated-
loss), `swap_filter` (giới hạn swap pip/ngày theo hướng, skip thứ tư
triple-swap), `logs` (level, file pattern, terminal output, redact số
tài khoản). Spec cũ không có các block này vẫn validate như cũ.

**PR-7 (discovery / fix-loop helpers):** `discover.doctor` chạy
doctor của kit (Python / Wine / MetaEditor / module + scaffold bắt
buộc), `discover.scan` quét workspace và phân loại theo extension
(`.mq5` → ea-source, `.mqh` → include, `.set` → tester-set, `.ex5`
→ compiled, `.onnx` → onnx-model), `discover.llm_context` wire 1
trong 3 LLM-bridge scaffold pattern (`cloud-api` / `self-hosted-
ollama` / `embedded-onnx-llm`) vào EA `.mq5` có sẵn, và
`verify.auto_fix` chạy AP auto-fixer trên file (rewrite in-place)
hoặc trên source string in-memory. Pair `verify.lint` ↔
`verify.auto_fix` để đóng fix-loop cho agent mà không cần rời
bridge.

```bash
python mcp/vibecodekit-bridge/server.py
```

Wire format ổn định từ PR-1 → PR-5 → PR-7 → PR-8 và các PR sau
(PR-8 chỉ thêm field vào schema spec, không đụng surface bridge).


### 5.5. Cấu hình MCP client

Xem [docs/ENV-SETUP-vi.md](ENV-SETUP-vi.md) cho cấu hình cụ thể từng
IDE/CLI (Claude Desktop, Cursor, Codex, Devin).

---

## 6. 23 anti-pattern detector

Lint chia 2 cấp:

### 6.1. Critical APs — ERROR, block ship (8)

| ID | Mô tả | Detector ở đâu |
|----|------|----------------|
| AP-1 | `OrderSend` không có SL | `scripts/vibecodekit_mql5/lint.py` |
| AP-3 | Lot cố định, không risk-based | `lint.py` |
| AP-5 | EA overfit (in-sample only, không OOS) | `lint.py` |
| AP-15 | `OrderSend` thô, không qua `CTrade` | `lint.py` |
| AP-17 | `WebRequest` gọi trong `OnTick` | `lint.py` |
| AP-18 | `OrderSendAsync` thiếu `OnTradeTransaction` handler | `lint.py` |
| AP-20 | Hardcode pip (`* 0.0001`, `* _Point`) | `lint.py` |
| AP-21 | JPY/XAU digits broken (`digits-tested:` < 2 class) | `lint.py` |

### 6.2. Best-practice APs — WARN, không block (14)

| ID | Mô tả | Detector |
|----|------|---------|
| AP-2 | SL quá chặt | `lint_best_practice.py` |
| AP-4 | Martingale không có cap | `lint_best_practice.py` |
| AP-6 | Curve-fitted optimization | `lint_best_practice.py` |
| AP-7 | Magic number hardcode | `lint_best_practice.py` |
| AP-8 | Không có spread guard | `lint_best_practice.py` |
| AP-9 | Multi-entry trên cùng bar | `lint_best_practice.py` |
| AP-10 | `OrderSend` không check return | `lint_best_practice.py` |
| AP-11 | EA blind về mode (netting vs hedging) | `lint_best_practice.py` |
| AP-12 | Leak indicator handle (không release) | `lint_best_practice.py` |
| AP-13 | EA broker-coupled (`SymbolInfoDouble` hardcode) | `lint_best_practice.py` |
| AP-14 | Không log MFE/MAE | `lint_best_practice.py` |
| AP-16 | Reinvent stdlib (tự code thay vì `CTrade`) | `lint_best_practice.py` |
| AP-19 | ONNX không validate trên Strategy Tester | `lint_best_practice.py` |
| AP-22 | `OnTick` không đặt lệnh (signal placeholder) | `lint_best_practice.py` |
| AP-23 | `CTrade.Buy/Sell` không check return/retcode | `lint_best_practice.py` |
| AP-24 | Đọc history/chỉ báo khi chưa có sync guard | `lint_best_practice.py` |
| AP-25 | `delete` thô không có pointer guard | `lint_best_practice.py` |

### 6.3. Method-hiding (1, build-aware)

Build MetaEditor ≥ 5260 báo ERROR khi subclass `CExpert` có method
trùng tên với base class mà thiếu `using BaseClass::method;`. Build
< 5260 chỉ WARN.

```bash
python -m vibecodekit_mql5.method_hiding_check MyEA.mq5 --build 5260
```

---

## 7. Troubleshooting

### "wine: command not found"
- Linux: `./scripts/setup-wine-metaeditor.sh` chưa chạy thành công.
- macOS: `brew install --cask wine-stable`.
- Windows: không cần Wine — đặt `METAEDITOR_BIN=C:\Path\To\metaeditor64.exe`.

### `python -m vibecodekit_mql5.doctor` báo "metaeditor-bin: not found"
- Đặt biến môi trường `METAEDITOR_BIN`:
  ```bash
  export METAEDITOR_BIN=~/.wine/drive_c/Program\ Files/MetaTrader\ 5/metaeditor64.exe
  ```

### `doctor --soft` cho CI chỉ chạy docs / lint (không có Wine)
Các probe Wine / MetaEditor / terminal chuyển thành cảnh báo thay vì lỗi, để
CI không có Wine vẫn exit 0. Các check bắt buộc (Python ≥ 3.10, import kit
package, `docs/references/`, scaffold archetypes) vẫn flip gate như cũ.
```bash
python -m vibecodekit_mql5.doctor --soft
# JSON output có thêm "soft": true và "strict_ok": <ok không lọc>
# rc == 0 khi chỉ có probe optional wine/MT5 fail; rc == 1 nếu bất kỳ
# check bắt buộc nào fail.
```

### Test ONNX e2e fail vì PyTorch không cài
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install onnx onnxscript
```

### `audit-plan-v5.py --post-phase=E` báo missing scaffold
- Chạy `git status` xem có file scaffold nào untracked không.
- Kiểm tra `.gitignore` không loại nhầm artefact:
  ```bash
  git check-ignore -v examples/**/results/canary.log
  ```

### MCP server `mt5-bridge` báo "MetaTrader5 not installed"
```bash
pip install MetaTrader5  # chỉ chạy được trên Windows hoặc Wine với MT5 desktop
```

### `forge_init` báo 401 Unauthorized
- Đặt `ALGO_FORGE_API_KEY` qua secrets manager hoặc env var:
  ```bash
  export ALGO_FORGE_API_KEY=your_key_here
  ```

### "Linguist phân loại repo là MQL4 thay vì MQL5"
- Đã fix ở `.gitattributes` (PR #17). Nếu vẫn thấy MQL4 trên GitHub
  language bar, đợi 10 phút sau commit để GitHub re-run Linguist.

---

## Tài nguyên bổ sung

- [`docs/COMMANDS.md`](COMMANDS.md) — Bảng tra cứu 43 lệnh
- [`docs/references/`](references/) — 28 cheatsheet kỹ thuật (50-survey → 79-pip-norm)
- [`docs/PLAN-v5.md`](PLAN-v5.md) — Spec gốc 1089 dòng
- [`docs/anti-patterns-AVOID.md`](anti-patterns-AVOID.md) — Anti-pattern phải tránh từ VCK-HU
- [`docs/rri-personas/`](rri-personas/) — 6 file YAML × 25 câu hỏi
- [`docs/rri-templates/`](rri-templates/) — 8 template markdown step-by-step
- [`examples/ea-wizard-macd-sar-eurusd-h1-portfolio/`](../examples/ea-wizard-macd-sar-eurusd-h1-portfolio/) — Worked example 4 tiếng

Câu hỏi / báo lỗi → mở issue trên
https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea/issues
