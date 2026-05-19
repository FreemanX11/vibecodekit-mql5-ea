"""PR-11 — ``mql5-spec-from-prompt`` infers PR-2 / PR-8 optional blocks.

Smoke-test gap G1 in ``/home/ubuntu/work/smoke-test/REPORT.md`` flagged
that the parser ignored every block added after the initial release —
even when the prompt explicitly mentioned FTMO, Friday close, stealth,
ATR trailing, partial close, correlation guard, swap filter, or
structured logging. These tests pin the parser's new behaviour for
each of the 8 optional blocks (3 PR-2 + 5 PR-8) and prove the output
still round-trips through ``spec_schema.validate`` and the YAML
emitter.

The parser remains deterministic / regex-only — no LLM call, no
network — so each prompt below has a single canonical extraction.
"""

from __future__ import annotations

import pytest

from vibecodekit_mql5 import build as build_mod
from vibecodekit_mql5 import spec_schema
from vibecodekit_mql5.spec_from_prompt import parse, to_yaml


# ─────────────────────────────────────────────────────────────────────────────
# Common helpers
# ─────────────────────────────────────────────────────────────────────────────

def _validate(spec: dict) -> None:
    spec_schema.validate(spec, valid_presets=build_mod.PRESETS)


# ─────────────────────────────────────────────────────────────────────────────
# Back-compat — no PR-2/PR-8 keywords ⇒ no new blocks
# ─────────────────────────────────────────────────────────────────────────────

def test_simple_prompt_omits_all_optional_blocks() -> None:
    """The original PROMPTS_VALID matrix must keep producing the same shape."""
    spec = parse("build EA trend EURUSD H1 risk 0.5%").spec
    for block in (
        "prop_firm", "time_exit", "stealth",
        "trailing", "partial_close", "correlation",
        "swap_filter", "logs",
    ):
        assert block not in spec, f"prompt without {block} keyword leaked the block"


def test_simple_prompt_marks_all_blocks_as_defaulted() -> None:
    result = parse("trend EURUSD H1 risk 0.5%")
    for block in (
        "prop_firm", "time_exit", "stealth",
        "trailing", "partial_close", "correlation",
        "swap_filter", "logs",
    ):
        assert block in result.defaulted
        assert block not in result.inferred


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 — prop_firm
# ─────────────────────────────────────────────────────────────────────────────

def test_prop_firm_full_extraction() -> None:
    spec = parse(
        "trend EURUSD H1 risk 0.5% FTMO daily DD 5% max DD 10% "
        "profit target 8% news block 30 weekend flat copy trading lock"
    ).spec
    pf = spec["prop_firm"]
    assert pf == {
        "daily_dd_pct": 5.0, "max_dd_pct": 10.0, "profit_target_pct": 8.0,
        "news_block_min": 30, "weekend_flat": True, "copy_trading_lock": True,
    }
    _validate(spec)


def test_prop_firm_bare_keyword_opts_in_with_defaults() -> None:
    spec = parse("trend EURUSD H1 FTMO").spec
    assert "prop_firm" in spec
    assert spec["prop_firm"]["daily_dd_pct"] == 5.0


def test_prop_firm_funded_synonym_opts_in() -> None:
    spec = parse("trend EURUSD H1 funded account").spec
    assert "prop_firm" in spec


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 — time_exit
# ─────────────────────────────────────────────────────────────────────────────

def test_time_exit_close_friday_at_specific_hour() -> None:
    spec = parse("trend EURUSD H1 close on friday at 20 max trade hours 48").spec
    te = spec["time_exit"]
    assert te["close_on_friday"] is True
    assert te["friday_close_hour"] == 20
    assert te["max_trade_hours"] == 48
    _validate(spec)


def test_time_exit_session_window_extracted() -> None:
    spec = parse("trend EURUSD H1 session start 8 session end 22").spec
    te = spec["time_exit"]
    assert te["session_start_hour"] == 8
    assert te["session_end_hour"] == 22
    _validate(spec)


