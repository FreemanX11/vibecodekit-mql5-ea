"""End-to-end tests for the EA-docs orchestrator + CLI (PR-16).

Covers:

* ``build_doc_content`` — composing ``DocContent`` from spec + .mq5 + meta.
* ``render_markdown`` — git-diffable parallel renderer.
* ``main`` (``mql5-ea-docs`` CLI) — file I/O round-trip.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.vibecodekit_mql5.ea_docs import (
    BuildMeta,
    build_doc_content,
    main,
    render_markdown,
)
from scripts.vibecodekit_mql5.ea_docs_render import (
    DocContent,
    render_html_document,
)
from scripts.vibecodekit_mql5.spec_blocks_extra import (
    CorrelationConfig,
    SwapFilterConfig,
    TrailingConfig,
)
from scripts.vibecodekit_mql5.spec_extensions import (
    PropFirmConfig,
    StealthConfig,
)
from scripts.vibecodekit_mql5.spec_schema import (
    EaSpec,
    FilterConfig,
    RiskConfig,
    SignalConfig,
)


# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────


_MQ5_SAMPLE = '''
//+------------------------------------------------------------------+
//|                                              MaxComplexEA.mq5   |
//+------------------------------------------------------------------+
#property strict

input group "Risk";
input double InpRiskPct = 0.5; // % equity per trade
input int    InpSLPips  = 30;

input group "Trailing";
input double InpATRMult = 2.5;
'''


def _full_spec() -> EaSpec:
    return EaSpec(
        name="MaxComplexEA_PortfolioMR",
        preset="standard",
        stack="wizard-composable",
        symbol="EURUSD",
        timeframe="H1",
        mode="enterprise",
        risk=RiskConfig(),
        signals=[
            SignalConfig(kind="ema_cross"),
            SignalConfig(kind="rsi"),
        ],
        filters=[FilterConfig(kind="spread")],
        prop_firm=PropFirmConfig(daily_dd_pct=5.0, weekend_flat=True),
        stealth=StealthConfig(split_orders=True),
        trailing=TrailingConfig(enabled=True, mode="atr", atr_mult=2.5),
        correlation=CorrelationConfig(max_correlated_positions=2),
        swap_filter=SwapFilterConfig(skip_wednesday_triple_swap=True),
    )


def _build_meta() -> BuildMeta:
    return BuildMeta(
        ea_version="0.1.0",
        kit_version="0.1.0-test",
        built_at="2026-05-19T18:00:00Z",
        built_from="max-complex-ea.yaml",
        compile_status="ok (ex5 16498 bytes, 0 errors, 512 ms)",
        gate_status="fail (Trader-17: 6/17)",
    )


# ────────────────────────────────────────────────────────────────────────────
# build_doc_content
# ────────────────────────────────────────────────────────────────────────────


def test_build_doc_content_returns_populated_dataclass() -> None:
    content = build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta())
    assert isinstance(content, DocContent)
    assert "MaxComplexEA" in content.title_main
    # Frontmatter has every metadata field.
    fm = content.frontmatter
    assert fm["ea_name"] == "MaxComplexEA_PortfolioMR"
    assert fm["ea_version"] == "0.1.0"
    assert fm["compile"].startswith("ok")
    assert fm["gate"].startswith("fail")
    # 3 architecture layers (risk / signals / execution).
    assert len(content.overview_layers) == 3
    # 4 timeline steps with last highlighted.
    assert len(content.strategy_timeline) == 4
    assert content.strategy_timeline[-1].highlight
    # Params parsed from .mq5.
    names = [p.name for p in content.params]
    assert "InpRiskPct" in names
    assert "InpSLPips" in names
    assert "InpATRMult" in names
    # Take-notes derived from the spec.
    assert content.notes


def test_build_doc_content_signal_count_in_layer_caption() -> None:
    content = build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta())
    signals_layer = content.overview_layers[1]
    assert "2 signal" in signals_layer.caption
    assert "AND" in signals_layer.caption  # default signal_logic


def test_build_doc_content_unknown_lang_falls_back_to_vi() -> None:
    content_vi = build_doc_content(
        _full_spec(), _MQ5_SAMPLE, _build_meta(), lang="vi"
    )
    content_other = build_doc_content(
        _full_spec(), _MQ5_SAMPLE, _build_meta(), lang="klingon"
    )
    assert content_vi.notes == content_other.notes


def test_build_doc_content_empty_mq5_text() -> None:
    """No inputs in source → empty param table, but doc still renders."""
    content = build_doc_content(_full_spec(), "", _build_meta())
    assert not content.params  # may be [] or () depending on default factory
    # The renderer should still happily produce HTML.
    html = render_html_document(content)
    assert "<!doctype html>" in html


def test_build_meta_now_fills_timestamp() -> None:
    meta = BuildMeta.now(ea_version="9.9.9")
    assert meta.ea_version == "9.9.9"
    assert meta.built_at.endswith("Z")
    assert "T" in meta.built_at  # ISO-8601


# ────────────────────────────────────────────────────────────────────────────
# render_markdown
# ────────────────────────────────────────────────────────────────────────────


def test_render_markdown_has_frontmatter_fence() -> None:
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    assert md.startswith("---\n")
    # Second '---' fence closes the frontmatter block.
    assert md.count("---\n") >= 2


def test_render_markdown_includes_inputs_table() -> None:
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    assert "## EA Inputs" in md
    assert "| Group | Name | Type | Default | Note |" in md
    assert "`InpRiskPct`" in md


def test_render_markdown_includes_take_notes() -> None:
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    assert "## Take Notes" in md
    # Severity prefixes.
    assert "ℹ️" in md or "⚠️" in md or "🔥" in md


def test_render_markdown_escapes_pipe_in_note() -> None:
    """Markdown table cells can't contain ``|`` un-escaped — make sure
    parser-emitted tooltips with pipes don't break the table."""
    mq5_with_pipe = 'input int InpX = 1; // a | b'
    md = render_markdown(
        build_doc_content(_full_spec(), mq5_with_pipe, _build_meta())
    )
    assert "a \\| b" in md
    assert " a | b " not in md  # un-escaped form must not appear


