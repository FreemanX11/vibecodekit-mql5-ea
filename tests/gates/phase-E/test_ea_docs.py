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
# Regression tests for PR-16.1 — Devin Review findings.
# ────────────────────────────────────────────────────────────────────────────


def test_kit_version_resolves_real_distribution() -> None:
    """The dist name in pyproject.toml is 'vibecodekit-mql5-ea' (with the
    ``-ea`` suffix). The previous lookup used 'vibecodekit-mql5', so
    ``_kit_version`` always returned 'unknown' once the package was
    installed in editable mode. Pin the correct dist name here so the
    bug can't regress silently."""
    from scripts.vibecodekit_mql5 import ea_docs as ea_docs_mod

    assert ea_docs_mod._DIST_NAME == "vibecodekit-mql5-ea"
    # If the test runner installed the package (e.g. ``pip install -e .``)
    # the call should succeed and return a non-"unknown" version.
    # When the dist is not installed (e.g. tests run from a raw checkout
    # without ``pip install -e .``) we still want the call to be safe.
    assert ea_docs_mod._kit_version() != ""


def test_signal_kinds_html_escaped_in_closing_fragment() -> None:
    """``build_doc_content`` accepts any ``EaSpec`` directly, including
    one whose signal kinds contain raw HTML. The closing fragment must
    not let that leak through as live markup."""
    from scripts.vibecodekit_mql5.ea_docs import _render_signals_summary

    fragment = _render_signals_summary("<script>alert(1)</script>", "vi")
    assert "<script>" not in fragment
    assert "&lt;script&gt;" in fragment
    assert "&lt;/script&gt;" in fragment


def test_signal_kinds_html_escaped_via_closing_html() -> None:
    """End-to-end version: drop a malicious-looking kind through
    ``build_doc_content`` and confirm the rendered HTML escapes it."""
    spec = _full_spec()
    # Bypass the schema by mutating the frozen dataclass with object.__setattr__.
    object.__setattr__(spec.signals[0], "kind", "<img src=x onerror=alert(1)>")
    html_out = render_html_document(build_doc_content(spec, _MQ5_SAMPLE, _build_meta()))
    assert "<img src=x onerror=alert(1)>" not in html_out
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_out


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
    # PR-18.2: default lang is Vietnamese; the section header and table
    # column labels are localized, but the code identifier ``InpRiskPct``
    # is a project name and stays verbatim.
    assert "## Tham số EA" in md
    assert "| Nhóm | Tên | Kiểu | Mặc định | Ghi chú |" in md
    assert "`InpRiskPct`" in md


def test_render_markdown_includes_take_notes() -> None:
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    assert "## Lưu ý quan trọng" in md
    # PR-18.3: severity prefixes are plain Vietnamese text labels
    # (emoji rendered as tofu in headless-Chrome PDF export).
    assert (
        "[Lưu ý]" in md
        or "[Cảnh báo]" in md
        or "[Nguy hiểm]" in md
    )
    # Belt-and-braces: the legacy emoji prefixes must not leak through.
    for emoji in ("ℹ️", "⚠️", "🔥", "ℹ", "⚠", "🔥"):
        assert emoji not in md, f"legacy emoji {emoji!r} leaked into markdown"


def test_render_markdown_uses_english_labels_when_lang_en() -> None:
    """Opt-in EN: when caller passes ``lang='en'`` the headers and
    column labels switch but project identifiers stay the same."""
    md = render_markdown(
        build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta(), lang="en")
    )
    assert "## EA Inputs" in md
    assert "## Take Notes" in md
    assert "| Group | Name | Type | Default | Note |" in md
    assert "`InpRiskPct`" in md


def test_render_markdown_severity_prefix_localized_to_english_when_lang_en() -> None:
    """PR-18.4 regression: the take-note severity prefix must follow
    ``lang``. Previously (PR-18.3) the prefix was hard-coded to the
    Vietnamese labels ``[Lưu ý] / [Cảnh báo] / [Nguy hiểm]`` and leaked
    into the EN markdown alongside otherwise-English note titles and
    bodies."""
    md_en = render_markdown(
        build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta(), lang="en")
    )
    # At least one English severity tag must show up.
    assert (
        "[Note]" in md_en
        or "[Warning]" in md_en
        or "[Danger]" in md_en
    ), "EN markdown must use English severity tags"
    # Vietnamese tags must NOT appear in the EN output.
    for vi_tag in ("[Lưu ý]", "[Cảnh báo]", "[Nguy hiểm]"):
        assert vi_tag not in md_en, (
            f"Vietnamese severity tag {vi_tag!r} leaked into EN markdown"
        )


def test_render_markdown_severity_prefix_localized_to_vietnamese_by_default() -> None:
    """Companion of the EN test: the default (VN) markdown must use the
    Vietnamese severity tags and must NOT leak English tags."""
    md_vi = render_markdown(
        build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta())
    )
    assert (
        "[Lưu ý]" in md_vi
        or "[Cảnh báo]" in md_vi
        or "[Nguy hiểm]" in md_vi
    ), "VN markdown must use Vietnamese severity tags"
    for en_tag in ("[Note]", "[Warning]", "[Danger]"):
        assert en_tag not in md_vi, (
            f"English severity tag {en_tag!r} leaked into VN markdown"
        )


