"""Tests for the Neo-Retro Dev Deck design-system renderer (PR-15).

The renderer is intentionally split into small ``render_*`` component
functions so each can be unit-tested in isolation. The full ``render_html_document``
is then an integration sanity-check that everything composes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.vibecodekit_mql5 import ea_docs_render as r


# ────────────────────────────────────────────────────────────────────────────
# Asset loading
# ────────────────────────────────────────────────────────────────────────────


def test_assets_dir_exists() -> None:
    assert r.ASSETS_DIR.is_dir()
    assert r.CSS_PATH.is_file()
    assert (r.ASSETS_DIR / "icons").is_dir()


def test_load_asset_returns_css_content() -> None:
    css = r.load_asset("style.css")
    assert "--c-hot-pink" in css
    assert "--c-yellow" in css
    assert "--c-cyan" in css
    # Print rules ensure PDF parity with HTML preview.
    assert "@page" in css
    assert "@media print" in css


def test_load_asset_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes ea_docs_assets"):
        r.load_asset("../../etc/passwd")


@pytest.mark.parametrize("name", list(r.ICON_NAMES))
def test_load_icon_known_names(name: str) -> None:
    svg = r.load_icon(name)
    assert svg.startswith("<svg")
    assert 'shape-rendering="crispEdges"' in svg


def test_load_icon_unknown_falls_back_to_spark() -> None:
    """Unknown icon names should never crash — fall back to ``spark``."""
    fallback = r.load_icon("does-not-exist")
    spark = r.load_icon("spark")
    assert fallback == spark


# ────────────────────────────────────────────────────────────────────────────
# Component renderers — each in isolation
# ────────────────────────────────────────────────────────────────────────────


def test_render_frontmatter_emits_key_value_pairs() -> None:
    out = r.render_frontmatter({"ea_name": "FooEA", "ea_version": "0.1.0"})
    assert 'class="frontmatter"' in out
    assert "ea_name:" in out
    assert "FooEA" in out
    assert "ea_version:" in out
    assert "0.1.0" in out


def test_render_frontmatter_empty_returns_empty() -> None:
    assert r.render_frontmatter({}) == ""


def test_render_frontmatter_escapes_html_in_values() -> None:
    """User-supplied values must be HTML-escaped."""
    out = r.render_frontmatter({"name": "<script>alert(1)</script>"})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_render_section_header_includes_icon_and_title() -> None:
    out = r.render_section_header("EA Inputs", "code")
    assert 'class="section-header"' in out
    assert "EA INPUTS" not in out  # title is not uppercase'd in HTML (CSS does it)
    assert "EA Inputs" in out
    assert "<svg" in out


def test_render_manifesto_has_decorative_icons_and_claim() -> None:
    content = r.DocContent(
        title_main="Portfolio MR",
        title_jp="ポートフォリオ",
        title_en="Portfolio Mean-Reversion",
    )
    out = r.render_manifesto(content)
    assert 'class="manifesto"' in out
    assert "Portfolio MR" in out
    assert "ポートフォリオ" in out
    assert "Portfolio Mean-Reversion" in out
    # 3 decorative pixel icons in corners.
    assert out.count('class="deco') == 3


def test_render_layer_stack_renders_each_layer_with_color_class() -> None:
    layers = [
        r.LayerSpec("Risk Guard", "DD cap + correlation", "pink", "robot"),
        r.LayerSpec("Signal Fusion", "6 signals fused", "yellow", "code"),
        r.LayerSpec("Execution", "Stealth split", "cyan", "browser"),
    ]
    out = r.render_layer_stack(layers)
    assert 'class="layer-stack"' in out
    assert "Risk Guard" in out and "Signal Fusion" in out and "Execution" in out
    assert "pink" in out and "yellow" in out and "cyan" in out


def test_render_layer_stack_empty_returns_empty() -> None:
    assert r.render_layer_stack([]) == ""


def test_render_timeline_with_highlight() -> None:
    steps = [
        r.TimelineStep("Scan"),
        r.TimelineStep("Build"),
        r.TimelineStep("Ship", highlight=True),
    ]
    out = r.render_timeline(steps)
    assert 'class="timeline"' in out
    assert "Scan" in out and "Build" in out and "Ship" in out
    assert "step highlight" in out
    # Two arrows between three steps.
    assert out.count('class="arrow"') == 2


def test_render_timeline_empty_returns_empty() -> None:
    assert r.render_timeline([]) == ""


def test_render_param_table_groups_rows() -> None:
    rows = [
        r.ParamRow("Risk", "InpRiskPct", "double", "0.5", "%/lệnh"),
        r.ParamRow("Risk", "InpSLPips", "int", "30", "pips"),
        r.ParamRow("Filter", "InpMaxSpread", "int", "2", "pips, skip"),
    ]
    out = r.render_param_table(rows)
    assert 'class="param-table"' in out
    # Only 2 group rows — "Risk" appears once, "Filter" appears once.
    assert out.count('class="group-row"') == 2
    assert "InpRiskPct" in out
    assert "InpSLPips" in out
    assert "InpMaxSpread" in out


def test_render_param_table_escapes_html() -> None:
    rows = [r.ParamRow("G", "Inp<x>", "int", "0", "<bad>")]
    out = r.render_param_table(rows)
    assert "<bad>" not in out
    assert "&lt;bad&gt;" in out


def test_render_take_note_respects_severity() -> None:
    note = r.TakeNote("Broker tz", "GMT+2 assumed", severity="warn", icon="gear")
    out = r.render_take_note(note)
    assert "take-note warn" in out
    assert "Broker tz" in out
    assert "GMT+2 assumed" in out


def test_render_take_note_invalid_severity_falls_back_to_info() -> None:
    note = r.TakeNote("Title", "Body", severity="EXPLOSIVE")
    out = r.render_take_note(note)
    assert "take-note info" in out


# ────────────────────────────────────────────────────────────────────────────
# render_html_document — integration
# ────────────────────────────────────────────────────────────────────────────


def _full_doc() -> r.DocContent:
    return r.DocContent(
        title_main="Portfolio Mean-Reversion EA",
        title_jp="ポートフォリオ平均回帰",
        title_en="Portfolio Mean-Reversion Architecture",
        frontmatter={
            "ea_name": "MaxComplexEA_PortfolioMR",
            "ea_version": "0.1.0",
            "compile": "ok",
        },
        overview_layers=[
            r.LayerSpec("Risk Guard", "DD cap", "pink", "robot"),
            r.LayerSpec("Signal Fusion", "6 fused", "yellow", "code"),
        ],
        strategy_timeline=[
            r.TimelineStep("Scan"),
            r.TimelineStep("Ship", highlight=True),
        ],
        params=[r.ParamRow("Risk", "InpRiskPct", "double", "0.5", "")],
        notes=[r.TakeNote("Note", "Body", "info", "spark")],
    )


def test_render_html_document_returns_self_contained_html() -> None:
    out = r.render_html_document(_full_doc())
    # Sanity: well-formed HTML5.
    assert out.startswith("<!doctype html>")
    assert out.endswith("</html>")
    # CSS inlined (no <link rel="stylesheet">).
    assert "<style>" in out
    assert "--c-hot-pink" in out
    assert "<link" not in out
    # SVG icons inlined (no <img src=...>).
    assert "<svg" in out
    assert "<img" not in out
    # All sections appear.
    assert "MaxComplexEA_PortfolioMR" in out  # frontmatter
    assert "Portfolio Mean-Reversion EA" in out  # manifesto claim
    assert "Risk Guard" in out  # layer
    assert "Ship" in out  # timeline
    assert "InpRiskPct" in out  # param-table
    assert "Note" in out  # take-note


def test_render_html_document_omits_empty_sections() -> None:
    """If a section has no content, no header should appear."""
    content = r.DocContent(title_main="Empty EA")
    out = r.render_html_document(content)
    assert "Empty EA" in out
    # The CSS rules for these classes are still inlined, but no HTML element
    # should actually use them — check for the rendered ``class="..."`` tag.
    assert 'class="section-header"' not in out
    assert 'class="param-table"' not in out
    assert 'class="layer-stack"' not in out
    assert 'class="timeline"' not in out


def test_render_html_document_writes_screenshot_compatible_file(
    tmp_path: Path,
) -> None:
    """Round-trip via filesystem — make sure browser can load the file."""
    out_html = tmp_path / "sample.html"
    out_html.write_text(r.render_html_document(_full_doc()), encoding="utf-8")
    # File is non-empty + properly UTF-8 encoded.
    assert out_html.stat().st_size > 5000
    reread = out_html.read_text(encoding="utf-8")
    assert reread.startswith("<!doctype html>")