# ────────────────────────────────────────────────────────────────────────────
# CLI integration (file round-trip)
# ────────────────────────────────────────────────────────────────────────────


def _write_spec_yaml(tmp: Path) -> Path:
    spec_path = tmp / "spec.yaml"
    spec_path.write_text(
        '''
name: MaxComplexEA_PortfolioMR
preset: standard
stack: wizard-composable
symbol: EURUSD
timeframe: H1
mode: personal
risk: {per_trade_pct: 0.5}
signals:
  - kind: ema_cross
prop_firm:
  daily_dd_pct: 5.0
  weekend_flat: true
''',
        encoding="utf-8",
    )
    return spec_path


def test_cli_writes_html_and_md(tmp_path: Path, capsys) -> None:
    pytest.importorskip("yaml")
    spec = _write_spec_yaml(tmp_path)
    mq5 = tmp_path / "ea.mq5"
    mq5.write_text(_MQ5_SAMPLE, encoding="utf-8")
    out = tmp_path / "out"

    rc = main([str(spec), str(mq5), "--out", str(out), "--lang", "vi"])
    assert rc == 0

    captured = capsys.readouterr().out.strip()
    payload = json.loads(captured)
    assert payload["ok"] is True
    assert "html" in payload["outputs"]
    assert "md" in payload["outputs"]

    html_path = Path(payload["outputs"]["html"])
    md_path = Path(payload["outputs"]["md"])
    assert html_path.is_file() and html_path.stat().st_size > 4000
    assert md_path.is_file() and md_path.stat().st_size > 500
    assert html_path.name == "MaxComplexEA_PortfolioMR.docs.html"
    assert md_path.name == "MaxComplexEA_PortfolioMR.docs.md"


def test_cli_respects_formats_flag(tmp_path: Path, capsys) -> None:
    pytest.importorskip("yaml")
    spec = _write_spec_yaml(tmp_path)
    mq5 = tmp_path / "ea.mq5"
    mq5.write_text(_MQ5_SAMPLE, encoding="utf-8")
    out = tmp_path / "out"

    rc = main([str(spec), str(mq5), "--out", str(out), "--formats", "md"])
    assert rc == 0

    captured = json.loads(capsys.readouterr().out.strip())
    assert "md" in captured["outputs"]
    assert "html" not in captured["outputs"]


def test_cli_rejects_unknown_format(tmp_path: Path, capsys) -> None:
    pytest.importorskip("yaml")
    spec = _write_spec_yaml(tmp_path)
    mq5 = tmp_path / "ea.mq5"
    mq5.write_text(_MQ5_SAMPLE, encoding="utf-8")
    out = tmp_path / "out"

    rc = main([str(spec), str(mq5), "--out", str(out), "--formats", "docx"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown formats" in err


def test_cli_returns_2_on_missing_spec(tmp_path: Path, capsys) -> None:
    rc = main([
        str(tmp_path / "missing.yaml"),
        str(tmp_path / "missing.mq5"),
        "--out", str(tmp_path / "out"),
    ])
    assert rc == 2
    assert "error" in capsys.readouterr().err
