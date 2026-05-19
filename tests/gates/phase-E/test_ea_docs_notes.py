"""Tests for the rule-table take-notes derivation (PR-16).

Each rule fires on a specific block of ``EaSpec``. We build spec
fixtures that toggle one block at a time and assert the rule output.
"""

from __future__ import annotations

import pytest

from scripts.vibecodekit_mql5.ea_docs_notes import (
    SUPPORTED_LANGS,
    derive_take_notes,
)
from scripts.vibecodekit_mql5.spec_blocks_extra import (
    CorrelationConfig,
    LogsConfig,
    PartialCloseConfig,
    SwapFilterConfig,
    TrailingConfig,
)
from scripts.vibecodekit_mql5.spec_extensions import (
    PropFirmConfig,
    StealthConfig,
    TimeExitConfig,
)
from scripts.vibecodekit_mql5.spec_schema import (
    EaSpec,
    RiskConfig,
    SignalConfig,
)


def _bare_spec(**overrides) -> EaSpec:
    """A minimal valid spec — used as a baseline for additive toggles."""
    defaults = dict(
        name="TestEA",
        preset="standard",
        stack="wizard-composable",
        symbol="EURUSD",
        timeframe="H1",
        mode="personal",
        risk=RiskConfig(),
        signals=[SignalConfig(kind="ma_cross")],
    )
    defaults.update(overrides)
    return EaSpec(**defaults)


# ────────────────────────────────────────────────────────────────────────────
# Empty spec → no notes
# ────────────────────────────────────────────────────────────────────────────


def test_empty_spec_emits_no_notes() -> None:
    spec = _bare_spec()
    assert derive_take_notes(spec) == []


def test_invalid_lang_falls_back_to_vi() -> None:
    spec = _bare_spec(stealth=StealthConfig(split_orders=True))
    en = derive_take_notes(spec, lang="en")
    vi = derive_take_notes(spec, lang="vi")
    fallback = derive_take_notes(spec, lang="klingon")
    assert fallback == vi
    assert fallback != en


@pytest.mark.parametrize("lang", list(SUPPORTED_LANGS))
def test_supported_langs_all_render(lang: str) -> None:
    """All rules render in every supported language without crashing."""
    spec = _bare_spec(
        prop_firm=PropFirmConfig(daily_dd_pct=5.0, weekend_flat=True),
        time_exit=TimeExitConfig(
            close_on_friday=True, friday_close_hour=20, max_trade_hours=48,
        ),
        stealth=StealthConfig(split_orders=True, avoid_round_numbers=True),
        trailing=TrailingConfig(enabled=True, mode="atr", atr_mult=2.5),
        partial_close=PartialCloseConfig(
            enabled=True,
            levels=[{"at_pips": 20.0, "pct": 50.0}],
        ),
        correlation=CorrelationConfig(max_correlated_positions=2),
        swap_filter=SwapFilterConfig(skip_wednesday_triple_swap=True),
        logs=LogsConfig(redact_account_numbers=True),
        preset="ml-onnx",
        mode="enterprise",
    )
    notes = derive_take_notes(spec, lang=lang)
    # Expect roughly one note per block + a couple of extras
    # (onnx + enterprise). Lower bound 10 is safely under the actual
    # count and resilient if we add new rules later.
    assert len(notes) >= 10
    for n in notes:
        assert n.title
        assert n.body
        assert n.severity in ("info", "warn", "danger")
        assert n.icon


# ────────────────────────────────────────────────────────────────────────────
# Block-by-block targeted tests
# ────────────────────────────────────────────────────────────────────────────


def test_prop_firm_fires_with_daily_dd() -> None:
    spec = _bare_spec(prop_firm=PropFirmConfig(daily_dd_pct=5.0))
    notes = derive_take_notes(spec)
    assert any("daily drawdown" in n.title.lower() for n in notes)


