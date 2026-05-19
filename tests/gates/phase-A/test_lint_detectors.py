"""Phase A — lint detector unit tests (8 tests, one per critical AP)."""
from __future__ import annotations

from pathlib import Path


from vibecodekit_mql5.lint import lint_source

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _codes(src: str) -> list[str]:
    return [f.code for f in lint_source("inline.mq5", src)]


def _findings(filename: str) -> list:
    src = (FIXTURES / filename).read_text(encoding="utf-8")
    return lint_source(filename, src)


def test_detector_ap1_no_sl():
    codes = [f.code for f in _findings("ap_01_no_sl.mq5")]
    assert "AP-1" in codes


def test_detector_ap3_lot_fixed():
    codes = [f.code for f in _findings("ap_03_lot_fixed.mq5")]
    assert "AP-3" in codes


def test_detector_ap5_overfitted():
    codes = [f.code for f in _findings("ap_05_overfitted.mq5")]
    assert "AP-5" in codes


def test_detector_ap15_raw_ordersend():
    codes = [f.code for f in _findings("ap_15_raw_ordersend.mq5")]
    assert "AP-15" in codes


def test_detector_ap17_webrequest_ontick():
    codes = [f.code for f in _findings("ap_17_webrequest_ontick.mq5")]
    assert "AP-17" in codes


def test_detector_ap18_async_no_handler():
    codes = [f.code for f in _findings("ap_18_async_no_handler.mq5")]
    assert "AP-18" in codes


def test_detector_ap20_hardcoded_pip():
    codes = [f.code for f in _findings("ap_20_hardcoded_pip.mq5")]
    assert "AP-20" in codes


def test_detector_ap21_jpy_xau_broken():
    # Has only `digits-tested: 5` ⇒ < 2 classes ⇒ WARN AP-21.
    findings = _findings("ap_21_jpy_xau_broken.mq5")
    ap21 = [f for f in findings if f.code == "AP-21"]
    assert ap21
    assert ap21[0].severity == "WARN"


def test_detector_ap21_accepts_boxed_comment_in_scaffold():
    """Wizard scaffolds emit `//| digits-tested: 5, 3 |` inside the
    MetaEditor box-comment header. AP-21 must accept that as a valid
    multi-class declaration, not flag it as missing/single-class."""
    from vibecodekit_mql5.lint import lint_source
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    scaffold = repo_root / "scaffolds" / "wizard-composable" / "netting" / "EAName.mq5"
    findings = lint_source(str(scaffold), scaffold.read_text())
    ap21 = [f for f in findings if f.code == "AP-21"]
    assert ap21 == [], f"AP-21 false-positive on scaffold box comment: {ap21}"
