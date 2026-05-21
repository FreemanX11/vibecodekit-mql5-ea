---
id: user-guide-vi
title: Hướng dẫn sử dụng vibecodekit-mql5-ea — Step-by-Step Build EA
applicable_phase: E
audience: end_user, dev_team, ai_agent_operator
---

# Hướng dẫn step-by-step build project EA bằng `vibecodekit-mql5-ea`

> Tài liệu này đi từ **zero → file `.ex5` đã compile + dashboard public +
> docs Neo-Retro Dev Deck tiếng Việt** qua đúng từng bước, kèm câu lệnh
> thật và snippet output kỳ vọng. Mọi con số trong tài liệu đều khớp với
> baseline mới nhất sau PR-19: **50 CLI command**, **4 MCP server (30
> tool trên `vibecodekit-bridge`)**, **23 anti-pattern detector**, **8
> schema block optional** trên `ea-spec.yaml`, **799 test passing / 2
> skipped**.

> 🇬🇧 Bản tiếng Anh: [USER-GUIDE-en.md](USER-GUIDE-en.md)
> 📖 Reference manual đầy đủ: [USAGE-vi.md](USAGE-vi.md)
> 🔧 Setup môi trường + tích hợp IDE/CLI: [ENV-SETUP-vi.md](ENV-SETUP-vi.md)
> 💬 Build theo prompt: [devin-chat-driven-build.md](devin-chat-driven-build.md)

---

## Mục lục