def test_prop_firm_weekend_flat_fires() -> None:
    spec = _bare_spec(prop_firm=PropFirmConfig(weekend_flat=True))
    titles = [n.title for n in derive_take_notes(spec)]
    assert any("flat cuối tuần" in t for t in titles)


def test_time_exit_friday_close_hour_in_title() -> None:
    spec = _bare_spec(
        time_exit=TimeExitConfig(close_on_friday=True, friday_close_hour=21)
    )
    notes = derive_take_notes(spec)
    assert any("21h" in n.title for n in notes)


def test_stealth_split_orders_fires_warn() -> None:
    spec = _bare_spec(stealth=StealthConfig(split_orders=True))
    notes = derive_take_notes(spec)
    matched = [n for n in notes if "split" in n.title.lower()]
    assert matched and matched[0].severity == "warn"


def test_trailing_atr_mode_fires_with_mult() -> None:
    spec = _bare_spec(
        trailing=TrailingConfig(enabled=True, mode="atr", atr_mult=3.0)
    )
    notes = derive_take_notes(spec)
    assert any("ATR-adaptive" in n.title and "3.0" in n.title for n in notes)


def test_trailing_disabled_emits_no_note() -> None:
    spec = _bare_spec(trailing=TrailingConfig(enabled=False, mode="atr"))
    notes = derive_take_notes(spec)
    assert not any("Trailing" in n.title for n in notes)


def test_partial_close_levels_count_in_title() -> None:
    spec = _bare_spec(partial_close=PartialCloseConfig(
        enabled=True,
        levels=[
            {"at_pips": 20.0, "pct": 50.0},
            {"at_pips": 50.0, "pct": 30.0},
        ],
    ))
    notes = derive_take_notes(spec)
    assert any("2 level" in n.title for n in notes)


def test_correlation_max_positions_in_title() -> None:
    spec = _bare_spec(
        correlation=CorrelationConfig(max_correlated_positions=2)
    )
    notes = derive_take_notes(spec)
    assert any("max 2" in n.title for n in notes)


def test_swap_filter_wednesday_fires_warn() -> None:
    spec = _bare_spec(
        swap_filter=SwapFilterConfig(skip_wednesday_triple_swap=True)
    )
    notes = derive_take_notes(spec)
    matched = [n for n in notes if "triple-swap" in n.title.lower()]
    assert matched and matched[0].severity == "warn"


def test_logs_redact_emits_info() -> None:
    spec = _bare_spec(logs=LogsConfig(redact_account_numbers=True))
    notes = derive_take_notes(spec)
    matched = [n for n in notes if "account number" in n.title.lower()]
    assert matched and matched[0].severity == "info"


def test_onnx_signal_emits_warn() -> None:
    spec = _bare_spec(signals=[SignalConfig(kind="onnx_predict")])
    notes = derive_take_notes(spec)
    matched = [n for n in notes if "ONNX" in n.title]
    assert matched and matched[0].severity == "warn"


def test_ml_onnx_preset_emits_warn() -> None:
    spec = _bare_spec(preset="ml-onnx")
    notes = derive_take_notes(spec)
    assert any("ONNX" in n.title for n in notes)


def test_enterprise_mode_emits_info() -> None:
    spec = _bare_spec(mode="enterprise")
    notes = derive_take_notes(spec)
    matched = [n for n in notes if "enterprise" in n.title.lower()]
    assert matched and matched[0].severity == "info"


def test_personal_mode_emits_no_enterprise_note() -> None:
    spec = _bare_spec(mode="personal")
    notes = derive_take_notes(spec)
    assert not any("enterprise" in n.title.lower() for n in notes)


def test_en_lang_renders_english_text() -> None:
    spec = _bare_spec(stealth=StealthConfig(split_orders=True))
    notes = derive_take_notes(spec, lang="en")
    assert notes
    # English body never contains the VN word "Lệnh".
    assert all("Lệnh" not in n.body for n in notes)
