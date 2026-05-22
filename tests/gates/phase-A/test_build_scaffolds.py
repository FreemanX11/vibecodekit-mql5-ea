"""Phase A — build scaffold unit tests (4 tests, one per preset).

Renders each Phase A preset into a tmp dir and verifies:
  - the rendered .mq5 contains the requested name/symbol/tf substitutions
  - the .mqh helpers are co-located
  - a Sets/default.set is present
"""
from __future__ import annotations

from pathlib import Path


from vibecodekit_mql5.build import BuildRequest, build

REPO = Path(__file__).resolve().parents[3]


def _render_preset(preset: str, stack: str, tmp_path: Path) -> Path:
    out = tmp_path / f"{preset}_{stack}"
    req = BuildRequest(
        preset=preset,
        name="DemoEA",
        symbol="EURUSD",
        tf="H1",
        stack=stack,
        out_dir=out,
        scaffolds_root=REPO / "scaffolds",
        include_root=REPO / "Include",
    )
    return build(req)


def _assert_rendered(out: Path) -> None:
    mq5 = out / "DemoEA.mq5"
    assert mq5.is_file(), f"missing rendered .mq5 in {out}"
    text = mq5.read_text(encoding="utf-8")
    assert "{{NAME}}" not in text and "{{SYMBOL}}" not in text and "{{TF}}" not in text
    assert "DemoEA" in text and "EURUSD" in text and "H1" in text
    assert (out / "CPipNormalizer.mqh").is_file()
    assert (out / "CRiskGuard.mqh").is_file()
    assert (out / "CMagicRegistry.mqh").is_file()
    assert (out / "Sets" / "default.set").is_file()
    # FLOW-{vi,en}.md are authoring artifacts for the docs renderer.
    # They must NOT be copied into the rendered output (would pollute
    # the user's MT5 Experts folder + leak template into ship.zip).
    assert not (out / "FLOW-vi.md").exists()
    assert not (out / "FLOW-en.md").exists()


def test_scaffold_stdlib(tmp_path: Path):
    out = _render_preset("stdlib", "netting", tmp_path)
    _assert_rendered(out)


def test_scaffold_wizard_composable(tmp_path: Path):
    out = _render_preset("wizard-composable", "netting", tmp_path)
    _assert_rendered(out)


def test_scaffold_portfolio_basket(tmp_path: Path):
    out = _render_preset("portfolio-basket", "hedging", tmp_path)
    _assert_rendered(out)


def test_scaffold_ml_onnx(tmp_path: Path):
    out = _render_preset("ml-onnx", "python-bridge", tmp_path)
    _assert_rendered(out)
