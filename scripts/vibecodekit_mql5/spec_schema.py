"""``ea-spec.yaml`` schema validator.

This is the structured DSL behind ``mql5-auto-build --spec ea.yaml``. The MVP
schema covers the four blocks needed to render a customised stdlib/netting
project:

    name:        EA name
    preset:      scaffold preset (stdlib, trend, ml-onnx, ...)
    stack:       scaffold stack (netting, hedging, python-bridge, ...)
    symbol:      trading symbol
    timeframe:   H1 / M15 / ...
    mode:        permission mode (personal/team/enterprise, default: personal)
    risk:
      per_trade_pct:    optional, default 0.5  — 0 < x ≤ 5.0
      daily_loss_pct:   optional, default 5.0  — 0 < x ≤ 20.0
      max_spread_pips:  optional, default 3.0  — 0 < x ≤ 50.0
      max_open_positions: optional, default 3  — 1 ≤ n ≤ 100
      sl_pips:          optional, default 30   — 1 ≤ n ≤ 10000
      tp_pips:          optional, default 60   — 1 ≤ n ≤ 10000
    signals:           # MVP: documented in <out_dir>/signals.md; codegen later
      - kind:  macd | sar | rsi | ema_cross | bbands | atr_break
        ...indicator-specific params...
      logic: AND | OR   # default AND
    filters:           # optional, MVP: documented only
      - kind: time_window | news_blackout
        ...
    hooks:             # optional, MVP: documented only
      on_init: [...]
      on_deinit: [...]

The validator is pure stdlib (no Pydantic) so it stays lightweight. Errors are
collected and raised together so the caller sees every problem in one shot
instead of fix-and-retry per field.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Iterable


VALID_MODES: frozenset[str] = frozenset({"personal", "team", "enterprise"})
VALID_SIGNAL_KINDS: frozenset[str] = frozenset({
    "macd", "sar", "rsi", "ema_cross", "bbands", "atr_break",
})
VALID_FILTER_KINDS: frozenset[str] = frozenset({"time_window", "news_blackout"})
VALID_SIGNAL_LOGIC: frozenset[str] = frozenset({"AND", "OR"})

REQUIRED_TOP_FIELDS: tuple[str, ...] = (
    "name", "preset", "stack", "symbol", "timeframe",
)


class SpecValidationError(ValueError):
    """Raised when ``ea-spec.yaml`` is structurally invalid.

    The message lists every problem found, joined by ``"; "`` so a single
    ``str(exc)`` shows the operator everything to fix.
    """


@dataclass
class RiskConfig:
    """Risk-management overrides for the scaffolded EA inputs."""

    per_trade_pct: float = 0.5
    daily_loss_pct: float = 5.0
    max_spread_pips: float = 3.0
    max_open_positions: int = 3
    sl_pips: int = 30
    tp_pips: int = 60

    def as_template_vars(self) -> dict[str, str]:
        """Render risk fields as ``{{KEY}}`` string substitutions.

        Returns a dict ready to merge into ``build._render``'s replace table.
        Values are strings so the renderer can do straight string interpolation.
        """
        # `0.05` style daily-loss percent (legacy default) vs the new percent
        # representation (5.0 == 5%). Keep both keys so older templates that
        # still reference {{DAILY_LOSS_FRAC}} continue to work alongside the
        # new {{DAILY_LOSS_PCT}}.
        return {
            "RISK_PER_TRADE_PCT": _fmt_float(self.per_trade_pct),
            "DAILY_LOSS_PCT": _fmt_float(self.daily_loss_pct),
            "DAILY_LOSS_FRAC": _fmt_float(self.daily_loss_pct / 100.0),
            "MAX_SPREAD_PIPS": _fmt_float(self.max_spread_pips),
            "MAX_POSITIONS": str(int(self.max_open_positions)),
            "SL_PIPS": str(int(self.sl_pips)),
            "TP_PIPS": str(int(self.tp_pips)),
            # Legacy: stdlib/netting still has `InpRiskMoney = 100.0` hardcoded.
            # Derive a money figure from the percent for cosmetic parity until
            # the include lib starts respecting per_trade_pct directly (P1.x).
            "RISK_MONEY": _fmt_float(self.per_trade_pct * 200.0),
        }


@dataclass
class SignalConfig:
    """A single indicator entry inside the ``signals:`` list."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.params}


