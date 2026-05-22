"""mql5-build — render a Phase A scaffold into a fresh project directory.

Usage:
    mql5-build <preset> --name X --symbol Y --tf Z [--stack S] [--out DIR]

Phase A presets (per docs/phase-A-spec.md):
    stdlib              stacks: netting, hedging, python-bridge
    wizard-composable   stacks: netting
    portfolio-basket    stacks: netting, hedging
    ml-onnx             stacks: python-bridge

What it does:
    1. Locate <scaffolds_root>/<preset>/<stack>/ — defaults to <repo>/scaffolds.
    2. Render every file under it, substituting {{NAME}}, {{SYMBOL}}, {{TF}},
       {{MAGIC}} into both filenames and content.
    3. Refuse to overwrite an existing output dir unless --force.
    4. Copy the 3 Include/ .mqh files next to the rendered .mq5 so the project
       is self-contained and `mql5-compile` Just Works.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCAFFOLDS = REPO_ROOT / "scaffolds"
DEFAULT_INCLUDE   = REPO_ROOT / "Include"

PHASE_A_PRESETS: dict[str, list[str]] = {
    "stdlib":            ["netting", "hedging", "python-bridge"],
    "wizard-composable": ["netting"],
    "portfolio-basket":  ["netting", "hedging"],
    "ml-onnx":           ["python-bridge"],
}

# Phase D adds 14 additional scaffolds (1 HFT async, 3 LLM bridge variants,
# 10 strategy archetypes). Keep this dict separate so Phase A tests remain
# untouched but consumers see the combined map via PRESETS below.
PHASE_D_PRESETS: dict[str, list[str]] = {
    "hft-async":          ["netting"],
    "service-llm-bridge": ["cloud-api", "self-hosted-ollama", "embedded-onnx-llm"],
    "trend":              ["netting"],
    "mean-reversion":     ["hedging"],
    "breakout":           ["netting"],
    "hedging-multi":      ["hedging"],
    "news-trading":       ["netting"],
    "arbitrage-stat":     ["python-bridge"],
    "scalping":           ["hedging"],
    "library":            ["netting"],
    "indicator-only":     ["netting"],
    "grid":               ["hedging"],
    "dca":                ["hedging"],
}

# Phase E adds the MQL5 Service archetype (build 5320+). Services are
# chart-less background programs (data collectors, LLM/REST pollers,
# VPS canaries) — they live alongside EAs but never call CTrade, so
# they intentionally bypass the Phase-A risk-guard wiring.
PHASE_E_PRESETS: dict[str, list[str]] = {
    "service":            ["standalone"],
}

PRESETS: dict[str, list[str]] = {
    **PHASE_A_PRESETS,
    **PHASE_D_PRESETS,
    **PHASE_E_PRESETS,
}


@dataclass
class BuildRequest:
    preset: str
    name: str
    symbol: str
    tf: str
    stack: str
    out_dir: Path
    scaffolds_root: Path
    include_root: Path
    force: bool = False
    # Optional per-build template variables, e.g. risk overrides emitted by
    # ``spec_schema.RiskConfig.as_template_vars``. Each key/value is replaced
    # in scaffold text as ``{{KEY}}`` -> ``value``. Empty by default so the
    # existing callers (``mql5-build`` CLI, Phase A tests) keep their old
    # behaviour: scaffolds with no extra placeholders render identically.
    extras: dict[str, str] = field(default_factory=dict)
    # Optional companion files to write into ``out_dir`` after the scaffold
    # has been rendered, e.g. ``signals.md`` describing the indicator chain
    # the user asked for. ``(rel_path, content)`` tuples; UTF-8 text only.
    extra_files: list[tuple[str, str]] = field(default_factory=list)


def _magic_for(name: str) -> int:
    """Deterministic 5-digit-ish magic from the EA name. 70000–79999 range."""
    h = int(hashlib.sha1(name.encode("utf-8")).hexdigest(), 16)
    return 70000 + (h % 10000)


# Default values for spec-driven placeholders. Used when a scaffold template
# references e.g. ``{{RISK_MONEY}}`` but the caller didn't supply ``extras``
# (typical for the bare ``mql5-build`` CLI). These match the previous hardcoded
# numbers in stdlib/netting so the rendered output is identical to v1.0.1.
_EXTRA_DEFAULTS: dict[str, str] = {
    "RISK_MONEY":         "100.0",
    "RISK_PER_TRADE_PCT": "0.5",
    "SL_PIPS":            "30",
    "TP_PIPS":            "60",
    "DAILY_LOSS_FRAC":    "0.05",
    "DAILY_LOSS_PCT":     "5.0",
    "MAX_SPREAD_PIPS":    "3.0",
    "MAX_POSITIONS":      "3",
}


def _render(text: str, req: BuildRequest, magic: int) -> str:
    out = (
        text.replace("{{NAME}}",   req.name)
            .replace("{{SYMBOL}}", req.symbol)
            .replace("{{TF}}",     req.tf)
            .replace("{{MAGIC}}",  str(magic))
    )
    # Apply spec-driven overrides first, then fill any leftover defaults so
    # scaffolds that reference {{RISK_MONEY}} / {{SL_PIPS}} / ... still render
    # correctly when the caller (e.g. plain ``mql5-build`` CLI) didn't pass an
    # ``extras`` dict. Templates that don't reference a given placeholder
    # simply ignore it, keeping the change backward-compatible.
    merged: dict[str, str] = {**_EXTRA_DEFAULTS, **req.extras}
    for key, value in merged.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def _render_name(name: str, req: BuildRequest) -> str:
    return name.replace("EAName", req.name).replace("{{NAME}}", req.name)


# Scaffold files with these suffixes are treated as binary: copied as raw
# bytes, no template substitution. Everything else is text + rendered.
_BINARY_SUFFIXES = frozenset({".onnx", ".png", ".jpg", ".jpeg", ".gif",
                              ".ico", ".bin", ".dat"})


def build(req: BuildRequest) -> Path:
    if req.preset not in PRESETS:
        raise ValueError(f"unknown preset {req.preset!r}; valid: {sorted(PRESETS)}")
    if req.stack not in PRESETS[req.preset]:
        raise ValueError(
            f"preset {req.preset!r} does not support stack {req.stack!r}; "
            f"valid: {PRESETS[req.preset]}"
        )

    src_dir = req.scaffolds_root / req.preset / req.stack
    if not src_dir.is_dir():
        raise FileNotFoundError(f"scaffold not found: {src_dir}")

    if req.out_dir.exists():
        if not req.force:
            raise FileExistsError(f"refusing to overwrite {req.out_dir} (use --force)")
        shutil.rmtree(req.out_dir)
    req.out_dir.mkdir(parents=True)

    magic = _magic_for(req.name)
    for src in src_dir.rglob("*"):
        if src.is_dir():
            continue
        # FLOW-{vi,en}.md are authoring artifacts consumed by the docs
        # renderer (``ea_docs_semantics.load_flow_narrative``). They are
        # injected — already placeholder-substituted — into the
        # generated ``.docs.html`` / ``.docs.md``, so the raw template
        # should never reach the end-user's build folder.
        if src.name in ("FLOW-vi.md", "FLOW-en.md"):
            continue
        rel = src.relative_to(src_dir)
        dst = req.out_dir / Path(*[_render_name(p, req) for p in rel.parts])
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Binary scaffold assets (.onnx model stubs, .png images, etc.)
        # must be copied byte-for-byte. Text scaffolds get template
        # substitution via _render().
        if src.suffix.lower() in _BINARY_SUFFIXES:
            dst.write_bytes(src.read_bytes())
        else:
            text = src.read_text(encoding="utf-8", errors="replace")
            dst.write_text(_render(text, req, magic), encoding="utf-8")

    # Co-locate Include/.mqh files so /mql5-compile resolves them locally.
    if req.include_root.is_dir():
        for inc in req.include_root.glob("*.mqh"):
            (req.out_dir / inc.name).write_bytes(inc.read_bytes())

    # Spec-driven companion files (e.g. signals.md describing the indicator
    # chain the user asked for). Written after the scaffold so they can
    # deliberately shadow any scaffold file of the same name.
    for rel_path, content in req.extra_files:
        dst = req.out_dir / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(content, encoding="utf-8")
    return req.out_dir


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mql5-build", description=__doc__.splitlines()[0])
    p.add_argument("preset", choices=sorted(PRESETS))
    p.add_argument("--name",   required=True)
    p.add_argument("--symbol", required=True)
    p.add_argument("--tf",     required=True)
    p.add_argument("--stack",  default=None,
                   help="default = first stack supported by preset")
    p.add_argument("--out",    default=None,
                   help="output directory (default: ./<name>)")
    p.add_argument("--scaffolds-root", default=str(DEFAULT_SCAFFOLDS))
    p.add_argument("--include-root",   default=str(DEFAULT_INCLUDE))
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    stack = args.stack or PRESETS[args.preset][0]
    out_dir = Path(args.out) if args.out else Path.cwd() / args.name
    req = BuildRequest(
        preset=args.preset,
        name=args.name,
        symbol=args.symbol,
        tf=args.tf,
        stack=stack,
        out_dir=out_dir,
        scaffolds_root=Path(args.scaffolds_root),
        include_root=Path(args.include_root),
        force=args.force,
    )
    try:
        out = build(req)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        print(f"mql5-build: {exc}", file=sys.stderr)
        return 2
    print(f"built {req.preset}/{req.stack} → {out}")
    for f in sorted(out.rglob("*")):
        if f.is_file():
            print(f"  {f.relative_to(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
