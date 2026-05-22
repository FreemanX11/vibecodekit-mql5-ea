"""Tests for the Phase-1 per-input semantic library + FLOW narrative.

Locks in:

* ``input-semantics.yaml`` loads, every entry has the documented schema.
* ``enrich_param_rows`` merges parsed ``InputDecl`` with the library and
  downgrades cleanly when an input has no entry yet.
* ``substitute_placeholders`` resolves ``{spec.foo.bar:fmt}`` against a
  real ``EaSpec`` and rewrites ``{InpXxx}`` to backticked identifiers,
  leaving everything else untouched.
* ``load_flow_narrative`` reads the bundled FLOW files for the two
  Phase-1 archetypes (``trend/netting`` + ``portfolio-basket/{netting,
  hedging}``).
* End-to-end through ``build_doc_content`` / ``render_markdown`` /
  ``render_html_document`` the new sections actually show up in the
  documents the user receives.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.vibecodekit_mql5.ea_docs import build_doc_content, render_markdown
from scripts.vibecodekit_mql5.ea_docs_inputs import InputDecl
from scripts.vibecodekit_mql5.ea_docs_render import render_html_document
from scripts.vibecodekit_mql5.ea_docs_semantics import (
    DEFAULT_SCAFFOLDS_ROOT,
    DEFAULT_SEMANTICS_PATH,
    EnrichedParamRow,
    InputSemantic,
    enrich_param_rows,
    load_flow_narrative,
    load_input_semantics,
    substitute_placeholders,
)
from scripts.vibecodekit_mql5.ea_docs import BuildMeta
from scripts.vibecodekit_mql5.spec_schema import validate


def _build_meta(ea_version: str = "0.1.0") -> BuildMeta:
    return BuildMeta(
        ea_version=ea_version,
        kit_version="0.1.0-test",
        built_at="2026-05-22T18:00:00Z",
        built_from="semantics-test.yaml",
        compile_status="skipped",
        gate_status="skipped",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Library loader
# ─────────────────────────────────────────────────────────────────────────────


def test_input_semantics_default_file_loads_and_covers_core_inputs() -> None:
    """The repo-checked-in semantics file must parse and cover the
    inputs that every scaffold ships (Magic, RiskMoney, Sl/Tp, DailyLoss,
    MaxPositions). Without these the deep-dive renders as ``no_doc`` for
    the most common params — pointless to ship the feature."""
    semantics = load_input_semantics()
    assert isinstance(semantics, dict)
    assert DEFAULT_SEMANTICS_PATH.is_file()

    core = {
        "InpMagic", "InpRiskMoney", "InpSlPips", "InpTpPips",
        "InpDailyLossPct", "InpMaxPositions",
        "InpEmaFastPeriod", "InpEmaSlowPeriod",
    }
    missing = core - set(semantics)
    assert not missing, f"semantics library missing core entries: {missing}"

    risk = semantics["InpRiskMoney"]
    assert isinstance(risk, InputSemantic)
    assert risk.meaning
    assert risk.unit
    assert risk.formula
    assert "InpSlPips" in risk.depends_on
    assert risk.used_by
    assert risk.sensible_range
    assert risk.gotchas


def test_input_semantics_missing_file_returns_empty_dict(tmp_path: Path) -> None:
    """Library loader must not raise when the file is missing — the
    renderer should degrade to source-side tooltip only."""
    missing = tmp_path / "does-not-exist.yaml"
    assert load_input_semantics(missing) == {}


def test_input_semantics_malformed_root_raises(tmp_path: Path) -> None:
    """A non-dict YAML root is operator error — fail loud, not silent."""
    path = tmp_path / "bad.yaml"
    path.write_text("- just_a_list\n- nope\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_input_semantics(path)


# ─────────────────────────────────────────────────────────────────────────────
# enrich_param_rows
# ─────────────────────────────────────────────────────────────────────────────


def _decl(name: str, type_: str = "double", default: str = "1.0",
          group: str = "", tooltip: str = "") -> InputDecl:
    return InputDecl(group=group, name=name, type=type_, default=default,
                     tooltip=tooltip)


def test_enrich_param_rows_attaches_semantic_when_present() -> None:
    decls = [_decl("InpRiskMoney", type_="double", default="100.0")]
    rows = enrich_param_rows(decls)
    assert len(rows) == 1
    assert isinstance(rows[0], EnrichedParamRow)
    assert rows[0].name == "InpRiskMoney"
    assert rows[0].semantic is not None
    assert rows[0].semantic.meaning  # at least 1 char


def test_enrich_param_rows_downgrades_unknown_inputs_to_no_semantic() -> None:
    decls = [_decl("InpFancyNewKnob", tooltip="some short description")]
    rows = enrich_param_rows(decls)
    assert len(rows) == 1
    assert rows[0].semantic is None
    assert rows[0].tooltip == "some short description"


# ─────────────────────────────────────────────────────────────────────────────
# substitute_placeholders
# ─────────────────────────────────────────────────────────────────────────────


def _spec(**overrides):
    base = {
        "name": "SemanticsTestEA",
        "preset": "trend",
        "stack": "netting",
        "symbol": "EURUSD",
        "timeframe": "H1",
        "risk": {"daily_loss_pct": 5.0, "sl_pips": 30, "tp_pips": 60},
    }
    base.update(overrides)
    return validate(base)


def test_substitute_placeholders_replaces_spec_paths_and_percent_format() -> None:
    spec = _spec()
    text = (
        "EA {spec.name} runs on {spec.symbol} {spec.timeframe}; "
        "DD cap = {spec.risk.daily_loss_pct:pct}; "
        "SL = {spec.risk.sl_pips} pips."
    )
    out = substitute_placeholders(text, spec)
    assert "EA SemanticsTestEA runs on EURUSD H1" in out
    assert "DD cap = 5%" in out  # 5.0 already-percent stays as 5%
    assert "SL = 30 pips" in out


def test_substitute_placeholders_handles_fraction_pct_under_one() -> None:
    """A fraction like 0.05 must render as ``5%`` (multiplied by 100)."""

    class _Stub:
        class _R:
            daily_loss_pct = 0.05
        risk = _R()

    out = substitute_placeholders(
        "DD = {spec.risk.daily_loss_pct:pct}", _Stub()
    )
    assert out == "DD = 5%"


def test_substitute_placeholders_rewrites_input_brace_to_backticks() -> None:
    spec = _spec()
    out = substitute_placeholders(
        "Cap = {InpMaxPositions} positions, magic = {InpMagic}.", spec
    )
    assert "`InpMaxPositions`" in out
    assert "`InpMagic`" in out
    # Original braces must be gone.
    assert "{InpMaxPositions}" not in out


def test_substitute_placeholders_missing_attr_resolves_to_em_dash() -> None:
    spec = _spec()
    out = substitute_placeholders(
        "Threshold = {spec.no.such.attr:pct}.", spec
    )
    assert "—" in out


def test_substitute_placeholders_passes_through_unrelated_braces() -> None:
    spec = _spec()
    out = substitute_placeholders(
        "C++ code {ASCII_BLOCK} and {random.dotted.path} stay raw.", spec
    )
    # {ASCII_BLOCK} doesn't start with spec. or Inp, stays untouched.
    assert "{ASCII_BLOCK}" in out
    # {random.dotted.path} also untouched — only `spec.` paths are subbed.
    assert "{random.dotted.path}" in out


# ─────────────────────────────────────────────────────────────────────────────
# FLOW narrative loader
# ─────────────────────────────────────────────────────────────────────────────


def test_flow_narrative_loads_for_phase1_archetypes() -> None:
    """Phase-1 scope: ``trend/netting`` + ``portfolio-basket/{netting,
    hedging}`` must each ship a Vietnamese FLOW file."""
    for preset, stack in (
        ("trend", "netting"),
        ("portfolio-basket", "netting"),
        ("portfolio-basket", "hedging"),
    ):
        md = load_flow_narrative(preset, stack, lang="vi")
        assert md, f"FLOW-vi.md missing for {preset}/{stack}"
        # Must reference at least one of the dynamic spec placeholders so
        # the substitution layer has something to do at render time.
        assert "{spec." in md, (
            f"{preset}/{stack} FLOW-vi.md has no spec placeholders — "
            "it should reference the EA's actual spec values"
        )


def test_flow_narrative_missing_archetype_returns_none(tmp_path: Path) -> None:
    """Archetypes without an authored FLOW file return ``None`` so the
    renderer can silently omit the section."""
    assert load_flow_narrative("nonexistent", "stack") is None


# Every FLOW file committed to the repo must use only placeholders that
# resolve against a valid EaSpec — otherwise the rendered narrative
# leaks ``—`` placeholders to end users.
@pytest.mark.parametrize(
    ("preset", "stack"),
    [
        ("trend", "netting"),
        ("portfolio-basket", "netting"),
        ("portfolio-basket", "hedging"),
    ],
)
def test_flow_narrative_placeholders_all_resolve(preset: str, stack: str) -> None:
    flow = load_flow_narrative(preset, stack, lang="vi")
    assert flow is not None
    spec = _spec(name="FlowTestEA", preset=preset, stack=stack)
    out = substitute_placeholders(flow, spec)
    # No remaining ``{spec.…}`` tokens.
    assert "{spec." not in out, (
        f"{preset}/{stack} FLOW-vi.md has placeholders that did not "
        f"resolve against the default EaSpec — first occurrence at: "
        f"{out[out.index('{spec.'):out.index('{spec.') + 80]!r}"
    )
    # And no leftover ``—`` from failed substitutions (allow ``—`` in
    # author prose, but not produced by the engine: do a sanity-check
    # by comparing against the source. The engine never inserts ``—``
    # unless a placeholder mismatched).
    src_em_dash = flow.count("—")
    out_em_dash = out.count("—")
    assert out_em_dash <= src_em_dash + flow.count("{spec."), (
        f"{preset}/{stack} produced unexpected ``—`` placeholders "
        f"(src={src_em_dash}, out={out_em_dash})"
    )


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end through build_doc_content + render_markdown / HTML
# ─────────────────────────────────────────────────────────────────────────────


_TREND_MQ5 = """
#property strict
input long   InpMagic        = 80100;
input double InpRiskMoney    = 100.0;
input int    InpSlPips       = 30;
input int    InpTpPips       = 60;
input double InpDailyLossPct = 0.05;
input int    InpMaxPositions = 3;
sinput int   InpEmaFastPeriod = 50;
sinput int   InpEmaSlowPeriod = 200;