@dataclass
class FilterConfig:
    """A single entry inside the ``filters:`` list."""

    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.params}


@dataclass
class PropFirmConfig:
    """Prop-firm compliance constraints (FTMO/MFF/FundedNext-style).

    All fields are optional. When omitted the auto-build pipeline treats
    the section as absent and skips any prop-firm-specific safeguards.
    Templates that don't reference these fields ignore the section
    entirely — the block is purely additive.
    """

    daily_dd_pct: float | None = None
    max_dd_pct: float | None = None
    profit_target_pct: float | None = None
    news_block_min: int | None = None
    weekend_flat: bool = False
    copy_trading_lock: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v is not False}


@dataclass
class TimeExitConfig:
    """Time-based exit constraints layered on top of price-based SL/TP.

    All fields are optional.
    """

    close_on_friday: bool = False
    friday_close_hour: int | None = None
    max_trade_hours: int | None = None
    session_end_hour: int | None = None
    session_start_hour: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v is not False}


@dataclass
class StealthConfig:
    """Broker-side anti-pattern obfuscation switches.

    All fields are optional. NB: stealth tactics interact with broker
    ToS — enabling them is a policy decision, not a code one. The kit
    only validates shape; ship/no-ship is a human call.
    """

    randomize_slippage_pips: float | None = None
    randomize_comment_pool: list[str] = field(default_factory=list)
    randomize_lot_jitter_pct: float | None = None
    split_orders: bool = False
    avoid_round_numbers: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.randomize_slippage_pips is not None:
            out["randomize_slippage_pips"] = self.randomize_slippage_pips
        if self.randomize_comment_pool:
            out["randomize_comment_pool"] = list(self.randomize_comment_pool)
        if self.randomize_lot_jitter_pct is not None:
            out["randomize_lot_jitter_pct"] = self.randomize_lot_jitter_pct
        if self.split_orders:
            out["split_orders"] = True
        if self.avoid_round_numbers:
            out["avoid_round_numbers"] = True
        return out


@dataclass
class EaSpec:
    """Validated spec ready to feed into the build/lint/compile pipeline."""

    name: str
    preset: str
    stack: str
    symbol: str
    timeframe: str
    mode: str = "personal"
    risk: RiskConfig = field(default_factory=RiskConfig)
    signals: list[SignalConfig] = field(default_factory=list)
    signal_logic: str = "AND"
    filters: list[FilterConfig] = field(default_factory=list)
    hooks: dict[str, list[str]] = field(default_factory=dict)
    prop_firm: PropFirmConfig | None = None
    time_exit: TimeExitConfig | None = None
    stealth: StealthConfig | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "preset": self.preset,
            "stack": self.stack,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "mode": self.mode,
            "risk": asdict(self.risk),
            "signals": [s.to_dict() for s in self.signals],
            "signal_logic": self.signal_logic,
            "filters": [f.to_dict() for f in self.filters],
            "hooks": dict(self.hooks),
        }
        if self.prop_firm is not None:
            out["prop_firm"] = self.prop_firm.to_dict()
        if self.time_exit is not None:
            out["time_exit"] = self.time_exit.to_dict()
        if self.stealth is not None:
            out["stealth"] = self.stealth.to_dict()
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_float(value: float) -> str:
    """Render a float the way MQL5 ``input`` declarations expect it.

    Floats need a decimal point so MetaEditor parses them as ``double`` and not
    ``int``. ``1.0`` → ``"1.0"``, ``1.5`` → ``"1.5"``, ``0.05`` → ``"0.05"``.
    """
    s = f"{float(value):.6f}".rstrip("0")
    return s + "0" if s.endswith(".") else s


def _check_str(errors: list[str], spec: dict[str, Any], key: str) -> None:
    value = spec.get(key)
    if not isinstance(value, str) or not value:
        errors.append(f"spec.{key} must be a non-empty string")


def _check_num_range(
    errors: list[str],
    block: str,
    key: str,
    value: Any,
    *,
    min_excl: float,
    max_incl: float,
    is_int: bool = False,
) -> None:
    if is_int:
        if not isinstance(value, int) or isinstance(value, bool):
            errors.append(f"{block}.{key} must be an integer, got {type(value).__name__}")
            return
    else:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            errors.append(f"{block}.{key} must be a number, got {type(value).__name__}")
            return
    if not (min_excl < float(value) <= max_incl):
        errors.append(
            f"{block}.{key}={value!r} must satisfy {min_excl} < x <= {max_incl}"
        )


