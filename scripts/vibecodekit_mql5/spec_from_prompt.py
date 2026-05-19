"""Translate a free-text description into a valid ``ea-spec.yaml``.

This module is the bridge between the Devin **chat-driven build** playbook
(P2.2) and ``mql5-auto-build``. The playbook captures a single English (or
Vietnamese) sentence from the user — ``"build EA trend EURUSD H1 risk 0.5%
SL 30 TP 60 macd + sar"`` — and turns it into a YAML spec that
``spec_schema.validate`` accepts.

Design choices
--------------

* **Deterministic, regex-only**. The parser is intentionally rule-based so
  it can run inside an unattended pipeline (no LLM call, no network).
  Anything it can't parse is left at its schema default rather than
  hallucinated; ``--strict`` makes those gaps an error.

* **Stdlib only** — no ``pyyaml`` import here; the output is rendered via
  the same minimalist emitter used elsewhere in the kit so the module is
  safe to import in environments where pyyaml is missing.

* **Idempotent**. Re-running the parser on its own emitted YAML produces
  the same YAML (the round-trip is covered by tests).

Module layout — kept under the 400-LOC audit ceiling via two siblings:

* :mod:`vibecodekit_mql5.spec_from_prompt_recognisers` — recogniser
  tables + low-level match helpers for the original schema fields
  (preset, stack, symbol, timeframe, risk, signals, name).
* :mod:`vibecodekit_mql5.spec_from_prompt_blocks` — PR-2 / PR-8
  optional block matchers + YAML emitter helpers.

CLI
---

::

    mql5-spec-from-prompt "build EA trend EURUSD H1 risk 0.5%"

Writes the resulting spec to stdout. Use ``--out PATH`` to write to a file
and ``--strict`` to require every schema-mandatory field be inferable from
the prompt (default: fall back to schema defaults silently).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import build as build_mod
from . import spec_schema
from .spec_from_prompt_blocks import (
    BLOCK_MATCHERS,
    OPTIONAL_BLOCKS,
)
from .spec_from_prompt_recognisers import (
    PRESET_KEYWORDS_PATTERNS,
    STACK_KEYWORDS,
    SYMBOLS,
    TIMEFRAMES,
    looked_up,
    match_name,
    match_preset,
    match_risk,
    match_signals,
    match_stack,
    match_symbol,
    match_timeframe,
)
from .spec_from_prompt_yaml import emit_yaml_block


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptParseResult:
    """Structured outcome of parsing a single prompt.

    ``spec`` is a plain dict ready to be passed to ``spec_schema.validate``
    or rendered via ``to_yaml``. ``inferred`` lists the field paths that
    were filled from the prompt (vs falling back to schema defaults), so
    callers can surface "I assumed X because you didn't say" warnings.
    """

    spec: dict[str, object] = field(default_factory=dict)
    inferred: list[str] = field(default_factory=list)
    defaulted: list[str] = field(default_factory=list)


def parse(prompt: str) -> PromptParseResult:
    """Return a structured spec for ``prompt``.

    The parser never raises; gaps in the prompt are filled with the same
    defaults ``spec_schema.RiskConfig`` uses so the output is always
    schema-valid.
    """
    result = PromptParseResult()
    text = prompt.strip()
    if not text:
        # Fully blank prompts still produce a syntactically valid spec —
        # the caller can decide whether to accept that.
        result.spec = _default_spec()
        result.defaulted = ["everything"]
        return result

    preset, preset_stack = match_preset(text)
    stack = match_stack(text, fallback=preset_stack)
    # The schema enforces ``(preset, stack)`` compatibility, so we clamp
    # the prompt's stack hint to what the chosen preset actually supports.
    allowed = build_mod.PRESETS.get(preset, [])
    if allowed and stack not in allowed:
        stack = preset_stack if preset_stack in allowed else allowed[0]
    symbol = match_symbol(text)
    timeframe = match_timeframe(text)
    risk = match_risk(text)
    signals = match_signals(text)
    name = match_name(text, preset=preset, symbol=symbol, timeframe=timeframe)

    spec: dict[str, object] = {
        "name": name,
        "preset": preset,
        "stack": stack,
        "symbol": symbol,
        "timeframe": timeframe,
    }
    if risk:
        spec["risk"] = risk
    if signals:
        spec["signals"] = signals

    # PR-2 / PR-8 optional blocks — only added when the prompt actually
    # mentions them. Each matcher returns ``None`` if it has nothing to
    # contribute, preserving back-compat with prompts that don't mention
    # any of these features.
    optional_blocks = {
        name: fn(text) for name, fn in BLOCK_MATCHERS.items()
    }
    for block_name, block_value in optional_blocks.items():
        if block_value:
            spec[block_name] = block_value

    # Track what we inferred vs what we defaulted, for transparency.
    inferred: list[str] = ["name"]
    for k, v in (
        ("preset", looked_up(text, PRESET_KEYWORDS_PATTERNS)),
        ("stack",  looked_up(text, STACK_KEYWORDS)),
        ("symbol", any(s.upper() in text.upper() for s in SYMBOLS)),
        ("timeframe", any(tf in text.upper() for tf in TIMEFRAMES)),
        ("risk",   bool(risk)),
        ("signals",bool(signals)),
    ):
        if v:
            inferred.append(k)
        else:
            result.defaulted.append(k)
    for block_name in OPTIONAL_BLOCKS:
        if optional_blocks[block_name]:
            inferred.append(block_name)
        else:
            result.defaulted.append(block_name)
    result.spec = spec
    result.inferred = inferred
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Defaults + YAML emitter
# ─────────────────────────────────────────────────────────────────────────────

def _default_spec() -> dict[str, object]:
    """Schema-valid spec used when the prompt is completely empty."""
    return {
        "name": "StdlibEurusdH1",
        "preset": "stdlib",
        "stack": "netting",
        "symbol": "EURUSD",
        "timeframe": "H1",
    }


def to_yaml(spec: dict[str, object]) -> str:
    """Emit a minimal YAML serialisation of ``spec``.

    Only handles the subset of types this module produces: strings, ints,
    floats, lists of dicts, plus the dict-shaped PR-2 / PR-8 optional
    blocks. Output is stable so test fixtures don't churn.
    """
    lines: list[str] = []
    for key in ("name", "preset", "stack", "symbol", "timeframe", "mode"):
        if key in spec:
            lines.append(f"{key}: {spec[key]}")
    if "risk" in spec:
        risk = spec["risk"]
        assert isinstance(risk, dict)
        lines.append("risk:")
        for rk in (
            "per_trade_pct", "daily_loss_pct", "max_spread_pips",
            "max_open_positions", "sl_pips", "tp_pips",
        ):
            if rk in risk:
                lines.append(f"  {rk}: {risk[rk]}")
    if "signals" in spec:
        sigs = spec["signals"]
        lines.append("signals:")
        if isinstance(sigs, dict):
            if "logic" in sigs:
                lines.append(f"  logic: {sigs['logic']}")
            entries = sigs.get("list", [])
            if entries:
                lines.append("  list:")
                for entry in entries:
                    assert isinstance(entry, dict)
                    (k, v), = entry.items()
                    lines.append(f"    - {k}: {v}")
        else:
            assert isinstance(sigs, list)
            for entry in sigs:
                assert isinstance(entry, dict)
                (k, v), = entry.items()
                lines.append(f"  - {k}: {v}")

    # PR-2 / PR-8 optional blocks — emit in canonical order so test
    # fixtures don't churn. Skip any block not present in the spec.
    for block_name in OPTIONAL_BLOCKS:
        if block_name not in spec:
            continue
        block = spec[block_name]
        assert isinstance(block, dict), block_name
        lines.append(f"{block_name}:")
        lines.extend(emit_yaml_block(block, indent=2))
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="mql5-spec-from-prompt",
        description="Translate a free-text EA description into ea-spec.yaml.",
    )
    p.add_argument("prompt", help="Natural-language description of the EA")
    p.add_argument(
        "--out", type=Path,
        help="Write the spec here instead of stdout.",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="Exit non-zero if the prompt is missing schema-mandatory fields.",
    )
    p.add_argument(
        "--explain", action="store_true",
        help="Print a one-line summary of what was inferred vs defaulted.",
    )
    args = p.parse_args(argv)

    result = parse(args.prompt)
    # Run the spec through the real validator so we never emit garbage.
    spec_schema.validate(result.spec, valid_presets=build_mod.PRESETS)

    if args.strict:
        # Strictness is about whether the operator gave us enough to ground
        # the build. ``stack`` is implied by ``preset`` and ``name`` is
        # always synthesised from the other three, so we only insist on the
        # three fields a human would normally type into the prompt.
        required_for_strict = {"preset", "symbol", "timeframe"}
        missing = required_for_strict & set(result.defaulted)
        if missing:
            print(
                f"missing fields the prompt didn't mention: {sorted(missing)}",
                file=sys.stderr,
            )
            return 1

    yaml_text = to_yaml(result.spec)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(yaml_text, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(yaml_text)

    if args.explain:
        msg = (
            f"inferred: {result.inferred}  "
            f"defaulted: {result.defaulted}"
        )
        print(msg, file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