- [0. TL;DR — đường ngắn nhất](#0-tldr--đường-ngắn-nhất)
- [1. Chuẩn bị môi trường](#1-chuẩn-bị-môi-trường)
- [2. Health check `mql5-doctor`](#2-health-check-mql5-doctor)
- [3. Chọn 1 trong 2 lối đi](#3-chọn-1-trong-2-lối-đi)
- [4. Lối A — CLI thủ công, 7 bước](#4-lối-a--cli-thủ-công-7-bước)
  - [4.1. Từ ý tưởng → `ea-spec.yaml`](#41-từ-ý-tưởng--ea-specyaml)
  - [4.2. Validate spec (8 block)](#42-validate-spec-8-block)
  - [4.3. Build EA bằng `mql5-auto-build`](#43-build-ea-bằng-mql5-auto-build)
  - [4.3.1. EA docs auto-generation (Neo-Retro Dev Deck)](#431-ea-docs-auto-generation-neo-retro-dev-deck)
  - [4.4. Verify — lint, method-hiding, trader17, permission](#44-verify--lint-method-hiding-trader17-permission)
  - [4.5. Test — backtest, walkforward, Monte Carlo](#45-test--backtest-walkforward-monte-carlo)
  - [4.6. Review — engineering, CSO, CEO, RRI](#46-review--engineering-cso-ceo-rri)
  - [4.7. Ship — dashboard + Algo Forge PR](#47-ship--dashboard--algo-forge-pr)
- [5. Lối B — AI coding agent qua MCP bridge](#5-lối-b--ai-coding-agent-qua-mcp-bridge)
  - [5.1. Cài `vibecodekit-bridge` vào tool](#51-cài-vibecodekit-bridge-vào-tool)
  - [5.2. Prompt mẫu cho agent](#52-prompt-mẫu-cho-agent)
  - [5.3. Fix-loop `verify.lint` ↔ `verify.auto_fix`](#53-fix-loop-verifylint--verifyauto_fix)
  - [5.4. Re-render docs qua `docs.ea_render`](#54-re-render-docs-qua-docsea_render)
- [6. Schema `ea-spec.yaml` — 8 block optional](#6-schema-ea-specyaml--8-block-optional)
- [7. Troubleshooting & FAQ](#7-troubleshooting--faq)
- [8. Phụ lục — 50 CLI command theo nhóm](#8-phụ-lục--50-cli-command-theo-nhóm)

---

## 0. TL;DR — đường ngắn nhất

5 lệnh là ra `.ex5`. Phần còn lại của tài liệu là giải thích từng dòng.

```bash
# (1) Setup 1 lần
./scripts/setup-wine-metaeditor.sh && python -m venv .venv && \
    source .venv/bin/activate && pip install -e .

# (2) Health check
python -m vibecodekit_mql5.doctor

# (3) Free-text → ea-spec.yaml
python -m vibecodekit_mql5.spec_from_prompt \
    "EA trend EURUSD H1 MACD + EMA cross, risk 0.5%, SL 30 TP 60, prop firm FTMO" \
    --out ea-spec.yaml

# (4) Build + lint + compile + permission gate + dashboard, một lệnh
python -m vibecodekit_mql5.auto_build --spec ea-spec.yaml \
    --out ./dist --mode personal

# (5) Trader-17 + RRI sanity check trước khi backtest
python -m vibecodekit_mql5.trader_check ./dist/MyEA.mq5
```

Sản phẩm:

- `./dist/MyEA.mq5` — source đã render đầy đủ template + RiskGuard +
  PipNormalizer + same-bar guard + 8 TIP an toàn.
- `./dist/MyEA.ex5` — đã compile xanh.
- `./dist/dashboard.html` — quality matrix 64 cell, sẵn sàng publish.
- `./dist/lint.json`, `./dist/permission.json` — bằng chứng kiểm thử.

---

## 1. Chuẩn bị môi trường

Phần này chỉ chạy 1 lần / máy. Nếu muốn cấu hình chi tiết (proxy, Wine
prefix riêng, Docker), xem [ENV-SETUP-vi.md](ENV-SETUP-vi.md).

### 1.1. Yêu cầu

| Thành phần | Phiên bản | Bắt buộc? |
|------------|-----------|-----------|
| Python | ≥ 3.10 | ✅ |
| Wine | 8.0.2 (Linux/macOS) | ✅ khi compile bằng MetaEditor headless |
| MetaEditor | build ≥ 5260 | ✅ (để method-hiding ở mức ERROR) |
| MT5 terminal | build ≥ 4885 | ⚙️ chỉ cần khi chạy backtest cục bộ |
| ONNX runtime | 1.14 | ⚙️ chỉ scaffold `ml-onnx` |
| Xvfb | bất kỳ | ⚙️ chỉ headless CI Linux |

### 1.2. Linux (Ubuntu 22.04+) — script 1 phát

```bash
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea

# Cài Wine + MetaEditor headless qua wineboot (~3 phút, idempotent)
./scripts/setup-wine-metaeditor.sh

# Venv riêng cho kit, cài kit ở chế độ editable
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 1.3. Windows native

- Cài Python ≥ 3.10 từ [python.org](https://python.org).
- Cài MetaTrader 5 ở `C:\Program Files\MetaTrader 5\` (MetaEditor native
  có sẵn).
- Bật biến môi trường (PowerShell):

  ```powershell
  setx MQL5_TERMINAL_PATH "C:\Users\<you>\AppData\Roaming\MetaQuotes\Terminal\<HASH>"
  ```

- Trong PowerShell, kích hoạt venv:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\Activate.ps1
  pip install -e .
  ```

### 1.4. Docker (Devin / CI / VPS)

```bash
docker build -f Dockerfile.devin -t vck-mql5 .
docker run --rm -it -v "$PWD":/workspace vck-mql5 bash
```

Image này đã có sẵn Wine 8.0.2 + MetaEditor + Python venv + tất cả
requirement.lock. Đây cũng là image dùng cho CI `linux-tests` và
`windows-tests`.

---

## 2. Health check `mql5-doctor`

Chạy ngay sau install. Doctor probe Python deps, Wine, MetaEditor,
PipNormalizer, scaffold tree và 4 MCP server hiện có.

```bash
python -m vibecodekit_mql5.doctor
```

Kỳ vọng:

```json
{
  "ok": true,
  "probes": [
    {"name": "python",        "ok": true, "detail": "3.11.4"},
    {"name": "wine",          "ok": true, "detail": "8.0.2"},
    {"name": "metaeditor",    "ok": true, "detail": "build 5260"},
    {"name": "pipnormalizer", "ok": true},
    {"name": "scaffolds",     "ok": true, "detail": "23 preset×stack"},
    {"name": "mcp_servers",   "ok": true, "detail": "4 servers"}
  ]
}
```

Nếu probe nào `ok: false`, chỉ cần đọc trường `detail` — doctor đã viết
luôn câu lệnh fix gợi ý vào đó (ví dụ: `re-run setup-wine-metaeditor.sh`,
`pip install onnxruntime==1.14`, …).

> 💡 **Tip cho AI agent**: doctor cũng được wrap thành MCP tool
> `discover.doctor` — gọi qua bridge thay vì shell xem mục
> [5. Lối B](#5-lối-b--ai-coding-agent-qua-mcp-bridge).

---

## 3. Chọn 1 trong 2 lối đi

Kit cố tình hỗ trợ song song **2 con đường**:

| | **Lối A — CLI thủ công** | **Lối B — AI agent qua MCP** |
|---|---|---|
| Đối tượng | Dev tự tay gõ lệnh, đọc output | Codex CLI / Claude Code / Cursor / Devin / Claude Desktop |
| Transport | Shell / venv | JSON-RPC 2.0 over stdio |
| Tool surface | 50 CLI command | 29 MCP tool wrap đúng 25/50 lệnh + 4 helper |
| Khi nào dùng | Học kit, debug, dạy lớp, demo cho khách | Build EA hàng loạt, fix-loop tự động, dùng trong IDE coding agent |
| Pipeline | **Y hệt nhau** — cùng `auto_build`, lint, permission gate, dashboard | |

Bạn có thể dùng cả hai trong cùng project. Sản phẩm cuối (`.mq5`,
`.ex5`, dashboard) là bit-by-bit giống nhau.

Phần [4. Lối A](#4-lối-a--cli-thủ-công-7-bước) sẽ đi qua 7 bước CLI.
Phần [5. Lối B](#5-lối-b--ai-coding-agent-qua-mcp-bridge) đi qua việc
cài bridge vào 5 tool agent.

---

## 4. Lối A — CLI thủ công, 7 bước

```
prompt → spec → build → verify → test → review → ship
        4.1     4.2    4.3-4.4   4.5    4.6    4.7
```

### 4.1. Từ ý tưởng → `ea-spec.yaml`

Có 2 cách lấy `ea-spec.yaml`:

**(a) Free-text → spec (chat-driven)**

Nhanh nhất cho EA "kinh điển":

```bash
python -m vibecodekit_mql5.spec_from_prompt \
    "EA trend EURUSD H1 MACD + EMA cross, risk 0.5%, SL 30 pips TP 60 pips, prop firm FTMO daily-DD 5%, close Friday 20h" \
    --out ea-spec.yaml
```

Parser sẽ tự suy luận `preset`, `stack` (mặc định `wizard-composable`),
`signals`, `filters`, và 3 block PR-2 (`prop_firm`, `time_exit`,
`stealth`) khi prompt nhắc tới chúng. Output bao gồm trường
`inferred` (giá trị tự suy luận) + `defaulted` (giá trị áp default) để
review trước khi build:

```yaml
name: TrendEA_EURUSD_H1
preset: standard
stack: wizard-composable
symbol: EURUSD
timeframe: H1
mode: personal
risk:
  per_trade_pct: 0.5
  sl_pips: 30
  tp_pips: 60
signals:
  - kind: macd
    fast: 12
    slow: 26
    signal: 9
  - kind: ema_cross
    fast: 9
    slow: 21
signal_logic: AND
prop_firm:
  daily_dd_pct: 5.0
  weekend_flat: true
time_exit:
  close_on_friday: true
  friday_close_hour: 20
```

**(b) Viết tay từ template**

Cho EA có hook đặc biệt hoặc dùng 5 block schema PR-8 mới
(`trailing`, `partial_close`, `correlation`, `swap_filter`, `logs`).
Xem mục [6. Schema](#6-schema-ea-specyaml--8-block-optional) để biết
tất cả field hợp lệ.

### 4.2. Validate spec (8 block)

```bash
python -m vibecodekit_mql5.spec_validate ea-spec.yaml
```

Lệnh này gom mọi lỗi schema vào một message duy nhất (joined bằng
`"; "`) — không stop ở lỗi đầu tiên. Ví dụ output khi spec sai 3 chỗ:

```
SpecValidationError: spec.timeframe must be a non-empty string; spec.risk.per_trade_pct=15.0 must satisfy 0 < x <= 10.0; spec.partial_close.levels[0].pct=-0.5 must satisfy -1e-9 < x <= 100.0
```

8 block optional, full back-compat:

| Block | Mục đích |
|-------|----------|
| `prop_firm` | FTMO/MFF: DD limits, news block, weekend-flat, copy-trading lock |
| `time_exit` | Close on Friday, max trade hours, session windows |
| `stealth` | Random slippage / comment pool / lot jitter, split orders |
| `trailing` | Trailing-stop: fixed / ATR / parabolic |
| `partial_close` | Scale-out nhiều mức + move-SL-về-breakeven |
| `correlation` | Max vị thế correlated, Pearson threshold, symbol group |
| `swap_filter` | Giới hạn swap pip/ngày, skip thứ tư triple-swap |
| `logs` | Level (debug/info/warn/error), file pattern, redact tài khoản |

Spec cũ không có các block này vẫn validate bình thường.

### 4.3. Build EA bằng `mql5-auto-build`

Lệnh đầu não. Chạy 6 stage tuần tự, có rollback nếu stage nào fail:

```
scan → build → lint → compile → permission-gate → dashboard
```

```bash
python -m vibecodekit_mql5.auto_build \
    --spec ea-spec.yaml \
    --out ./dist \
    --mode personal
```

Cờ `--mode` chọn permission profile:

| `--mode` | Layer áp dụng | Phù hợp |
|----------|---------------|---------|
| `personal` | 1, 2, 3, 4, 7 (5 layer) | Trader retail, account cá nhân |
| `team` | thêm 5 (commit signing) | Dev team chung repo |
| `enterprise` | đủ 1-7 | Prop firm, fund, broker |

Output `./dist`:

```
dist/
├── TrendEA_EURUSD_H1.mq5            # source đã render
├── TrendEA_EURUSD_H1.ex5            # binary compile xanh
├── TrendEA_EURUSD_H1.docs.html      # docs Neo-Retro (mở browser)
├── TrendEA_EURUSD_H1.docs.md        # docs Markdown song song
├── lint.json                         # 0 ERROR + ≤ N WARN tuỳ AP
├── permission.json                   # 7-layer report
├── quality-matrix.html               # quality matrix 64-cell + embed card
└── build.log
```

Nếu một stage fail (ví dụ compile báo `unknown identifier`), `auto_build`
**không** chạy permission-gate / dashboard, để dev fix trước.

### 4.3.1. EA docs auto-generation (Neo-Retro Dev Deck)

Sau khi compile + gate xong, pipeline tự render 1 file docs hướng dẫn
chi tiết cho EA vừa build — **mặc định 100% tiếng Việt**, theo design
system Neo-Retro Dev Deck (cream grid bg, hot pink / yellow / cyan block
viền đen dày, pixel-art icon). Code identifier (`InpMagic`,
`InpRiskMoney`, `CRiskGuard`, `ema_cross`, ...) giữ nguyên theo project.

**Cấu trúc docs sinh ra:**

| Section | Nội dung |
|---------|----------|
| Frontmatter | `ea_name`, `ea_version`, `kit_version`, `built_at`, verdict `compile` + `gate` |
| Hero manifesto | Slogan + tên EA |
| Kiến trúc hệ thống | 3 layer block: Quản lý vốn / Tổng hợp tín hiệu / Thực thi lệnh |
| Chu trình chiến lược | Timeline 4 bước: Quét → Soạn → Kiểm → Phát hành |
| Tham số EA | Bảng `Tên · Kiểu · Mặc định · Ghi chú` parse từ mọi `input` declaration trong `.mq5` |
| Lưu ý quan trọng | Take-notes auto-derived từ 8 block PR-2/PR-8 (prop-firm, trailing, partial close, ONNX, ...) |

![EA docs Neo-Retro VN — phần hero + kiến trúc](https://app.devin.ai/attachments/5678d878-23f9-433c-a6f2-b4f4c39bade5/screenshot-ea-docs-vi-top.png)

![EA docs Neo-Retro VN — timeline + params + take-notes](https://app.devin.ai/attachments/cb444a06-96e7-46f3-bdaa-b4d9f3adef72/screenshot-ea-docs-vi-middle.png)

**Dashboard `quality-matrix.html`** mọc thêm card vàng đính kèm 2-3 link
tới docs html / md / pdf (PDF chỉ xuất hiện nếu Chrome có sẵn):

![Dashboard với embed card EA Docs](https://app.devin.ai/attachments/c6618a98-d836-4494-9a71-491c1202b18b/screenshot-dashboard-embed.png)

**Cờ điều khiển docs**

| Cờ | Mặc định | Tác dụng |
|----|----------|----------|
| `--no-docs` | (off) | Bỏ qua stage docs hoàn toàn |
| `--docs-lang vi\|en` | `vi` | Ngôn ngữ docs. `en` opt-out về tiếng Anh, mặc định tiếng Việt |
| `--docs-formats html,md` | `html,md` | Format xuất. Thêm `pdf` để render qua headless Chrome |

**Ví dụ — xuất kèm PDF qua headless Chrome:**

```bash
python -m vibecodekit_mql5.auto_build \
    --spec ea-spec.yaml \
    --out ./dist \
    --mode personal \
    --docs-formats html,md,pdf
```

Khi `pdf` được yêu cầu, pipeline dò Chrome theo thứ tự:

1. `$MQL5_CHROME_PATH` env var (override mạnh nhất)
2. Chrome for Testing trong Devin sandbox
3. Playwright chromium nếu đã cài
4. `chromium` / `chrome` trên `PATH`

Nếu không host nào có Chrome → build **vẫn xanh**, `auto-build-report.json`
ghi `docs.pdf_error` chỉ rõ env var để override. Dashboard chỉ render link
tới các format thực sự có trên đĩa (PR-18.1).

**Render lại docs độc lập (không cần re-build EA)** — CLI `mql5-ea-docs`:

```bash
python -m vibecodekit_mql5.ea_docs \
    ./dist/TrendEA_EURUSD_H1.mq5 \
    --spec ea-spec.yaml \
    --out ./dist \
    --lang vi \
    --formats html,md,pdf
```

Lưu ý: artifact sinh ra từ CLI này **byte-identical** với artifact pipeline
vì cả hai share helper `auto_build_docs_stage.write_docs_to_disk` (PR-19).

### 4.4. Verify — lint, method-hiding, trader17, permission

`auto_build` đã chạy 3 verify đầu tự động (lint, method-hiding,
permission). Bạn có thể chạy lẻ:

**Lint 23 anti-pattern (8 ERROR + 14 WARN + 1 method-hiding)**

```bash
python -m vibecodekit_mql5.lint            ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.lint_best_practice ./dist/TrendEA_EURUSD_H1.mq5
```

ERROR break CI. WARN chỉ log để xem xét. Danh sách 23 AP đầy đủ ở mục
[6 trong USAGE-vi.md](USAGE-vi.md#6-23-anti-pattern-detector).

**Method-hiding check** (chỉ áp dụng MetaEditor build ≥ 5260)

```bash
python -m vibecodekit_mql5.method_hiding_check ./dist/TrendEA_EURUSD_H1.mq5
```

**Trader-17 checklist** — 17 điểm reliability cho live trading

```bash
python -m vibecodekit_mql5.trader_check ./dist/TrendEA_EURUSD_H1.mq5
```

**Permission gate** (chạy lại nếu đổi `--mode`)

```bash
python -m vibecodekit_mql5.permission --mode personal --in ./dist
```

### 4.5. Test — backtest, walkforward, Monte Carlo

Kit cố tình KHÔNG tự chạy MT5 — bạn vẫn chủ động chạy tester (qua
terminal local, Wine, hoặc MT5 Cloud Network). Kit lo parse + verdict.

**Backtest 1 cú (đã có XML từ tester)**

```bash
python -m vibecodekit_mql5.backtest ./reports/run1.xml
```

→ JSON 14 metric (PF, Sharpe, GHPR, expected payoff, MFE/MAE, …).

**Tự lái terminal64.exe đầu cuối**

```bash
python -m vibecodekit_mql5.tester_run \
    --ea ./dist/TrendEA_EURUSD_H1.ex5 \
    --tester-ini tester.ini \
    --out ./reports/run1.xml
```

(Cần `MQL5_TERMINAL_PATH` hoặc cờ `--terminal-path`.)

**Walkforward IS/OOS**

```bash
python -m vibecodekit_mql5.walkforward ./reports/is.xml ./reports/oos.xml
```

Verdict PASS/WARN/FAIL ở ngưỡng Sharpe correlation 0.5 / 0.3.

**Monte Carlo bootstrap DD**

```bash
python -m vibecodekit_mql5.monte_carlo ./reports/returns.csv --reported-dd 12.5
```

Verdict PASS nếu p95 ≤ 1.5 × reported DD.

**Multibroker stability** (N file XML từ N broker)

```bash
python -m vibecodekit_mql5.multibroker --reports ic.xml,ftmo.xml,exness.xml
```

**Overfit sanity** (so OOS/IS Sharpe ratio, không cần XML)

```bash
python -m vibecodekit_mql5.overfit_check ./reports/is.xml ./reports/oos.xml
```

### 4.6. Review — engineering, CSO, CEO, RRI

5 review persona + 6 RRI persona — open template để dev tự fill (hoặc
agent fill qua bridge):

```bash
python -m vibecodekit_mql5.eng_review     ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.cso            ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.ceo_review     ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.investigate    ./reports/incident.log

# RRI: backtest review, risk & robustness, indicator-dev
python -m vibecodekit_mql5.rri_bt        ./reports/oos.xml
python -m vibecodekit_mql5.rri_rr        ./dist/TrendEA_EURUSD_H1.mq5
python -m vibecodekit_mql5.rri_chart     ./dist/TrendEA_EURUSD_H1.mq5
```

Output: file Markdown template với 5 persona × 7 dimension × 8 axis
(280 ô) cho RRI-bt, 25 câu / persona × 3 mode cho RRI-rr.

### 4.7. Ship — dashboard + Algo Forge PR

**Đóng gói artifact ship-ready**

Sau khi `mql5-auto-build` sinh `./dist`, chạy `mql5-package` để tạo
manifest checksum + file zip giao cho operator/reviewer:

```bash
python -m vibecodekit_mql5.package \
    --out-dir ./dist \
    --spec ea-spec.yaml
```

Hoặc bật đóng gói ngay trong pipeline:

```bash
python -m vibecodekit_mql5.auto_build \
    --spec ea-spec.yaml \
    --out-dir ./dist \
    --mode personal \
    --package
```

`--package` chỉ chạy sau khi pipeline xanh; nếu build/lint/compile/gate fail,
report ghi package bị skip và không sinh zip. Có thể override tên zip bằng
`--package-zip ./release/TrendEA-v1.0.0.zip`.

Output thêm vào `./dist`:

```
dist/
├── manifest.json                # inventory + SHA-256 từng artifact
└── dist-ship.zip                 # gói ship-ready gồm artifact + manifest
```

`manifest.json` phân nhóm file theo mục đích:

| Group | Gồm những gì | Mục đích |
|-------|--------------|----------|
| `runtime` | `*.ex5`, `Sets/*.set` | Copy vào MT5 để chạy EA / Strategy Tester |
| `source` | `*.mq5`, `*.mqh`, `README.md` | Audit source, recompile, review scaffold |
| `review` | `auto-build-report.json`, `quality-matrix.html`, `*.docs.*`, `*.log` | Bằng chứng build/lint/compile/gate + docs |
| `repro` | `ea-spec.yaml`, model/data phụ trợ nếu có | Tái tạo build từ spec |

Mỗi artifact trong manifest có cấu trúc:

```json
{
  "path": "TrendEA_EURUSD_H1.ex5",
  "group": "runtime",
  "kind": "compiled-ea",
  "size": 36466,
  "sha256": "...",
  "archive_path": "TrendEA_EURUSD_H1.ex5"
}
```

Nếu spec nằm ngoài `--out-dir`, `--spec` sẽ đưa spec vào zip dưới
`repro/<tên-file-spec>` để gói release tự đủ thông tin tái tạo.

**Render + publish dashboard**

```bash
python -m vibecodekit_mql5.dashboard \
    --in ./dist \
    --publish-cmd 'rsync -az ./dist/dashboard.html user@host:/var/www/'
```

Không có `--publish-cmd` thì dashboard chỉ trả về `file://` URI cục bộ
(hermetic-safe cho CI).

**Mở PR trên MQL5 Algo Forge**

```bash
export MQL5_FORGE_TOKEN=...
python -m vibecodekit_mql5.forge_pr \
    --repo my-org/my-ea \
    --title "TrendEA v1.0" \
    --body "Dashboard: $(cat ./dist/dashboard_url.txt)"
```

Không có token → trả dry-run dict (`endpoint` + `planned_payload`) để
debug.

**Tag + push (release)**

```bash
python -m vibecodekit_mql5.ship --tag v1.0.0 --push
```

---

## 5. Lối B — AI coding agent qua MCP bridge

Kit có 4 MCP server (JSON-RPC 2.0 over stdio):

| Server | Tool | Read/Write | Mục đích |
|--------|------|-----------|----------|
| `metaeditor-bridge` | 3 | Write | Compile EA qua MetaEditor headless (Wine) |
| `mt5-bridge` | 10 | **READ-ONLY** | Đọc account, position, history, symbol info |
| `algo-forge-bridge` | 6 | Write | CRUD repo, PR trên MQL5 Algo Forge |
| `vibecodekit-bridge` | **30** | Write | Toàn bộ pipeline build EA (spec → ship + docs) |

`vibecodekit-bridge` là server bạn cần. 30 tool chia theo nhóm:

| Nhóm | Tool count | Tên |
|------|------------|-----|
| `spec.*` | 2 | `spec.from_prompt`, `spec.validate` |
| `build.*` | 1 | `build.auto` |
| `verify.*` | 14 | `verify.lint`, `verify.lint_best_practice`, `verify.method_hiding`, `verify.compile`, `verify.permission`, `verify.trader17`, `verify.broker_safety`, `verify.backtest`, `verify.walkforward`, `verify.montecarlo`, `verify.multibroker`, `verify.fitness`, `verify.mfe_mae`, `verify.overfit`, `verify.auto_fix` |
| `review.*` | 4 | `review.eng`, `review.cso`, `review.ceo`, `review.investigate` |
| `rri.*` | 1 | `rri.persona` |
| `dashboard.*` | 1 | `dashboard.publish` |
| `forge.*` | 1 | `forge.pr.create` |
| `discover.*` | 3 | `discover.doctor`, `discover.scan`, `discover.llm_context` |
| `docs.*` | 1 | `docs.ea_render` (PR-19) |

### 5.1. Cài `vibecodekit-bridge` vào tool

**Claude Code CLI**

```bash
claude mcp add vibecodekit-bridge -- \
    python /abs/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py
```

**Cursor IDE**

`.cursor/mcp.json` ở repo gốc:

```json
{
  "mcpServers": {
    "vibecodekit-bridge": {
      "command": "python",
      "args": ["/abs/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py"]
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`)

```toml
[mcp.servers.vibecodekit-bridge]
command = "python"
args = ["/abs/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py"]
```

**Claude Desktop** (`%APPDATA%\Claude\claude_desktop_config.json` trên Windows hoặc `~/Library/Application Support/Claude/claude_desktop_config.json` trên macOS)

```json
{
  "mcpServers": {
    "vibecodekit-bridge": {
      "command": "python",
      "args": ["C:\\path\\to\\vibecodekit-mql5-ea\\mcp\\vibecodekit-bridge\\server.py"]
    }
  }
}
```

**Devin** — đã có sẵn trong snapshot mặc định khi bạn clone repo này; không cần cài thêm.

### 5.2. Prompt mẫu cho agent

Sau khi cài, gõ prompt trực tiếp trong tool agent. Bridge sẽ tự chọn
tool đúng và pipeline kit chạy đầy đủ.

**Trong Claude Code CLI:**

```
Tôi cần một EA mean-reversion XAUUSD M15.
- Risk 0.3% mỗi lệnh
- SL 50 pip, TP 100 pip
- Bollinger Bands 20/2 + RSI < 30 → mua
- Trailing stop ATR 14, hệ số 2.5
- Đóng lệnh thứ 6 mỗi tuần
- Build với mode personal, output ra ./out/

Sau khi build xong, chạy verify.lint + verify.trader17 và publish
dashboard local.
```

Agent sẽ tự gọi tuần tự:

1. `spec.from_prompt` — tạo `ea-spec.yaml`.
2. `spec.validate` — confirm schema OK.
3. `build.auto` — render + compile + permission gate + docs + dashboard.
4. `verify.lint` — quét 23 AP.
5. `verify.trader17` — 17 checklist.
6. `dashboard.publish` — generate `dashboard.html`.
7. `docs.ea_render` (PR-19) — tùy chọn, re-render docs tiếng Việt /
   xuất kèm PDF nếu agent cần version khác (xem [5.4](#54-re-render-docs-qua-docsea_render)).

**Trong Cursor (chat sidebar):**

```
@vibecodekit-bridge build EA scalper EURUSD M5 risk 0.2% SL 10 TP 15, ema cross 5/13, no news 30 min before/after, output ./scalper/
```

### 5.3. Fix-loop `verify.lint` ↔ `verify.auto_fix`

Đây là pattern mà PR-7 thêm vào — đặc biệt mạnh cho coding agent:

```
Loop:
  lint_result = call('verify.lint', {'path': './out/MyEA.mq5'})
  if lint_result['errors_count'] == 0: break
  call('verify.auto_fix', {'path': './out/MyEA.mq5'})  # rewrite in-place
```

### 5.4. Re-render docs qua `docs.ea_render`

PR-19 mở tool số 30: `docs.ea_render`. Agent có thể gọi trực tiếp khi
chỉ cần re-render docs (đổi ngôn ngữ, thêm PDF, tưới lại sau khi tweak
spec) mà không muốn re-run cả pipeline `build.auto`.

```python
out = call('docs.ea_render', {
  'spec':      spec_dict,                      # nguyên dạng parsed từ spec.validate
  'mq5_source': open('./out/MyEA.mq5').read(),
  'out_dir':   './out',
  'lang':      'vi',                            # mặc định; 'en' opt-out
  'formats':   ['html', 'md', 'pdf'],          # mặc định ['html','md']
})
# → {'ok': True, 'lang': 'vi', 'formats': [...],
#    'outputs': {'html': '.../MyEA.docs.html',
#                'md':   '.../MyEA.docs.md',
#                'pdf':  '.../MyEA.docs.pdf'},
#    'pdf_error': null}
```

Cặp `spec` thiếu key bắt buộc → server trả JSON-RPC `-32602 Invalid
params` ngay lập tức (PR-13). Spec sai schema → `{ok: false, stage:
'validate', errors: [...]}`. Chrome không có + `formats` có `pdf` →
`pdf_error` ghi rõ lý do, các format khác vẫn xuất bình thường.

Nếu muốn agent đọc file `.mq5` từ đĩa thay vì truyền in-memory:

```python
call('docs.ea_render', {
  'spec':     spec_dict,
  'mq5_path': './out/MyEA.mq5',
  'out_dir':  './out',
})
```

`verify.auto_fix` đóng 8 AP critical tự động (AP-1 missing SL, AP-3
missing magic, AP-15 race, AP-17 sync I/O, AP-18 method shadow,
AP-20 deinit leak, AP-21 OnTester missing, AP-22 init-fail handler).
Agent chỉ cần lặp lại tối đa 3 lần là sạch ERROR.

> ⚠️ `verify.auto_fix` mặc định đọc file với `errors='replace'` (PR-7.1
> hotfix) — file `.mq5` có ký tự Windows-1252 (©, em-dash) không làm
> crash bridge.

**Tool `discover.*` cho agent prime context:**

- `discover.doctor` — wrap `mql5-doctor` JSON, agent biết env có sẵn gì.
- `discover.scan` — quét workspace, phân loại file theo extension
  (`.mq5` → ea-source, `.mqh` → include, `.set` → tester-set, `.ex5` →
  compiled, `.onnx` → model).
- `discover.llm_context` — wire 1 trong 3 LLM-bridge scaffold pattern
  (`cloud-api` / `self-hosted-ollama` / `embedded-onnx-llm`) vào EA có
  sẵn.

---

## 6. Schema `ea-spec.yaml` — 8 block optional

Tất cả block dưới đây **optional + back-compat**. Spec không chứa
block nào trong số này vẫn validate sạch.

### 6.1. `prop_firm` (PR-2)

```yaml
prop_firm:
  daily_dd_pct: 5.0           # 0 < x <= 100
  max_dd_pct: 10.0            # 0 < x <= 100
  profit_target_pct: 8.0      # 0 < x <= 100
  news_block_min: 30          # 0 < x <= 1440
  weekend_flat: true
  copy_trading_lock: false
```

### 6.2. `time_exit` (PR-2)

```yaml
time_exit:
  close_on_friday: true
  friday_close_hour: 20       # 0 <= x <= 23
  max_trade_hours: 48         # 0 < x <= 720
  session_start_hour: 8       # 0 <= x <= 23
  session_end_hour: 22        # 0 <= x <= 23
```

### 6.3. `stealth` (PR-2)

```yaml
stealth:
  randomize_slippage_pips: 2.0
  randomize_comment_pool: [alpha, beta, gamma]
  randomize_lot_jitter_pct: 1.5
  split_orders: true
  avoid_round_numbers: true
```

### 6.4. `trailing` (PR-8)

```yaml
trailing:
  enabled: true
  mode: atr                   # fixed | atr | parabolic
  start_pips: 20.0
  step_pips: 5.0
  min_distance_pips: 3.0
  atr_period: 14              # bắt buộc khi mode=atr
  atr_mult: 2.5               # bắt buộc khi mode=atr
```

### 6.5. `partial_close` (PR-8)

```yaml
partial_close:
  enabled: true
  levels:
    - { at_pips: 20.0, pct: 50.0 }     # close 50% khi profit 20 pip
    - { at_pips: 50.0, pct: 30.0 }     # close thêm 30% khi profit 50 pip
  move_sl_to_breakeven_after_first: true
  breakeven_buffer_pips: 2.0
```

> 🔒 `pct` ∈ `[0, 100]`. Giá trị âm bị reject (PR-8.1 hotfix), `pct=0`
> vẫn hợp lệ (no-op level).

### 6.6. `correlation` (PR-8)

```yaml
correlation:
  max_correlated_positions: 2
  correlation_threshold: 0.8       # Pearson |r|, ∈ (-1, 1]
  correlation_window_bars: 100
  symbol_group: [EURUSD, GBPUSD, AUDUSD]
  block_if_correlated_loss: true
```

### 6.7. `swap_filter` (PR-8)

```yaml
swap_filter:
  max_long_swap_pips_per_day: -1.0    # số âm hợp lệ (broker cộng swap âm)
  max_short_swap_pips_per_day: -1.5
  max_hold_bars_if_negative_swap: 24
  skip_wednesday_triple_swap: true
```

### 6.8. `logs` (PR-8)

```yaml
logs:
  enabled: true
  level: info                 # debug | info | warn | error
  to_file: true
  file_pattern: "logs/{ea}_{date}.log"
  to_terminal: false
  redact_account_numbers: true
```

> ℹ️ Đến phiên bản này, 5 block PR-8 là **metadata** — `EaSpec`
> round-trip qua YAML và validate, nhưng scaffold template chưa
> consume các trường này. Scaffold sẽ tích hợp trong PR sau (ngoài
> scope hướng dẫn hiện tại).

---

## 7. Troubleshooting & FAQ

### 7.1. `mql5-doctor` báo Wine fail

```bash
./scripts/setup-wine-metaeditor.sh --reset
```

Cờ `--reset` xoá Wine prefix cũ và bootstrap lại. An toàn — kit không
lưu credential trong prefix.

### 7.2. Compile báo `metaeditor build < 5260`

Tải MetaTrader 5 build ≥ 5260 từ broker hoặc MetaQuotes. Nếu vẫn cần
build cũ, method-hiding linter sẽ chuyển từ ERROR sang WARN tự động
(nhưng bạn không nên ship live EA build < 5260).

### 7.3. `spec_validate` báo `unknown top-level key`

Bạn đặt block chưa có trong 5 trường gốc + 8 block PR-2+PR-8. Kiểm
tra chính tả (vd `prop-firm` vs `prop_firm` — kit dùng underscore).

### 7.4. `auto_build` báo permission-gate FAIL ở layer 5

Layer 5 = commit signing. Hoặc cần `git config commit.gpgsign true`
và setup GPG key, hoặc dùng `--mode personal` (skip layer 5).

### 7.5. `forge.pr.create` trả dry-run dict thay vì PR thật

Thiếu `MQL5_FORGE_TOKEN` trong env. Đặt token rồi chạy lại:

```bash
export MQL5_FORGE_TOKEN="..."
```

### 7.6. CI báo `LOC ceiling exceeded`

Module trong `scripts/vibecodekit_mql5/` có ceiling 400 effective LOC.
Tách phần code thừa sang module helper (xem
`spec_extensions.py` / `spec_blocks_extra.py` làm ví dụ).

### 7.7. AI agent gọi MCP nhưng không nhận được tool

- Đảm bảo đường dẫn tới `server.py` là **absolute path**.
- Đảm bảo venv kit đã `pip install -e .` trước khi launch server.
- Test stdio thủ công:

  ```bash
  echo '{"jsonrpc":"2.0","id":1,"method":"initialize"}' \
      | python mcp/vibecodekit-bridge/server.py
  ```

  Kỳ vọng response chứa `protocolVersion`, `capabilities`, `serverInfo`.

---

## 8. Phụ lục — 50 CLI command theo nhóm

Tham khảo nhanh. Reference đầy đủ ở [USAGE-vi.md](USAGE-vi.md).

**Discovery (4)** — `scan`, `survey`, `doctor`, `audit`

**Plan (4)** — `rri`, `vision`, `blueprint`, `tip`

**Build (12)** — `build`, `auto_build`, `auto_fix`, `spec_from_prompt`,
`dashboard`, `wizard`, `pip_normalize`, `async_build`, `onnx_export`,
`onnx_embed`, `llm_context`, `forge_init`

**Verify (11)** — `compile`, `lint`, `method_hiding_check`,
`backtest`, `tester_run`, `walkforward`, `monte_carlo`,
`overfit_check`, `multibroker`, `fitness`, `mfe_mae`

(`lint_best_practice` tồn tại như mô-đun Python — chạy qua
`python -m vibecodekit_mql5.lint_best_practice` — nhưng không đăng ký
là console script trong `pyproject.toml`, nên không đếm vào nhóm
Verify CLI.)

**RRI methodology (3)** — `rri_bt`, `rri_rr`, `rri_chart`

**Review (5)** — `review`, `eng_review`, `ceo_review`, `cso`,
`investigate`

**Deploy (3)** — `deploy_vps`, `cloud_optimize`, `canary`

**Ship (3)** — `forge_pr`, `ship`, `refine`

**Other (4)** — `broker_safety`, `trader_check`, `install`,
`second_opinion`

Tổng: **49 CLI** + 1 router meta = **50 entry**.

---

## Tổng kết

- **Lối A (CLI)**: phù hợp khi học kit, debug, dạy lớp. 7 bước rõ
  ràng từ prompt → ship.
- **Lối B (MCP)**: phù hợp khi dùng trong AI coding agent (Codex /
  Claude / Cursor / Devin / Claude Desktop). 30 tool wrap đầy đủ
  pipeline (kèm `docs.ea_render` để re-render docs theo yêu cầu).
- Pipeline kit là **source of truth**. Lối B chỉ là JSON-RPC wrapper
  của lối A — không bypass stage nào.
- Mỗi build tự sinh ra docs Neo-Retro Dev Deck **mặc định tiếng Việt**
  (`<name>.docs.html` + `.docs.md`, kèm `.docs.pdf` nếu có Chrome).
  Dashboard `quality-matrix.html` chỉ link tới format thực sự có
  trên đĩa.
- Schema `ea-spec.yaml` đã mở rộng đủ 8 block optional (3 PR-2 +
  5 PR-8) cho EA prop firm / trailing / partial close / correlation
  / swap filter / logs.
- Baseline mới nhất: **799 test passed / 2 skipped**, ruff clean,
  audit post-phase-E pass.

Khi gặp blocker không có trong mục [7. Troubleshooting](#7-troubleshooting--faq), mở issue ở
<https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea/issues> kèm
output của `python -m vibecodekit_mql5.doctor`.