def _validate_risk(errors: list[str], raw: Any) -> RiskConfig:
    if raw is None:
        return RiskConfig()
    if not isinstance(raw, dict):
        errors.append(f"spec.risk must be a mapping, got {type(raw).__name__}")
        return RiskConfig()
    cfg = RiskConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    unknown = set(raw.keys()) - valid_keys
    if unknown:
        errors.append(
            f"spec.risk has unknown keys: {sorted(unknown)} "
            f"(valid: {sorted(valid_keys)})"
        )
    bounds: dict[str, tuple[float, float, bool]] = {
        "per_trade_pct":      (0.0, 5.0, False),
        "daily_loss_pct":     (0.0, 20.0, False),
        "max_spread_pips":    (0.0, 50.0, False),
        "max_open_positions": (0.0, 100.0, True),
        "sl_pips":            (0.0, 10000.0, True),
        "tp_pips":            (0.0, 10000.0, True),
    }
    for k, (lo, hi, is_int) in bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        _check_num_range(errors, "spec.risk", k, raw[k],
                         min_excl=lo, max_incl=hi, is_int=is_int)
        if len(errors) == before:
            # value passed type + range checks — keep it on the cfg dataclass
            setattr(cfg, k, raw[k])
    return cfg


def _validate_signals(errors: list[str], raw: Any) -> tuple[list[SignalConfig], str]:
    if raw is None:
        return [], "AND"
    logic = "AND"
    items: Iterable[Any]
    if isinstance(raw, dict):
        # `signals: { list: [...], logic: AND }` shorthand for future-proofing.
        if "logic" in raw:
            logic = str(raw["logic"]).upper()
            if logic not in VALID_SIGNAL_LOGIC:
                errors.append(
                    f"spec.signals.logic={raw['logic']!r} not in {sorted(VALID_SIGNAL_LOGIC)}"
                )
                logic = "AND"
        items = raw.get("list") or raw.get("items") or []
    elif isinstance(raw, list):
        items = raw
    else:
        errors.append(f"spec.signals must be a list or mapping, got {type(raw).__name__}")
        return [], "AND"

    out: list[SignalConfig] = []
    for idx, entry in enumerate(items):
        if not isinstance(entry, dict):
            errors.append(f"spec.signals[{idx}] must be a mapping, got {type(entry).__name__}")
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in VALID_SIGNAL_KINDS:
            errors.append(
                f"spec.signals[{idx}].kind={kind!r} not in {sorted(VALID_SIGNAL_KINDS)}"
            )
            continue
        params = {k: v for k, v in entry.items() if k != "kind"}
        out.append(SignalConfig(kind=kind, params=params))
    return out, logic


def _validate_filters(errors: list[str], raw: Any) -> list[FilterConfig]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append(f"spec.filters must be a list, got {type(raw).__name__}")
        return []
    out: list[FilterConfig] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            errors.append(f"spec.filters[{idx}] must be a mapping, got {type(entry).__name__}")
            continue
        kind = entry.get("kind")
        if not isinstance(kind, str) or kind not in VALID_FILTER_KINDS:
            errors.append(
                f"spec.filters[{idx}].kind={kind!r} not in {sorted(VALID_FILTER_KINDS)}"
            )
            continue
        params = {k: v for k, v in entry.items() if k != "kind"}
        out.append(FilterConfig(kind=kind, params=params))
    return out


def _validate_hooks(errors: list[str], raw: Any) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        errors.append(f"spec.hooks must be a mapping, got {type(raw).__name__}")
        return {}
    out: dict[str, list[str]] = {}
    for stage, body in raw.items():
        if not isinstance(stage, str):
            errors.append(f"spec.hooks key {stage!r} must be a string")
            continue
        if not isinstance(body, list):
            errors.append(f"spec.hooks.{stage} must be a list, got {type(body).__name__}")
            continue
        out[stage] = [str(line) for line in body]
    return out


