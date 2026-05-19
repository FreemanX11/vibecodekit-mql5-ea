---
id: env-setup-vi
title: Tích hợp vibecodekit-mql5-ea với 6 môi trường (Devin / Codex CLI / Claude Code / Codex Desktop / Cursor / VS Code)
applicable_phase: E
audience: dev_team
---

# Tích hợp `vibecodekit-mql5-ea` với 6 môi trường dev / agent

Hướng dẫn này áp dụng v1.0.0+. Mỗi section hoàn chỉnh và độc lập:
chọn section IDE/CLI bạn dùng, paste config, sẵn sàng chạy 50 lệnh +
3 MCP server.

> 🇬🇧 English version pending — sections below are bilingual where it
> matters; CLI snippets are language-neutral.

## Mục lục

1. [Devin (new session)](#1-devin-new-session)
2. [Codex CLI (terminal)](#2-codex-cli-terminal)
3. [Claude Code CLI (terminal)](#3-claude-code-cli-terminal)
4. [Codex Desktop (Windows app)](#4-codex-desktop-windows-app)
5. [Cursor](#5-cursor)
6. [VS Code + Copilot Chat](#6-vs-code--copilot-chat)
7. [MCP server config bảng tổng hợp](#7-mcp-server-config-bảng-tổng-hợp)

---

## 1. Devin (new session)

Devin tự kế thừa repo + blueprint. Tạo session mới với link repo
`https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea` và prompt
khởi đầu mẫu (một lệnh gọn nếu muốn dùng pipeline auto-build):

```
Bắt chước docs/devin-chat-driven-build.md. Sau đó:
1. mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5%" \
     --out ea-spec.yaml --strict
2. mql5-auto-build --spec ea-spec.yaml --out-dir build/DemoEA --force
3. Báo `.ok`, stage nào fail, và `.dashboard.public_url` từ
   build/DemoEA/auto-build-report.json.
```

Nếu muốn flow từng bước thủ công (debug hoặc học):

```
Đọc docs/USAGE-vi.md.  Sau đó:
1. Chạy `python -m vibecodekit_mql5.doctor` để verify env.
2. Build EA mẫu `wizard-composable/netting` tên "DemoEA" cho EURUSD H1.
3. Lint + compile + walk-forward 12 cửa sổ.
4. Báo lại artefact tạo ra.
```

### 1.1. Blueprint đã có sẵn

Devin VM cho repo này đã pre-install:
- Wine 8.0.2 (đã wineboot headless)
- MetaEditor build ≥ 5260 (Wine-side)
- `terminal64.exe` + `$MQL5_TERMINAL_PATH` (cho `mql5-tester-run` /
  `mql5-auto-build` stage compile + tester)
- Python 3.10 + venv
- `torch` (CPU), `onnx`, `onnxscript`
- `pre-commit` hooks
- `pytest`, `ruff`, `pip-tools` (để regen `requirements.lock`)

Nếu thiếu, blueprint sẽ tự cài lúc session khởi tạo (xem
`devin_env(action="read_config")`).

#### 1.1a. Môi trường reproducible (Dockerfile / lockfile)

Nếu muốn container hoá hoàn toàn (CI runner, bản local Mac/Win, hay
ghim số phiên bản):

```bash
# 3-stage image: base (Python deps) → wine (Wine + MetaEditor) → ci
docker build -f Dockerfile.devin --target wine -t mql5-kit:wine .
docker run --rm -v $PWD:/work -w /work mql5-kit:wine \
    bash -lc 'pytest -q && mql5-doctor'
```

File `requirements.lock` (sinh bởi `pip-compile --extra dev`) pin toàn
bộ cây dep cho dev/test — reproducible 100% giữa local và CI. Regen
khi bạn thêm dep mới:

```bash
pip install pip-tools
pip-compile --extra dev --output-file requirements.lock
```

### 1.2. Secret cần có

Nếu chạy lệnh tích hợp Algo Forge thật:
```
ALGO_FORGE_API_KEY = <từ vault>
```

Devin biết yêu cầu secret này khi cần — không cần set trước.

### 1.3. Tip dùng Devin hiệu quả

- Tham chiếu file bằng `<ref_file file="..." />` để Devin paste vào tool call.
- Yêu cầu Devin chạy `python -m vibecodekit_mql5.audit` trước khi report
  hoàn thành task — đảm bảo 70-test conformance pass.
- Khi cần PR, Devin sẽ tự `git_pr(action="create")` với template repo.

---

## 2. Codex CLI (terminal)

Codex CLI là OpenAI agentic CLI chạy local. Cài đặt:
```bash
npm install -g @openai/codex
```

### 2.1. `AGENTS.md` ở root repo

Codex tự đọc `AGENTS.md` khi ở trong repo. Tạo file này:

```markdown
# AGENTS.md — vibecodekit-mql5-ea

## Setup
- Wine 8.0.2 đã được cài qua `./scripts/setup-wine-metaeditor.sh`.
- Python venv ở `.venv/`. Activate: `source .venv/bin/activate`.
- 50 lệnh `python -m vibecodekit_mql5.<name>` (xem `docs/COMMANDS.md`).
- Đọc `docs/USAGE-vi.md` để biết workflow đầy đủ.
- Shortcut 1-lệnh:
  `mql5-spec-from-prompt "<prompt>" --out ea-spec.yaml && mql5-auto-build --spec ea-spec.yaml`.

## Build
```bash
python -m vibecodekit_mql5.build <archetype> --name NAME --symbol SYM --tf TF
```

## Test
```bash
pytest tests/gates/ -q
python -m vibecodekit_mql5.audit
```

## Lint
```bash
ruff check scripts/ mcp/
```

## Bắt buộc
- KHÔNG dùng `OrderSend` thô — luôn qua `CTrade` (AP-15).
- LUÔN gọi `CPipNormalizer::Init()` trước `OrderSend` (AP-20/21).
- ONNX phải validate qua Strategy Tester (AP-19).
```

### 2.2. Cấu hình MCP server

Codex CLI hỗ trợ MCP qua `~/.codex/config.toml`:

```toml
[mcp.servers.metaeditor-bridge]
command = "python"
args = ["/path/to/vibecodekit-mql5-ea/mcp/metaeditor-bridge/server.py"]

[mcp.servers.mt5-bridge]
command = "python"
args = ["/path/to/vibecodekit-mql5-ea/mcp/mt5-bridge/server.py"]

[mcp.servers.algo-forge-bridge]
command = "python"
args = ["/path/to/vibecodekit-mql5-ea/mcp/algo-forge-bridge/server.py"]
env = { ALGO_FORGE_API_KEY = "your-key-here" }

[mcp.servers.vibecodekit-bridge]
command = "python"
args = ["/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py"]
```

### 2.3. Chạy

```bash
cd vibecodekit-mql5-ea
codex "Build EA wizard-composable cho EURUSD H1, lint, compile và walk-forward 12 cửa sổ"
```

---

## 3. Claude Code CLI (terminal)

Claude Code là Anthropic agentic CLI. Cài đặt:
```bash
npm install -g @anthropic-ai/claude-code
```

### 3.1. `CLAUDE.md` ở root repo

Tương tự `AGENTS.md`:

```markdown
# CLAUDE.md — vibecodekit-mql5-ea

Xem `docs/USAGE-vi.md` để biết workflow 8 bước. Quy tắc bắt buộc:

1. Mọi `.mq5` mới phải dùng `CTrade` (không `OrderSend` thô).
2. Pip math phải qua `CPipNormalizer`.
3. ONNX inference phải validate qua Strategy Tester.
4. KHÔNG sửa test để bypass — sửa code.

## Lệnh thường dùng
- `python -m vibecodekit_mql5.doctor` — health check
- `python -m vibecodekit_mql5.build <archetype>` — render scaffold
- `python -m vibecodekit_mql5.lint <ea.mq5>` — 8 critical AP
- `python -m vibecodekit_mql5.compile <ea.mq5>` — Wine MetaEditor
- `pytest tests/gates/ -q` — 234 test

## Skill files
- `.claude/skills/build-ea/SKILL.md` — workflow build EA chi tiết
- `.claude/skills/verify/SKILL.md` — multi-stage verify pipeline
```

### 3.2. Skill file (recommended)

Tạo `.claude/skills/build-ea/SKILL.md`:

```markdown
---
name: build-ea
description: Build a new MQL5 EA from scaffold using the kit's 8-step workflow. Use when user asks to create, scaffold, or generate an EA.
---

# build-ea

1. Run `python -m vibecodekit_mql5.scan <project-dir>` first.
2. If user hasn't specified archetype, ask: "Trend / mean-reversion /
   breakout / scalping / hedging-multi / news-trading / arbitrage-stat
   / grid / dca / ml-onnx / hft-async / service-llm-bridge?"
3. Choose variant: netting (Forex broker, single position per symbol)
   or hedging (US broker, multiple positions allowed).
4. Run `python -m vibecodekit_mql5.build <archetype> --name <NAME>
   --symbol <SYMBOL> --tf <TF> --stack <variant> --out <DIR>`.
5. Always follow up with `lint` + `compile`.
```

### 3.3. Cấu hình MCP server

```bash
claude mcp add metaeditor-bridge \
    -- python /path/to/vibecodekit-mql5-ea/mcp/metaeditor-bridge/server.py

claude mcp add mt5-bridge \
    -- python /path/to/vibecodekit-mql5-ea/mcp/mt5-bridge/server.py

claude mcp add algo-forge-bridge \
    --env ALGO_FORGE_API_KEY=your-key-here \
    -- python /path/to/vibecodekit-mql5-ea/mcp/algo-forge-bridge/server.py

claude mcp add vibecodekit-bridge \
    -- python /path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py
```

Verify:
```bash
claude mcp list
```

### 3.4. Chạy

```bash
cd vibecodekit-mql5-ea
claude "Build EA wizard-composable cho EURUSD H1, lint, compile và walk-forward"
```

---

## 4. Codex Desktop (Windows app)

Codex Desktop là OpenAI Windows GUI. MetaEditor là native trên Windows
nên KHÔNG cần Wine.

### 4.1. Workspace setup

1. File → Open Folder → chọn `vibecodekit-mql5-ea/`.
2. Codex tự đọc `AGENTS.md` (xem section 2.1).
3. Mở terminal trong Codex Desktop:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -e .
   $env:METAEDITOR_BIN = "C:\Program Files\MetaTrader 5\metaeditor64.exe"
   python -m vibecodekit_mql5.doctor
   ```

### 4.2. MCP server qua Settings UI

Settings → MCP Servers → Add:

| Field | Value |
|-------|-------|
| Name | `metaeditor-bridge` |
| Command | `python.exe` |
| Args | `C:\path\to\vibecodekit-mql5-ea\mcp\metaeditor-bridge\server.py` |

Lặp lại cho `mt5-bridge`, `algo-forge-bridge`, và `vibecodekit-bridge`.
Với `algo-forge-bridge` thêm env var `ALGO_FORGE_API_KEY` trong section
"Environment".

### 4.3. mt5-bridge trên Windows

Trên Windows, `mt5-bridge` thực sự kết nối được MT5 desktop qua
package `MetaTrader5`:
```powershell
pip install MetaTrader5
```

Sau đó MT5 desktop phải đang chạy + đã login. mt5-bridge tự discover.

### 4.4. Tip dùng Codex Desktop

- Phím tắt `Ctrl+Shift+P` → "Codex: Ask" để chat về repo hiện tại.
- Drag `.mq5` file vào chat để Codex paste nội dung.

---

## 5. Cursor

Cursor là VS Code fork tích hợp Composer + Cmd-K.

### 5.1. `.cursor/rules/mql5-kit.mdc`

Tạo file `.cursor/rules/mql5-kit.mdc`:

```markdown
---
description: vibecodekit-mql5-ea — MQL5 EA development with 22 AP detectors and 64-cell quality matrix.
globs: ["**/*.mq5", "**/*.mqh", "scripts/vibecodekit_mql5/**"]
alwaysApply: false
---

# Quy tắc kit

1. Mọi `.mq5` mới phải qua `python -m vibecodekit_mql5.build <archetype>`.
2. KHÔNG `OrderSend` thô — dùng `CTrade` (AP-15).
3. KHÔNG `WebRequest` trong `OnTick` (AP-17).
4. KHÔNG `OrderSendAsync` thiếu `OnTradeTransaction` (AP-18).
5. KHÔNG `* 0.0001` hardcode — qua `CPipNormalizer` (AP-20).
6. ONNX phải validate qua Strategy Tester (AP-19).

Trước khi merge `.mq5`:
```
python -m vibecodekit_mql5.lint <file>
python -m vibecodekit_mql5.compile <file>
python -m vibecodekit_mql5.method_hiding_check <file> --build 5260
```

Workflow đầy đủ: `docs/USAGE-vi.md`.
```

### 5.2. MCP qua Cursor Settings

Cursor → Settings → Features → Model Context Protocol → Add Server:

```json
{
  "mcpServers": {
    "metaeditor-bridge": {
      "command": "python",
      "args": ["/path/to/vibecodekit-mql5-ea/mcp/metaeditor-bridge/server.py"]
    },
    "mt5-bridge": {
      "command": "python",
      "args": ["/path/to/vibecodekit-mql5-ea/mcp/mt5-bridge/server.py"]
    },
    "algo-forge-bridge": {
      "command": "python",
      "args": ["/path/to/vibecodekit-mql5-ea/mcp/algo-forge-bridge/server.py"],
      "env": {
        "ALGO_FORGE_API_KEY": "your-key-here"
      }
    },
    "vibecodekit-bridge": {
      "command": "python",
      "args": ["/path/to/vibecodekit-mql5-ea/mcp/vibecodekit-bridge/server.py"]
    }
  }
}
```

Restart Cursor sau khi thêm.

### 5.3. Chạy

- `Cmd+K` để inline edit với rule kit áp dụng.
- `Cmd+L` Composer chat: "Build EA wizard cho EURUSD H1 dùng kit pattern".

---

## 6. VS Code + Copilot Chat

Copilot Chat hỗ trợ MCP từ phiên bản 1.94+ (2024-10).

### 6.1. `.github/copilot-instructions.md`

Tạo file này ở root repo:

```markdown
# Copilot instructions — vibecodekit-mql5-ea

Đọc `docs/USAGE-vi.md` để biết workflow.

## Quy tắc bắt buộc khi sinh `.mq5`
1. Include `CTrade`, `CPipNormalizer`, `CRiskGuard` ở top.
2. Magic number qua `CMagicRegistry::Reserve()`.
3. Mọi `OrderSend` qua `CTrade`.
4. `WebRequest` chỉ trong `OnTimer`, không bao giờ `OnTick`.
5. Indicator handle release trong `OnDeinit`.

## Test
```
pytest tests/gates/ -q
python -m vibecodekit_mql5.audit
ruff check scripts/ mcp/
```

## 50 lệnh
Xem `docs/COMMANDS.md`. Gọi: `python -m vibecodekit_mql5.<name>`.
```

### 6.2. MCP qua `.vscode/mcp.json`

```json
{
  "servers": {
    "metaeditor-bridge": {
      "type": "stdio",
      "command": "python",
      "args": ["${workspaceFolder}/mcp/metaeditor-bridge/server.py"]
    },
    "mt5-bridge": {
      "type": "stdio",
      "command": "python",
      "args": ["${workspaceFolder}/mcp/mt5-bridge/server.py"]
    },
    "algo-forge-bridge": {
      "type": "stdio",
      "command": "python",
      "args": ["${workspaceFolder}/mcp/algo-forge-bridge/server.py"],
      "env": {
        "ALGO_FORGE_API_KEY": "${input:algo_forge_key}"
      }
    }
  },
  "inputs": [
    {
      "id": "algo_forge_key",
      "type": "promptString",
      "description": "Algo Forge API key",
      "password": true
    }
  ]
}
```

Restart VS Code. Copilot Chat sẽ tự discover MCP server.

### 6.3. Workspace recommendation

Cài extension:
- **Python** (Microsoft)
- **Even Better TOML** (cho tester.ini syntax)
- **YAML** (cho rri-personas)
- **markdownlint** (cho 28 reference docs)

---

## 7. MCP server config bảng tổng hợp

Tất cả 3 server đều dùng JSON-RPC 2.0 over stdio. Path:

```
/path/to/vibecodekit-mql5-ea/mcp/metaeditor-bridge/server.py
/path/to/vibecodekit-mql5-ea/mcp/mt5-bridge/server.py
/path/to/vibecodekit-mql5-ea/mcp/algo-forge-bridge/server.py
```

Thay `/path/to/` bằng path thật của bạn. Trên Windows dùng absolute
path với forward slash hoặc escaped backslash.

### Tool tổng quan

| Server | Số tool | Tool | Cần ENV |
|--------|---------|------|---------|
| metaeditor-bridge | 3 | `metaeditor.compile`, `metaeditor.parse_log`, `metaeditor.includes_resolve` | `METAEDITOR_BIN` (optional) |
| mt5-bridge | 10 (chỉ-đọc) | `mt5.symbols.list`, `mt5.symbol.info`, `mt5.rates.copy`, `mt5.tick.last`, `mt5.account.info`, `mt5.terminal.info`, `mt5.positions.list`, `mt5.positions.history`, `mt5.history.deals`, `mt5.market.book` | MT5 desktop chạy + login (Windows/Wine) |
| algo-forge-bridge | 6 | `forge.init`, `forge.clone`, `forge.commit`, `forge.pr.create`, `forge.pr.list`, `forge.repo.list` | `ALGO_FORGE_API_KEY` |

### Tại sao mt5-bridge READ-ONLY?

Cố ý — kit này KHÔNG ship trade-execution qua MCP để tránh risk LLM
gửi lệnh nhầm. Mọi trade phải qua EA `.ex5` đã compile + Strategy
Tester. Test `test_mt5_bridge_readonly_no_trade` grep code base verify
zero token `order_send`, `order_close`, `position_modify`, `position_close`.

---

## Trợ giúp / báo lỗi

Nếu có IDE/CLI khác (Zed, Aider, Helix, ...) cần config — mở issue
hoặc PR vào file này:
https://github.com/BuildMqlCodekit-01/vibecodekit-mql5-ea/issues