def test_render_markdown_contains_no_japanese_decorative_text() -> None:
    """PR-18.2 contract: the Vietnamese docs must not leak the
    legacy Japanese subtitle decorations (``ポートフォリオ`` etc.).

    PR-18.3 extends this: the ``「 」`` CJK corner brackets that PR-18.2
    initially kept for visual flair are also dropped, because Chrome
    headless (used to export the PDF) has no font for them and renders
    them as tofu □ squares."""
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    for jp in ("ポートフォリオ", "システム", "アーキテクチャ"):
        assert jp not in md
    # PR-18.3: CJK corner brackets must NOT appear (would tofu in PDF).
    assert "「" not in md
    assert "」" not in md
    # The Vietnamese subtitle itself is still present, just without
    # the decorative brackets:
    assert "_Danh mục_" in md or "_Hệ thống_" in md


def test_render_markdown_has_no_chars_that_tofu_in_headless_chrome_pdf() -> None:
    """PR-18.3 regression: the markdown (and therefore the PDF rendered
    from the parallel HTML) must not contain any character that lives
    outside the basic Latin / Latin-1 / Vietnamese-Latin / common-symbol
    set. The user reported tofu □ squares in the PDF caused by ``「`` /
    ``」`` corner brackets and ``ℹ️ ⚠️ 🔥`` emoji — this test pins that
    class of bug shut so it can't regress silently.

    Identifiers (``InpMagic``, ``CRiskGuard``, ``OnTick``) are ASCII and
    pass through. Vietnamese diacritics are in U+00C0..U+1EFF. A small
    allowlist of decorative symbols (``→ · — …``) is permitted because
    they render in every default browser/PDF font.
    """
    from scripts.vibecodekit_mql5.ea_docs import render_markdown
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))

    # Vietnamese Latin block (U+00C0..U+024F + U+1E00..U+1EFF).
    def _is_safe(cp: int) -> bool:
        if cp < 128:
            return True  # ASCII
        if 0x00C0 <= cp <= 0x024F:
            return True  # Latin Extended-A/B (covers Đ, Ư, Ơ etc.)
        if 0x1E00 <= cp <= 0x1EFF:
            return True  # Latin Extended Additional (Vietnamese diacritics)
        # A tiny set of decorative symbols we use in headers/captions.
        if chr(cp) in "→·—…«»·°":
            return True
        return False

    unsafe = sorted({(hex(ord(c)), c) for c in md if not _is_safe(ord(c))})
    assert not unsafe, (
        f"Markdown contains characters that would render as tofu in "
        f"headless-Chrome PDF export: {unsafe!r}"
    )


def test_render_html_document_has_no_chars_that_tofu_in_headless_chrome_pdf() -> None:
    """PR-18.3 regression on the HTML path. ``render_html_document``
    is the source the PDF exporter feeds to headless Chrome — anything
    outside the safe Latin / Vietnamese / common-symbol set risks
    rendering as a tofu □ square in the PDF output.

    This complements ``..._has_no_chars_that_tofu_in_headless_chrome_pdf``
    above: that one covers the Markdown rendered for git/agent
    consumption, this one covers the HTML rendered for PDF export.
    """
    html_out = render_html_document(
        build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta())
    )

    def _is_safe(cp: int) -> bool:
        if cp < 128:
            return True
        if 0x00C0 <= cp <= 0x024F:
            return True
        if 0x1E00 <= cp <= 0x1EFF:
            return True
        if chr(cp) in "→·—…«»·°":
            return True
        return False

    unsafe = sorted({(hex(ord(c)), c) for c in html_out if not _is_safe(ord(c))})
    assert not unsafe, (
        f"HTML contains characters that would render as tofu in "
        f"headless-Chrome PDF export: {unsafe!r}"
    )


def test_render_markdown_overview_layers_localized_to_vietnamese() -> None:
    """The §2 layer-stack labels and captions must read in Vietnamese
    by default (e.g. 'Quản lý vốn' instead of 'Risk Guard')."""
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    assert "Quản lý vốn" in md
    assert "Tổng hợp tín hiệu" in md
    assert "Thực thi lệnh" in md
    # English layer titles must NOT appear in the default render:
    assert "Risk Guard" not in md
    assert "Signal Fusion" not in md


def test_render_markdown_timeline_localized_to_vietnamese() -> None:
    """Strategy-evolution timeline labels (Scan/Compose/Verify/Ship)
    must be Vietnamese by default."""
    md = render_markdown(build_doc_content(_full_spec(), _MQ5_SAMPLE, _build_meta()))
    for vn in ("Quét", "Soạn", "Kiểm", "Phát hành"):
        assert vn in md


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