def test_time_exit_bare_keyword_opts_in() -> None:
    spec = parse("trend EURUSD H1 time exit").spec
    assert "time_exit" in spec


# ─────────────────────────────────────────────────────────────────────────────
# PR-2 — stealth
# ─────────────────────────────────────────────────────────────────────────────

def test_stealth_full_extraction() -> None:
    spec = parse(
        "scalping XAUUSD M5 stealth split orders avoid round numbers "
        "randomize slippage 2 lot jitter 1.5"
    ).spec
    s = spec["stealth"]
    assert s["split_orders"] is True
    assert s["avoid_round_numbers"] is True
    assert s["randomize_slippage_pips"] == 2.0
    assert s["randomize_lot_jitter_pct"] == 1.5
    _validate(spec)


def test_stealth_bare_keyword_opts_in() -> None:
    spec = parse("scalping XAUUSD M5 stealth").spec
    assert "stealth" in spec


def test_stealth_comment_pool_default_list() -> None:
    spec = parse("scalping XAUUSD M5 randomize comments").spec
    s = spec["stealth"]
    assert isinstance(s["randomize_comment_pool"], list)
    assert len(s["randomize_comment_pool"]) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# PR-8 — trailing
# ─────────────────────────────────────────────────────────────────────────────

def test_trailing_atr_mode_with_params() -> None:
    spec = parse(
        "trend EURUSD H1 atr trailing start 20 step 5 atr mult 2.5"
    ).spec
    t = spec["trailing"]
    assert t["enabled"] is True
    assert t["mode"] == "atr"
    assert t["start_pips"] == 20.0
    assert t["atr_mult"] == 2.5
    _validate(spec)


def test_trailing_parabolic_mode() -> None:
    spec = parse("trend EURUSD H1 parabolic trailing").spec
    assert spec["trailing"]["mode"] == "parabolic"


def test_trailing_fixed_mode() -> None:
    spec = parse("trend EURUSD H1 fixed trailing").spec
    assert spec["trailing"]["mode"] == "fixed"


def test_trailing_bare_keyword_opts_in() -> None:
    spec = parse("trend EURUSD H1 trailing stop").spec
    assert spec["trailing"]["enabled"] is True


# ─────────────────────────────────────────────────────────────────────────────
# PR-8 — partial_close
# ─────────────────────────────────────────────────────────────────────────────

def test_partial_close_two_levels_extracted() -> None:
    spec = parse(
        "trend EURUSD H1 partial close 50% at 20 pips 30% at 50 pips "
        "move sl to breakeven"
    ).spec
    pc = spec["partial_close"]
    assert pc["enabled"] is True
    assert pc["levels"] == [
        {"at_pips": 20.0, "pct": 50.0},
        {"at_pips": 50.0, "pct": 30.0},
    ]
    assert pc["move_sl_to_breakeven_after_first"] is True
    _validate(spec)


def test_partial_close_breakeven_buffer_extracted() -> None:
    spec = parse("trend EURUSD H1 partial close 30% at 25 pips breakeven buffer 2").spec
    pc = spec["partial_close"]
    assert pc["breakeven_buffer_pips"] == 2.0


def test_partial_close_omitted_when_unrelated_percent() -> None:
    """``risk 0.5%`` shouldn't be misread as a partial-close level."""
    spec = parse("trend EURUSD H1 risk 0.5%").spec
    assert "partial_close" not in spec


# ─────────────────────────────────────────────────────────────────────────────
# PR-8 — correlation
# ─────────────────────────────────────────────────────────────────────────────

def test_correlation_full_extraction() -> None:
    spec = parse(
        "trend EURUSD H1 correlation max correlated 2 "
        "correlation threshold 0.8 correlation window 100 "
        "block if correlated loss"
    ).spec
    c = spec["correlation"]
    assert c["max_correlated_positions"] == 2
    assert c["correlation_threshold"] == 0.8
    assert c["correlation_window_bars"] == 100
    assert c["block_if_correlated_loss"] is True
    _validate(spec)