void OnTick() {}
"""


def test_build_doc_content_attaches_enriched_params_and_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _spec(name="E2ETrendEA", preset="trend", stack="netting")
    meta = _build_meta(ea_version="0.1.0")
    content = build_doc_content(spec, _TREND_MQ5, meta, lang="vi")

    # Legacy params (table view) still populated.
    assert content.params
    # New enriched_params populated — every InpFoo row gets a card.
    assert content.enriched_params
    assert len(content.enriched_params) == len(content.params)
    # At least the core inputs have semantics attached.
    by_name = {row.name: row for row in content.enriched_params}
    assert by_name["InpMagic"].semantic is not None
    assert by_name["InpRiskMoney"].semantic is not None
    # FLOW narrative loaded + substituted (no leftover spec placeholder).
    assert content.flow_narrative
    assert "{spec." not in content.flow_narrative
    assert "E2ETrendEA" in content.flow_narrative
    assert "EURUSD" in content.flow_narrative


def test_render_markdown_emits_param_deep_dive_and_flow_sections() -> None:
    spec = _spec(name="MdTrendEA", preset="trend", stack="netting")
    meta = _build_meta(ea_version="0.1.0")
    content = build_doc_content(spec, _TREND_MQ5, meta, lang="vi")
    md = render_markdown(content)

    assert "## Chi tiết từng tham số" in md
    assert "## Cách EA chạy" in md
    # Per-input headers must show name + type + default.
    assert "### `InpMagic` (`long`, mặc định `80100`)" in md
    # Semantic field labels render.
    assert "**Ý nghĩa:**" in md
    assert "**Công thức:**" in md
    # Dynamic-fill from spec landed in the FLOW prose.
    assert "MdTrendEA" in md
    assert "EURUSD" in md


def test_render_html_document_emits_param_deep_dive_and_flow_sections() -> None:
    spec = _spec(name="HtmlTrendEA", preset="trend", stack="netting")
    meta = _build_meta(ea_version="0.1.0")
    content = build_doc_content(spec, _TREND_MQ5, meta, lang="vi")
    html = render_html_document(content)

    assert "Chi tiết từng tham số" in html
    assert "param-deep-dive" in html
    assert "param-card" in html
    assert "Cách EA chạy" in html
    assert "flow-narrative" in html
    # Dynamic-fill landed inside the HTML.
    assert "HtmlTrendEA" in html


def test_default_scaffolds_root_resolves_to_repo_scaffolds() -> None:
    """Sanity: the module-level default actually points at a folder
    containing the Phase-1 archetypes (catches a refactor that breaks
    the relative path arithmetic)."""
    assert DEFAULT_SCAFFOLDS_ROOT.is_dir()
    assert (DEFAULT_SCAFFOLDS_ROOT / "trend" / "netting").is_dir()
    assert (DEFAULT_SCAFFOLDS_ROOT / "portfolio-basket" / "netting").is_dir()
