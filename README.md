# vibecodekit-mql5-ea

[![version](https://img.shields.io/badge/version-v1.0.1-blue)](https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea/releases/tag/v1.0.1)
[![tests](https://img.shields.io/badge/tests-852%20passing-success)]()
[![lint](https://img.shields.io/badge/ruff-clean-success)]()
[![license](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

> **Vibecode methodology kit** for building production-grade MQL5 Expert
> Advisors on MetaTrader 5. **Fifty CLI commands** (including a
> single-shot `mql5-auto-build` pipeline, an auto-fix loop for the eight
> critical anti-patterns, a natural-language `mql5-spec-from-prompt`
> parser, and a publishable quality-matrix dashboard), four MCP
> servers, twenty-nine reference cheatsheets, twenty-three anti-pattern
> detectors, and one fully worked 4-hour wizard-composable portfolio EA
> — all delivered as a flat, router-free, fail-fast toolkit.

📘 **Docs:** [Quickstart](docs/QUICKSTART.md) · [Step-by-step user guide (EN)](docs/USER-GUIDE-en.md) · [Hướng dẫn step-by-step (VN)](docs/USER-GUIDE-vi.md) · [Full usage reference (EN)](docs/USAGE-en.md) · [Reference đầy đủ (VN)](docs/USAGE-vi.md) · [Per-IDE setup](docs/ENV-SETUP-vi.md) · [Command catalog](docs/COMMANDS.md) · [Chat-driven build](docs/devin-chat-driven-build.md) · [Plan v5](docs/PLAN-v5.md)

---

## English

### What you get in v1.0.1

| Layer | Shipped |
|-------|---------|
| **Commands** | 50 (`/mql5-{scan,survey,doctor,audit,rri,vision,blueprint,tip,build,auto-build,auto-fix,spec-from-prompt,dashboard,wizard,pip-normalize,async-build,onnx-export,onnx-embed,llm-context,forge-init,compile,lint,method-hiding-check,backtest,tester-run,walkforward,monte-carlo,overfit-check,multibroker,fitness,mfe-mae,rri-bt,rri-rr,rri-chart,review,eng-review,ceo-review,cso,investigate,deploy-vps,cloud-optimize,canary,forge-pr,ship,refine,broker-safety,trader-check,install,second-opinion,permission}`) |
| **MCP servers** | 4 (`metaeditor-bridge`, `mt5-bridge` READ-ONLY[^1], `algo-forge-bridge`, `vibecodekit-bridge`) |
| **Reference docs** | 29 (`docs/references/50-survey.md` → `80-input-syntax.md`) |
| **Scaffolds** | 23 archetypes × broker variants (`scaffolds/trend/netting`, `scalping/hedging`, `hft-async/netting`, `service-llm-bridge/{cloud-api,self-hosted-ollama,embedded-onnx-llm}`, `ml-onnx/python-bridge`, `wizard-composable/netting`, `service/standalone`, …) |
| **Anti-pattern detectors** | 23 (8 critical `ERROR` + 14 best-practice `WARN` + 1 build-aware method-hiding) |
| **Quality matrix** | 8 dimensions × 8 axes = 64-cell HTML report (PASS / WARN / FAIL / N/A) |
| **Permission layers** | 7 (source-lint → compile → AP-lint → checklist → methodology → quality-matrix → broker-safety) |
| **Mode-aware orchestrator** | PERSONAL (layers 1/2/3/4/7) · TEAM (1-5,7) · ENTERPRISE (1-7) |
| **Trader checklist** | 17 items (`trader-check`) with 15/17 PASS threshold |
| **Worked example** | `examples/ea-wizard-macd-sar-eurusd-h1-portfolio/` — 4-hour enterprise turnaround |
| **Auto-build pipeline** | `mql5-spec-from-prompt` → `ea-spec.yaml` → `mql5-auto-build` (scan → build → lint → compile → permission-gate → dashboard) — single command, idempotent JSON report, optional publish-to-public-URL |
| **Reproducible env** | `requirements.lock` (pip-compile pinned) + `Dockerfile.devin` (3-stage: base / wine / ci) |
| **Test gate** | 852 tests passing across Phase 0/A/B/C/D/E |

[^1]: `mt5-bridge` requires the `MetaTrader5` Python package, which only
    installs on Windows or Wine MT5 desktop. On a Linux Devin VM without
    the broker terminal the import fails and every tool returns a
    deterministic **stub payload** (empty symbol list, zero bars, `build:
    0`). Stubs keep the MCP contract testable hermetically but never feed
    them into live broker-safety analysis. See
    [docs/USAGE-en.md §MCP servers](docs/USAGE-en.md#mcp-servers) for the
    full platform matrix.

### Quick start (5 minutes)

```bash
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea
./scripts/setup-wine-metaeditor.sh        # Linux only; ~3 min
python -m venv .venv && source .venv/bin/activate
pip install -e .

python -m vibecodekit_mql5.doctor         # health check
python -m vibecodekit_mql5.build stdlib --name FirstEA --symbol EURUSD --tf H1
python -m vibecodekit_mql5.lint    FirstEA.mq5
python -m vibecodekit_mql5.compile FirstEA.mq5
```

**One-shot pipeline (recommended for new EAs):**

```bash
# free text → ea-spec.yaml → scaffold + lint + compile + dashboard
mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5%" --out ea-spec.yaml
mql5-auto-build --spec ea-spec.yaml --out-dir build/FirstEA
jq '{ok, dashboard}' build/FirstEA/auto-build-report.json
```

See [docs/devin-chat-driven-build.md](docs/devin-chat-driven-build.md) for
the end-to-end chat flow and the `MQL5_DASHBOARD_PUBLISH_CMD` publish
hook (Vercel / S3 / scp+nginx).

Detailed walk-throughs:
- New users — start with the [step-by-step user guide](docs/USER-GUIDE-en.md), then deep-dive into [docs/USAGE-en.md](docs/USAGE-en.md)
- Dev teams + worked example — [examples/ea-wizard-macd-sar-eurusd-h1-portfolio/README.md](examples/ea-wizard-macd-sar-eurusd-h1-portfolio/README.md)
- IDE / CLI integration — [docs/ENV-SETUP-vi.md](docs/ENV-SETUP-vi.md)

### Phase history

| Phase | Tag | Theme | Highlights |
|-------|-----|-------|-----------|
| 0 | `v0.0.1` | Bootstrap | Wine 8.0.2 + headless MetaEditor + Xvfb + CI |
| A | `v0.1.0` | Core foundation | `CPipNormalizer`, `CRiskGuard`, `CMagicRegistry`, 8 critical AP detectors, 3 stdlib scaffolds |
| B | `v0.2.0` | Test & validation | Strategy Tester driver, walk-forward, Monte-Carlo, multi-broker, Trader-17 checklist |
| C | `v0.3.0` | Methodology | 6 RRI personas × 25 q × 3 modes, 8-step workflow, 64-cell quality matrix, 7-layer permission orchestrator |
| D | `v0.5.0` | Tech 2024-2025 | ONNX runtime 1.14 export/embed, HFT async (`OrderSendAsync` + `OnTradeTransaction`), Algo Forge, LLM bridge (3 patterns), Cloud Network optimize, method-hiding linter |
| **E** | **`v1.0.1`** | **Polish & ship** | **29 reference docs, 4 MCP servers, `/mql5-canary` + `/mql5-tester-run`, 4-hour worked example, full `[project.scripts]` entry-point coverage** |
| **E+** | _(post-v1.0.1)_ | Auto-build pipeline | `mql5-auto-build` single-shot orchestrator, `mql5-auto-fix` AP-1/3/5/15/17/18/20/21 transformer, `mql5-spec-from-prompt` natural-language → `ea-spec.yaml`, `mql5-dashboard` quality-matrix publisher with public-URL hook, schema-driven `ea-spec.yaml` (risk / signals / filters / hooks), `requirements.lock` + `Dockerfile.devin`, expanded Devin Wine setup with `terminal64.exe` |

### Anti-patterns this kit refuses to ship

This kit was forked from a methodology study of `vibecodekit-handwritten`
(`VCK-HU`). It deliberately does **not** re-inherit any of the following
hot-spots:

- `query_loop.py`, `tool_executor.py`, `intent_router.py`,
  `pipeline_router.py` — dead routers & god modules
- Master `/mql5` single-prompt entrypoint — every command stands alone
- LLM hallucination of test results — every "passes" claim must be
  traceable to a Strategy Tester XML report
- `OrderSend` without `MarketInfo`-aware `CPipNormalizer` — broker
  digits/point asymmetry breaks pip math on JPY/XAU
- ONNX inference that was never validated against a real Strategy Tester
  run (caught by AP-19)
- `OrderSendAsync` without an `OnTradeTransaction` handler (caught by
  AP-18)
- `WebRequest` calls inside `OnTick` (caught by AP-17)
- Method-hiding on `CExpert` subclass without `using BaseClass::method;`
  (caught on MetaEditor build ≥ 5260)

---

## Tiếng Việt

### v1.0.1 có gì

| Thành phần | Đã giao |
|-----------|---------|
| **Lệnh CLI** | 50 lệnh — đầy đủ chu trình `scan → plan → build → verify → review → deploy → ship`, bao gồm `mql5-auto-build` chạy 1 lệnh, `mql5-auto-fix` đóng 8 AP nghiêm trọng, `mql5-spec-from-prompt` parse free-text → `ea-spec.yaml`, `mql5-dashboard` xuất ma trận chất lượng kèm URL public |
| **MCP server** | 4 (`metaeditor-bridge`, `mt5-bridge` chỉ-đọc[^2], `algo-forge-bridge`, `vibecodekit-bridge`) — chuẩn MCP JSON-RPC 2.0 over stdio |
| **Tài liệu tham khảo** | 29 cheatsheet (`docs/references/50-survey.md` → `80-input-syntax.md`) |
| **Scaffold** | 23 archetype × biến thể tài khoản (`trend/netting`, `scalping/hedging`, `hft-async/netting`, 3 biến thể LLM bridge, ml-onnx, `wizard-composable/netting`, `service/standalone`, …) |
| **Bộ dò chống mẫu xấu** | 23 detector (8 lỗi nghiêm trọng `ERROR` + 14 best-practice `WARN` + 1 method-hiding theo build) |
| **Ma trận chất lượng** | 8 chiều × 8 trục = 64 ô HTML (PASS / WARN / FAIL / N/A) |
| **Lớp permission** | 7 lớp (source-lint → compile → AP-lint → checklist → methodology → quality-matrix → broker-safety) |
| **Mode orchestrator** | PERSONAL (lớp 1/2/3/4/7) · TEAM (1-5, 7) · ENTERPRISE (1-7) |
| **Trader checklist** | 17 mục (`trader-check`), ngưỡng pass 15/17 |
| **Ví dụ hoàn chỉnh** | `examples/ea-wizard-macd-sar-eurusd-h1-portfolio/` — turnaround 4 tiếng ở chế độ enterprise |
| **Pipeline auto-build** | `mql5-spec-from-prompt` → `ea-spec.yaml` → `mql5-auto-build` (scan → build → lint → compile → permission-gate → dashboard) — 1 lệnh, JSON report idempotent, hook publish public URL tuỳ chọn |
| **Môi trường reproducible** | `requirements.lock` (pip-compile pin chặt) + `Dockerfile.devin` (3 stage: base / wine / ci) |
| **Test gate** | 852 test pass qua Phase 0/A/B/C/D/E |

[^2]: `mt5-bridge` cần package `MetaTrader5` Python — chỉ cài được trên
    Windows hoặc Wine MT5 desktop. Trên Linux Devin VM, import fail và
    mọi tool trả **stub payload** cố định (symbol list rỗng, 0 bar,
    `build: 0`). Stub giữ MCP contract test hermetic được nhưng tuyệt
    đối không feed vào broker-safety phân tích thật. Xem
    [docs/USAGE-vi.md §MCP server](docs/USAGE-vi.md#mcp-server) cho ma
    trận platform chi tiết.

### Bắt đầu nhanh (5 phút)

```bash
git clone https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea
cd vibecodekit-mql5-ea
./scripts/setup-wine-metaeditor.sh        # chỉ Linux, ~3 phút
python -m venv .venv && source .venv/bin/activate
pip install -e .

python -m vibecodekit_mql5.doctor         # health check môi trường
python -m vibecodekit_mql5.build stdlib --name FirstEA --symbol EURUSD --tf H1
python -m vibecodekit_mql5.lint    FirstEA.mq5
python -m vibecodekit_mql5.compile FirstEA.mq5
```

**Pipeline 1-lệnh (khuyến nghị cho EA mới):**

```bash
# free-text → ea-spec.yaml → scaffold + lint + compile + dashboard
mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5%" --out ea-spec.yaml
mql5-auto-build --spec ea-spec.yaml --out-dir build/FirstEA
jq '{ok, dashboard}' build/FirstEA/auto-build-report.json
```

Xem [docs/devin-chat-driven-build.md](docs/devin-chat-driven-build.md)
cho flow chat đầy đủ và hook `MQL5_DASHBOARD_PUBLISH_CMD` để publish
bảng chất lượng lên Vercel / S3 / scp+nginx.

Hướng dẫn chi tiết:
- Người mới — đọc [hướng dẫn step-by-step](docs/USER-GUIDE-vi.md) trước, sau đó deep-dive [docs/USAGE-vi.md](docs/USAGE-vi.md)
- Team dev + worked example — [examples/ea-wizard-macd-sar-eurusd-h1-portfolio/README.md](examples/ea-wizard-macd-sar-eurusd-h1-portfolio/README.md)
- Tích hợp IDE / CLI — [docs/ENV-SETUP-vi.md](docs/ENV-SETUP-vi.md)

### Lịch sử các phase

| Phase | Tag | Chủ đề | Điểm nhấn |
|-------|-----|--------|----------|
| 0 | `v0.0.1` | Bootstrap | Wine 8.0.2 + MetaEditor headless + Xvfb + CI |
| A | `v0.1.0` | Nền tảng | `CPipNormalizer`, `CRiskGuard`, `CMagicRegistry`, 8 AP nghiêm trọng, 3 scaffold stdlib |
| B | `v0.2.0` | Test & validation | Driver Strategy Tester, walk-forward, Monte-Carlo, multi-broker, Trader-17 |
| C | `v0.3.0` | Phương pháp luận | 6 RRI persona × 25 câu × 3 mode, workflow 8 bước, ma trận 64 ô, orchestrator 7 lớp |
| D | `v0.5.0` | Công nghệ 2024-2025 | ONNX runtime 1.14, HFT async, Algo Forge, LLM bridge (3 pattern), Cloud Network optimize, method-hiding linter |
| **E** | **`v1.0.1`** | **Polish & ship** | **29 tài liệu tham khảo, 4 MCP server, `/mql5-canary` + `/mql5-tester-run`, worked example 4 tiếng, đầy đủ entry-point `[project.scripts]`** |
| **E+** | _(post-v1.0.1)_ | Pipeline auto-build | `mql5-auto-build` orchestrator 1 lệnh, `mql5-auto-fix` transform AP-1/3/5/15/17/18/20/21, `mql5-spec-from-prompt` free-text → `ea-spec.yaml`, `mql5-dashboard` publisher ma trận chất lượng có hook URL public, `ea-spec.yaml` schema-driven (risk / signals / filters / hooks), `requirements.lock` + `Dockerfile.devin`, mở rộng setup Devin Wine kèm `terminal64.exe` |

### Anti-pattern kit từ chối ship

Kit này KHÔNG kế thừa các điểm nóng từ `vibecodekit-handwritten` (VCK-HU):

- `query_loop.py`, `tool_executor.py`, `intent_router.py`, `pipeline_router.py` — router chết, god module
- Master `/mql5` entrypoint một prompt — mỗi command đứng độc lập
- LLM bịa kết quả test — mọi tuyên bố "đã pass" phải truy ngược về XML report của Strategy Tester
- `OrderSend` không qua `CPipNormalizer` aware-MarketInfo — bất đối xứng digits/point gây sai pip ở JPY/XAU
- ONNX inference chưa validate trên Strategy Tester thật (bắt bởi AP-19)
- `OrderSendAsync` không có handler `OnTradeTransaction` (bắt bởi AP-18)
- `WebRequest` gọi trong `OnTick` (bắt bởi AP-17)
- Method-hiding trên subclass `CExpert` không có `using BaseClass::method;` (bắt từ build MetaEditor ≥ 5260)

---

## License

[MIT](LICENSE)