def _check_unknown_keys(
    errors: list[str], block: str, raw: dict[str, Any], valid: set[str],
) -> None:
    unknown = set(raw.keys()) - valid
    if unknown:
        errors.append(
            f"spec.{block} has unknown keys: {sorted(unknown)} "
            f"(valid: {sorted(valid)})"
        )


def _validate_prop_firm(errors: list[str], raw: Any) -> PropFirmConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.prop_firm must be a mapping, got {type(raw).__name__}")
        return None
    cfg = PropFirmConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    _check_unknown_keys(errors, "prop_firm", raw, valid_keys)
    bounds: dict[str, tuple[float, float, bool]] = {
        "daily_dd_pct":      (0.0, 100.0, False),
        "max_dd_pct":        (0.0, 100.0, False),
        "profit_target_pct": (0.0, 100.0, False),
        "news_block_min":    (0.0, 1440.0, True),
    }
    for k, (lo, hi, is_int) in bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        _check_num_range(errors, "spec.prop_firm", k, raw[k],
                         min_excl=lo, max_incl=hi, is_int=is_int)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    for k in ("weekend_flat", "copy_trading_lock"):
        if k in raw:
            v = raw[k]
            if not isinstance(v, bool):
                errors.append(f"spec.prop_firm.{k} must be a bool, got {type(v).__name__}")
                continue
            setattr(cfg, k, v)
    return cfg


def _validate_time_exit(errors: list[str], raw: Any) -> TimeExitConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.time_exit must be a mapping, got {type(raw).__name__}")
        return None
    cfg = TimeExitConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    _check_unknown_keys(errors, "time_exit", raw, valid_keys)
    int_bounds: dict[str, tuple[float, float]] = {
        # 0-23 for hours (allow 0); use min_excl=-1 so 0 passes.
        "friday_close_hour":  (-1.0, 23.0),
        "session_end_hour":   (-1.0, 23.0),
        "session_start_hour": (-1.0, 23.0),
        # max_trade_hours must be positive (a 0-hour cap is meaningless).
        "max_trade_hours":    (0.0, 720.0),
    }
    for k, (lo, hi) in int_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        _check_num_range(errors, "spec.time_exit", k, raw[k],
                         min_excl=lo, max_incl=hi, is_int=True)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "close_on_friday" in raw:
        v = raw["close_on_friday"]
        if not isinstance(v, bool):
            errors.append(
                f"spec.time_exit.close_on_friday must be a bool, got {type(v).__name__}"
            )
        else:
            cfg.close_on_friday = v
    return cfg


def _validate_stealth(errors: list[str], raw: Any) -> StealthConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        errors.append(f"spec.stealth must be a mapping, got {type(raw).__name__}")
        return None
    cfg = StealthConfig()
    valid_keys = {f.name for f in cfg.__dataclass_fields__.values()}
    _check_unknown_keys(errors, "stealth", raw, valid_keys)
    float_bounds: dict[str, tuple[float, float]] = {
        "randomize_slippage_pips":  (0.0, 100.0),
        "randomize_lot_jitter_pct": (0.0, 50.0),
    }
    for k, (lo, hi) in float_bounds.items():
        if k not in raw:
            continue
        before = len(errors)
        _check_num_range(errors, "spec.stealth", k, raw[k],
                         min_excl=lo, max_incl=hi, is_int=False)
        if len(errors) == before:
            setattr(cfg, k, raw[k])
    if "randomize_comment_pool" in raw:
        pool = raw["randomize_comment_pool"]
        if not isinstance(pool, list) or not all(isinstance(p, str) for p in pool):
            errors.append("spec.stealth.randomize_comment_pool must be a list of strings")
        else:
            cfg.randomize_comment_pool = list(pool)
    for k in ("split_orders", "avoid_round_numbers"):
        if k in raw:
            v = raw[k]
            if not isinstance(v, bool):
                errors.append(f"spec.stealth.{k} must be a bool, got {type(v).__name__}")
                continue
            setattr(cfg, k, v)
    return cfg


