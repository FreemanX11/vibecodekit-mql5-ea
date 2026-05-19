"""Phase E unit tests — ``spec_schema`` DSL validator (P1.1).

Covers the spec validator behind ``mql5-auto-build --spec ea.yaml``:

* required top-level fields
* mode whitelist
* preset / stack cross-check
* risk-block bounds + unknown-key rejection
* signals/filters kind whitelists
* hooks shape
* ``RiskConfig.as_template_vars`` keys + numeric formatting
* ``render_signals_doc`` content
* end-to-end: rendered scaffold reflects spec.risk overrides + emits signals.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from vibecodekit_mql5 import auto_build, build as build_mod, spec_schema  # noqa: E402


MINIMAL = {
    "name": "SpecSchemaEA",
    "preset": "stdlib",
    "stack": "netting",
    "symbol": "EURUSD",
    "timeframe": "H1",
}


# ─────────────────────────────────────────────────────────────────────────────
# Required fields + types
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_happy_path_returns_easpec() -> None:
    out = spec_schema.validate(dict(MINIMAL))
    assert isinstance(out, spec_schema.EaSpec)
    assert out.name == "SpecSchemaEA"
    assert out.mode == "personal"  # default
    assert out.signal_logic == "AND"  # default
    assert out.signals == []
    assert out.filters == []
    assert out.hooks == {}


def test_validate_collects_all_errors_in_one_pass() -> None:
    bad = {
        "name": "",
        "preset": "totally-not-real",
        "symbol": "",
        # missing timeframe AND stack on purpose
        "mode": "dictator",
        "risk": {"per_trade_pct": 999.0, "max_open_positions": -1},
        "signals": [{"kind": "bogus"}],
    }
    with pytest.raises(spec_schema.SpecValidationError) as exc:
        spec_schema.validate(bad, valid_presets=build_mod.PRESETS)
    msg = str(exc.value)
    # Required-fields message preserved (legacy auto_build wording).
    assert "missing required fields" in msg
    assert "stack" in msg and "timeframe" in msg
    # Non-empty checks for present-but-empty fields.
    assert "spec.name must be a non-empty string" in msg
    # Mode whitelist.
    assert "spec.mode" in msg
    # Preset whitelist.
    assert "spec.preset" in msg
    # Risk bounds.
    assert "per_trade_pct" in msg
    # Signal kind whitelist.
    assert "spec.signals[0].kind" in msg


def test_validate_subclass_of_value_error() -> None:
    """SpecValidationError must subclass ValueError so existing auto_build
    error-handling (``except ValueError``) keeps catching it without changes.
    """
    assert issubclass(spec_schema.SpecValidationError, ValueError)


def test_validate_rejects_unknown_top_level_keys() -> None:
    spec = dict(MINIMAL, oops_typo="x")
    with pytest.raises(spec_schema.SpecValidationError, match="unknown top-level keys"):
        spec_schema.validate(spec)


def test_validate_rejects_non_dict_spec() -> None:
    with pytest.raises(spec_schema.SpecValidationError, match="must be a mapping"):
        spec_schema.validate("not a dict")  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# preset / stack cross-check
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_preset_stack_match_ok() -> None:
    spec_schema.validate(dict(MINIMAL), valid_presets=build_mod.PRESETS)


def test_validate_rejects_stack_not_in_preset() -> None:
    spec = dict(MINIMAL, stack="not-a-stack")
    with pytest.raises(spec_schema.SpecValidationError, match="spec.stack"):
        spec_schema.validate(spec, valid_presets=build_mod.PRESETS)


# ─────────────────────────────────────────────────────────────────────────────
# Risk block
# ─────────────────────────────────────────────────────────────────────────────

def test_risk_block_overrides_take_effect() -> None:
    spec = dict(MINIMAL, risk={
        "per_trade_pct": 1.0,
        "daily_loss_pct": 3.0,
        "max_spread_pips": 5.0,
        "max_open_positions": 7,
        "sl_pips": 50,
        "tp_pips": 120,
    })
    out = spec_schema.validate(spec)
    assert out.risk.per_trade_pct == 1.0
    assert out.risk.daily_loss_pct == 3.0
    assert out.risk.max_spread_pips == 5.0
    assert out.risk.max_open_positions == 7
    assert out.risk.sl_pips == 50
    assert out.risk.tp_pips == 120


def test_risk_block_rejects_out_of_range() -> None:
    spec = dict(MINIMAL, risk={"per_trade_pct": 99.0})
    with pytest.raises(spec_schema.SpecValidationError, match="per_trade_pct"):
        spec_schema.validate(spec)


def test_risk_block_rejects_unknown_field() -> None:
    spec = dict(MINIMAL, risk={"per_trade_pct": 1.0, "rocket_fuel": 9})
    with pytest.raises(spec_schema.SpecValidationError, match="rocket_fuel"):
        spec_schema.validate(spec)


def test_risk_block_rejects_bool_for_number() -> None:
    """``bool`` is a subclass of ``int`` in Python — but ``per_trade_pct=True``
    is almost certainly a typo, not a valid 1.0 percent. Reject it.
    """
    spec = dict(MINIMAL, risk={"per_trade_pct": True})
    with pytest.raises(spec_schema.SpecValidationError, match="per_trade_pct"):
        spec_schema.validate(spec)


def test_risk_as_template_vars_includes_legacy_keys() -> None:
    cfg = spec_schema.RiskConfig(
        per_trade_pct=0.5, daily_loss_pct=5.0,
        max_spread_pips=3.0, max_open_positions=3, sl_pips=30, tp_pips=60,
    )
    vars_ = cfg.as_template_vars()
    # New keys
    assert vars_["RISK_PER_TRADE_PCT"] == "0.5"
    assert vars_["DAILY_LOSS_PCT"] == "5.0"
    assert vars_["DAILY_LOSS_FRAC"] == "0.05"
    assert vars_["MAX_SPREAD_PIPS"] == "3.0"
    assert vars_["MAX_POSITIONS"] == "3"
    assert vars_["SL_PIPS"] == "30"
    assert vars_["TP_PIPS"] == "60"
    # Legacy money proxy — must be float-formatted ("100.0" not "100").
    assert vars_["RISK_MONEY"].endswith(".0") or "." in vars_["RISK_MONEY"]


# ─────────────────────────────────────────────────────────────────────────────
# Signals + filters + hooks
# ─────────────────────────────────────────────────────────────────────────────

def test_signals_list_form() -> None:
    spec = dict(MINIMAL, signals=[
        {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
        {"kind": "sar", "step": 0.02, "max": 0.2},
    ])
    out = spec_schema.validate(spec)
    assert [s.kind for s in out.signals] == ["macd", "sar"]
    assert out.signals[0].params == {"fast": 12, "slow": 26, "signal": 9}


def test_signals_mapping_form_with_logic() -> None:
    spec = dict(MINIMAL, signals={
        "logic": "OR",
        "list": [{"kind": "rsi", "period": 14}],
    })
    out = spec_schema.validate(spec)
    assert out.signal_logic == "OR"
    assert out.signals[0].kind == "rsi"


def test_signals_rejects_bad_logic() -> None:
    spec = dict(MINIMAL, signals={"logic": "XOR", "list": []})
    with pytest.raises(spec_schema.SpecValidationError, match="signals.logic"):
        spec_schema.validate(spec)


def test_signals_rejects_bad_kind() -> None:
    spec = dict(MINIMAL, signals=[{"kind": "magic_eight_ball"}])
    with pytest.raises(spec_schema.SpecValidationError, match="signals\\[0\\].kind"):
        spec_schema.validate(spec)


def test_filters_validated() -> None:
    spec = dict(MINIMAL, filters=[
        {"kind": "time_window", "from": "08:00", "to": "20:00"},
        {"kind": "news_blackout", "minutes_before": 30},
    ])
    out = spec_schema.validate(spec)
    assert [f.kind for f in out.filters] == ["time_window", "news_blackout"]


def test_filters_rejects_unknown_kind() -> None:
    spec = dict(MINIMAL, filters=[{"kind": "moon_phase"}])
    with pytest.raises(spec_schema.SpecValidationError, match="filters\\[0\\].kind"):
        spec_schema.validate(spec)


def test_hooks_validated() -> None:
    spec = dict(MINIMAL, hooks={
        "on_init": ["Print(\"init\")"],
        "on_deinit": ["Print(\"deinit\")"],
    })
    out = spec_schema.validate(spec)
    assert out.hooks["on_init"] == ['Print("init")']
    assert out.hooks["on_deinit"] == ['Print("deinit")']


def test_hooks_rejects_non_list_body() -> None:
    spec = dict(MINIMAL, hooks={"on_init": "not a list"})
    with pytest.raises(spec_schema.SpecValidationError, match="hooks.on_init"):
        spec_schema.validate(spec)


# ─────────────────────────────────────────────────────────────────────────────
# render_signals_doc
# ─────────────────────────────────────────────────────────────────────────────

def test_render_signals_doc_no_signals() -> None:
    out = spec_schema.validate(dict(MINIMAL))
    md = spec_schema.render_signals_doc(out)
    assert "# Signals for SpecSchemaEA" in md
    assert "EURUSD" in md and "H1" in md
    assert "_No signals declared" in md


def test_render_signals_doc_with_signals() -> None:
    spec = dict(MINIMAL, signals=[
        {"kind": "macd", "fast": 12, "slow": 26},
        {"kind": "sar"},
    ])
    out = spec_schema.validate(spec)
    md = spec_schema.render_signals_doc(out)
    assert "## Indicators" in md
    assert "macd" in md and "sar" in md
    assert "`fast`: `12`" in md


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end: auto_build pipeline carries spec.risk into the rendered scaffold
# ─────────────────────────────────────────────────────────────────────────────

def test_run_pipeline_applies_risk_overrides_and_writes_signals_md(
    tmp_path: Path, monkeypatch
) -> None:
    """Spec with custom risk + signals must:

    1. render the stdlib/netting EA with the spec's SL/TP/daily-loss numbers
    2. emit ``signals.md`` listing the declared indicators
    3. still pass lint (no new errors introduced by the substitutions)
    """
    # Monkeypatch compile/gate to keep the test hermetic (no Wine on CI).
    from vibecodekit_mql5 import compile as compile_mod
    from vibecodekit_mql5.permission import orchestrator as orch_mod

    fake_result = compile_mod.CompileResult(success=True, ex5_path="/tmp/fake.ex5")
    monkeypatch.setattr(compile_mod, "compile_mq5", lambda *_a, **_k: fake_result)

    class _FakeReport:
        ok = True
        mode = "personal"
        layers = []

    monkeypatch.setattr(orch_mod, "run", lambda _ns: _FakeReport())

    spec = {
        **MINIMAL,
        "name": "RiskOverrideEA",
        "risk": {"sl_pips": 77, "tp_pips": 144, "daily_loss_pct": 2.0,
                 "max_open_positions": 5},
        "signals": [{"kind": "macd", "fast": 12, "slow": 26}],
    }
    out_dir = tmp_path / "build"

    ea_spec = auto_build.validate_spec(spec)
    report = auto_build.run_pipeline(
        spec,
        out_dir,
        ea_spec=ea_spec,
        skip_compile=False,
        skip_gate=False,
    )
    assert report.ok, json.dumps(report.to_dict(), indent=2)

    mq5 = out_dir / "RiskOverrideEA.mq5"
    text = mq5.read_text()
    assert "InpSlPips      = 77" in text
    assert "InpTpPips      = 144" in text
    # 2.0% daily loss -> 0.02 fraction
    assert "InpDailyLossPct = 0.02" in text
    assert "InpMaxPositions = 5" in text

    sset = out_dir / "Sets" / "default.set"
    sset_txt = sset.read_text()
    assert "InpSlPips=77" in sset_txt
    assert "InpDailyLossPct=0.02" in sset_txt

    signals_md = out_dir / "signals.md"
    assert signals_md.is_file()
    assert "macd" in signals_md.read_text()


def test_run_pipeline_without_spec_signals_omits_signals_md(
    tmp_path: Path, monkeypatch
) -> None:
    from vibecodekit_mql5 import compile as compile_mod
    from vibecodekit_mql5.permission import orchestrator as orch_mod

    monkeypatch.setattr(
        compile_mod, "compile_mq5",
        lambda *_a, **_k: compile_mod.CompileResult(success=True, ex5_path="/tmp/fake.ex5"),
    )

    class _FakeReport:
        ok = True
        mode = "personal"
        layers = []

    monkeypatch.setattr(orch_mod, "run", lambda _ns: _FakeReport())

    spec = {**MINIMAL, "name": "NoSignalsEA"}
    out_dir = tmp_path / "build2"
    ea_spec = auto_build.validate_spec(spec)
    report = auto_build.run_pipeline(spec, out_dir, ea_spec=ea_spec)
    assert report.ok
    assert not (out_dir / "signals.md").exists(), \
        "signals.md should be omitted when spec.signals + spec.filters are empty"


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 schema extensions: prop_firm / time_exit / stealth
# ─────────────────────────────────────────────────────────────────────────────

def test_prop_firm_block_accepted_and_normalized() -> None:
    out = spec_schema.validate({
        **MINIMAL,
        "prop_firm": {
            "daily_dd_pct": 5.0, "max_dd_pct": 10.0,
            "profit_target_pct": 8.0, "news_block_min": 30,
            "weekend_flat": True, "copy_trading_lock": False,
        },
    })
    assert out.prop_firm is not None
    assert out.prop_firm.daily_dd_pct == 5.0
    assert out.prop_firm.weekend_flat is True
    # to_dict() strips defaults (False / None) for cleanliness.
    d = out.prop_firm.to_dict()
    assert "copy_trading_lock" not in d
    assert d["weekend_flat"] is True


def test_prop_firm_rejects_out_of_range() -> None:
    with pytest.raises(spec_schema.SpecValidationError) as excinfo:
        spec_schema.validate({
            **MINIMAL,
            "prop_firm": {"daily_dd_pct": 150.0, "news_block_min": 99999},
        })
    msg = str(excinfo.value)
    assert "daily_dd_pct" in msg
    assert "news_block_min" in msg


def test_prop_firm_rejects_bool_for_numeric_field() -> None:
    with pytest.raises(spec_schema.SpecValidationError) as excinfo:
        spec_schema.validate({
            **MINIMAL,
            "prop_firm": {"daily_dd_pct": True},
        })
    assert "daily_dd_pct" in str(excinfo.value)


def test_prop_firm_rejects_unknown_keys() -> None:
    with pytest.raises(spec_schema.SpecValidationError) as excinfo:
        spec_schema.validate({
            **MINIMAL,
            "prop_firm": {"daily_dd_pct": 5.0, "bogus_field": 1},
        })
    msg = str(excinfo.value)
    assert "prop_firm" in msg and "bogus_field" in msg


def test_time_exit_block_accepted() -> None:
    out = spec_schema.validate({
        **MINIMAL,
        "time_exit": {
            "close_on_friday": True, "friday_close_hour": 20,
            "max_trade_hours": 48, "session_start_hour": 8,
            "session_end_hour": 22,
        },
    })
    assert out.time_exit is not None
    assert out.time_exit.max_trade_hours == 48
    assert out.time_exit.close_on_friday is True


def test_time_exit_allows_hour_zero() -> None:
    # 0 is a valid hour (midnight) — the bounds use _check_num_range with
    # min_excl=-1 so 0 passes the strict-greater-than test.
    out = spec_schema.validate({
        **MINIMAL,
        "time_exit": {"session_start_hour": 0, "session_end_hour": 23},
    })
    assert out.time_exit is not None
    assert out.time_exit.session_start_hour == 0
    assert out.time_exit.session_end_hour == 23


def test_time_exit_rejects_max_trade_hours_zero() -> None:
    # max_trade_hours=0 is meaningless and must be rejected.
    with pytest.raises(spec_schema.SpecValidationError):
        spec_schema.validate({
            **MINIMAL, "time_exit": {"max_trade_hours": 0},
        })


def test_time_exit_rejects_bool_for_int_field() -> None:
    with pytest.raises(spec_schema.SpecValidationError) as excinfo:
        spec_schema.validate({
            **MINIMAL,
            "time_exit": {"max_trade_hours": True},
        })
    assert "max_trade_hours" in str(excinfo.value)


def test_stealth_block_accepted_with_comment_pool() -> None:
    out = spec_schema.validate({
        **MINIMAL,
        "stealth": {
            "randomize_slippage_pips": 2.0,
            "randomize_comment_pool": ["alpha", "beta"],
            "randomize_lot_jitter_pct": 1.5,
            "split_orders": True, "avoid_round_numbers": True,
        },
    })
    assert out.stealth is not None
    assert out.stealth.randomize_comment_pool == ["alpha", "beta"]
    assert out.stealth.split_orders is True


def test_stealth_rejects_non_string_in_comment_pool() -> None:
    with pytest.raises(spec_schema.SpecValidationError) as excinfo:
        spec_schema.validate({
            **MINIMAL,
            "stealth": {"randomize_comment_pool": ["ok", 123]},
        })
    assert "randomize_comment_pool" in str(excinfo.value)


def test_stealth_rejects_unknown_keys() -> None:
    with pytest.raises(spec_schema.SpecValidationError) as excinfo:
        spec_schema.validate({
            **MINIMAL,
            "stealth": {"foo_bar": 1},
        })
    assert "stealth" in str(excinfo.value)


def test_extensions_omitted_when_not_provided() -> None:
    """Specs that don't supply the new blocks must round-trip cleanly."""
    out = spec_schema.validate(dict(MINIMAL))
    assert out.prop_firm is None
    assert out.time_exit is None
    assert out.stealth is None
    # to_dict() must NOT include keys for sections the user didn't set.
    d = out.to_dict()
    assert "prop_firm" not in d
    assert "time_exit" not in d
    assert "stealth" not in d


def test_all_three_extensions_together() -> None:
    out = spec_schema.validate({
        **MINIMAL,
        "prop_firm": {"daily_dd_pct": 4.0, "weekend_flat": True},
        "time_exit": {"close_on_friday": True, "max_trade_hours": 24},
        "stealth":   {"randomize_slippage_pips": 1.5, "split_orders": True},
    })
    d = out.to_dict()
    assert d["prop_firm"]["daily_dd_pct"] == 4.0
    assert d["time_exit"]["close_on_friday"] is True
    assert d["stealth"]["split_orders"] is True


def test_extensions_must_be_mappings() -> None:
    """Lists or scalars in place of an extension block must fail cleanly."""
    for key in ("prop_firm", "time_exit", "stealth"):
        with pytest.raises(spec_schema.SpecValidationError) as excinfo:
            spec_schema.validate({**MINIMAL, key: ["bad", "shape"]})
        assert key in str(excinfo.value)
        assert "mapping" in str(excinfo.value)