def test_correlation_bare_keyword_opts_in() -> None:
    spec = parse("trend EURUSD H1 correlation guard").spec
    assert "correlation" in spec


# ─────────────────────────────────────────────────────────────────────────────
# PR-8 — swap_filter
# ─────────────────────────────────────────────────────────────────────────────

def test_swap_filter_full_extraction() -> None:
    spec = parse(
        "trend EURUSD H1 swap filter max long swap -1.0 max short swap -1.5 "
        "max hold bars 24 skip wednesday"
    ).spec
    sf = spec["swap_filter"]
    assert sf["max_long_swap_pips_per_day"] == -1.0
    assert sf["max_short_swap_pips_per_day"] == -1.5
    assert sf["max_hold_bars_if_negative_swap"] == 24
    assert sf["skip_wednesday_triple_swap"] is True
    _validate(spec)


def test_swap_filter_bare_negative_swap_opts_in() -> None:
    spec = parse("trend EURUSD H1 negative swap").spec
    assert "swap_filter" in spec


# ─────────────────────────────────────────────────────────────────────────────
# PR-8 — logs
# ─────────────────────────────────────────────────────────────────────────────

def test_logs_full_extraction() -> None:
    spec = parse(
        "trend EURUSD H1 log to file log level info redact account numbers"
    ).spec
    logs = spec["logs"]
    assert logs["enabled"] is True
    assert logs["level"] == "info"
    assert logs["to_file"] is True
    assert logs["redact_account_numbers"] is True
    _validate(spec)


@pytest.mark.parametrize("level", ["debug", "info", "warn", "error"])
def test_logs_level_synonyms(level: str) -> None:
    spec = parse(f"trend EURUSD H1 logs log level {level}").spec
    assert spec["logs"]["level"] == level


def test_logs_warning_normalised_to_warn() -> None:
    spec = parse("trend EURUSD H1 logs log level warning").spec
    assert spec["logs"]["level"] == "warn"


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end — the literal smoke-test G1 prompt fires all 8 blocks
# ─────────────────────────────────────────────────────────────────────────────

SMOKE_G1_PROMPT = (
    "trend EURUSD H1 risk 0.5% FTMO daily DD 5% max DD 10% "
    "profit target 8% weekend flat close on friday at 20 max trade hours 48 "
    "stealth split orders avoid round numbers "
    "atr trailing start 20 step 5 atr mult 2.5 "
    "partial close 50% at 20 pips 30% at 50 pips move sl to breakeven "
    "correlation max correlated 2 correlation threshold 0.8 correlation window 100 "
    "block if correlated loss "
    "swap filter max long swap -1.0 max short swap -1.5 skip wednesday triple swap "
    "log to file log level info redact account numbers"
)


def test_smoke_g1_prompt_extracts_all_eight_blocks() -> None:
    """The exact prompt G1 in REPORT.md flagged must now infer everything."""
    result = parse(SMOKE_G1_PROMPT)
    spec = result.spec
    for block in (
        "prop_firm", "time_exit", "stealth",
        "trailing", "partial_close", "correlation",
        "swap_filter", "logs",
    ):
        assert block in spec, f"missing {block} in smoke G1 prompt extraction"
        assert block in result.inferred
        assert block not in result.defaulted
    _validate(spec)


def test_smoke_g1_yaml_round_trip() -> None:
    """Emit → parse → equal spec, for the smoke prompt."""
    pytest.importorskip("yaml")
    import yaml  # type: ignore[import-untyped]

    spec = parse(SMOKE_G1_PROMPT).spec
    loaded = yaml.safe_load(to_yaml(spec))
    assert loaded == spec


def test_smoke_g1_yaml_emitter_is_stable() -> None:
    spec = parse(SMOKE_G1_PROMPT).spec
    assert to_yaml(spec) == to_yaml(spec)