def validate(
    spec: dict[str, Any],
    *,
    valid_presets: dict[str, list[str]] | None = None,
) -> EaSpec:
    """Validate a parsed spec dict and return an ``EaSpec``.

    ``valid_presets`` is the same shape as ``build.PRESETS`` — when supplied,
    the validator additionally checks that ``preset`` is known and ``stack``
    is allowed for that preset. Pass ``None`` to skip those checks (handy for
    pure schema-only unit tests).

    Raises :class:`SpecValidationError` collecting *every* problem at once.
    """
    errors: list[str] = []
    if not isinstance(spec, dict):
        raise SpecValidationError(f"spec must be a mapping, got {type(spec).__name__}")

    missing = [k for k in REQUIRED_TOP_FIELDS if k not in spec]
    if missing:
        # Match the legacy auto_build error string so existing consumers
        # (including downstream tooling that greps the message) keep working.
        errors.append(f"spec missing required fields: {missing}")
    for k in REQUIRED_TOP_FIELDS:
        if k in spec:
            _check_str(errors, spec, k)

    mode = spec.get("mode", "personal")
    if not isinstance(mode, str) or mode not in VALID_MODES:
        errors.append(f"spec.mode={mode!r} not in {sorted(VALID_MODES)}")
        mode = "personal"

    if valid_presets is not None and isinstance(spec.get("preset"), str):
        preset = spec["preset"]
        if preset not in valid_presets:
            errors.append(
                f"spec.preset={preset!r} not in {sorted(valid_presets)}"
            )
        else:
            stack = spec.get("stack")
            if isinstance(stack, str) and stack not in valid_presets[preset]:
                errors.append(
                    f"spec.stack={stack!r} not supported by preset {preset!r}; "
                    f"valid: {valid_presets[preset]}"
                )

    risk = _validate_risk(errors, spec.get("risk"))
    signals, signal_logic = _validate_signals(errors, spec.get("signals"))
    filters = _validate_filters(errors, spec.get("filters"))
    hooks = _validate_hooks(errors, spec.get("hooks"))
    prop_firm = _validate_prop_firm(errors, spec.get("prop_firm"))
    time_exit = _validate_time_exit(errors, spec.get("time_exit"))
    stealth = _validate_stealth(errors, spec.get("stealth"))

    unknown_top = set(spec.keys()) - {
        *REQUIRED_TOP_FIELDS, "mode", "risk", "signals", "filters", "hooks",
        "prop_firm", "time_exit", "stealth",
    }
    if unknown_top:
        errors.append(f"spec has unknown top-level keys: {sorted(unknown_top)}")

    if errors:
        raise SpecValidationError("; ".join(errors))

    return EaSpec(
        name=spec["name"],
        preset=spec["preset"],
        stack=spec["stack"],
        symbol=spec["symbol"],
        timeframe=spec["timeframe"],
        mode=mode,
        risk=risk,
        signals=signals,
        signal_logic=signal_logic,
        filters=filters,
        hooks=hooks,
        prop_firm=prop_firm,
        time_exit=time_exit,
        stealth=stealth,
    )


def render_signals_doc(spec: EaSpec) -> str:
    """Render the ``signals.md`` companion file written alongside the EA.

    MVP: we do NOT generate MQL5 signal code yet — that's the P1.x fan-out. For
    now we emit a Markdown file documenting what the user asked for, so the
    operator (or a future codegen pass) has the rules in one canonical place.
    """
    lines: list[str] = [
        f"# Signals for {spec.name}",
        "",
        f"- Symbol: `{spec.symbol}`",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Logic: **{spec.signal_logic}** (combine all signals with this operator)",
        "",
    ]
    if not spec.signals:
        lines.append("_No signals declared in spec.signals._")
    else:
        lines.append("## Indicators")
        lines.append("")
        for idx, sig in enumerate(spec.signals, start=1):
            lines.append(f"### {idx}. `{sig.kind}`")
            if sig.params:
                lines.append("")
                for k, v in sig.params.items():
                    lines.append(f"- `{k}`: `{v}`")
            lines.append("")
    if spec.filters:
        lines.append("## Filters")
        lines.append("")
        for idx, flt in enumerate(spec.filters, start=1):
            lines.append(f"- {idx}. `{flt.kind}` — {flt.params}")
        lines.append("")
    lines.append(
        "_This file is generated by `mql5-auto-build` from the spec.signals "
        "block. MQL5 code-generation for these signals is deferred to a "
        "future iteration; for now, use this doc as the spec to hand-code "
        "the entry/exit logic in `{name}.mq5`._".format(name=spec.name)
    )
    return "\n".join(lines) + "\n"
