"""Tests for the best-practice anti-pattern detectors added to lint.py
in Phase C. 5 sampled detectors plus a coverage check; total: 5 unit
tests (the coverage check is itself one of them)."""

from __future__ import annotations

from vibecodekit_mql5 import lint, lint_best_practice


def _findings_for(src: str, code: str) -> list:
    raw = src
    findings = lint.lint_source("file.mq5", raw)
    return [f for f in findings if f.code == code]


def test_best_practice_detectors_are_all_wired():
    codes = {c for c, _ in lint_best_practice.BEST_PRACTICE_DETECTORS}
    expected = {"AP-2", "AP-4", "AP-6", "AP-7", "AP-8", "AP-9", "AP-10",
                "AP-11", "AP-12", "AP-13", "AP-14", "AP-16", "AP-19",
                "AP-22", "AP-23", "AP-24", "AP-25"}
    assert codes == expected
    assert len(codes) == 17


def test_ap2_flags_tight_stoploss():
    src = (
        "// digits-tested: 5,3\n"
        "double sl_pips = 3;\n"
        "void OnTick(){ }\n"
    )
    findings = _findings_for(src, "AP-2")
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_ap7_flags_hardcoded_magic_but_not_registry_use():
    bad = (
        "// digits-tested: 5,3\n"
        "input int magic = 123456;\n"
        "void OnTick(){ }\n"
    )
    good = (
        "// digits-tested: 5,3\n"
        "#include <CMagicRegistry.mqh>\n"
        "CMagicRegistry MagicRegistry;\n"
        "input int magic = 123456;\n"
        "void OnTick(){ }\n"
    )
    assert _findings_for(bad, "AP-7"), "expected AP-7 on hardcoded magic"
    assert not _findings_for(good, "AP-7"), "expected no AP-7 when CMagicRegistry present"


def test_ap13_flags_hardcoded_broker_name():
    src = (
        "// digits-tested: 5,3\n"
        'string broker = "Exness";\n'
        "void OnTick(){ }\n"
    )
    findings = _findings_for(src, "AP-13")
    assert len(findings) == 1


def test_ap14_flags_missing_mfe_mae_logger():
    src = (
        "// digits-tested: 5,3\n"
        "#include <Trade/Trade.mqh>\n"
        "CTrade trade;\n"
        "void OnTick(){ trade.Buy(0.01, NULL, 0, 1.0); }\n"
    )
    findings = _findings_for(src, "AP-14")
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_ap16_flags_custom_trade_class():
    src = (
        "// digits-tested: 5,3\n"
        "class CMyTrade {\n"
        "    void Buy(double lot){}\n"
        "};\n"
    )
    findings = _findings_for(src, "AP-16")
    assert len(findings) == 1


def test_ap22_flags_placeholder_ontick():
    """OnTick that never reaches an order-placing call must WARN AP-22."""
    src = (
        "// digits-tested: 5,3\n"
        "void OnTick(void)\n"
        "  {\n"
        "   // signal logic to be filled in\n"
        "  }\n"
    )
    findings = _findings_for(src, "AP-22")
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_ap22_clean_when_ontick_places_trade():
    """OnTick that calls trade.Buy / trade.Sell must NOT trigger AP-22."""
    src = (
        "// digits-tested: 5,3\n"
        "#include <Trade/Trade.mqh>\n"
        "CTrade trade;\n"
        "void OnTick(void)\n"
        "  {\n"
        "   trade.Buy(0.01, NULL, 0.0, 1.0, 0.0);\n"
        "  }\n"
    )
    findings = _findings_for(src, "AP-22")
    assert findings == []


def test_ap22_clean_when_ontick_places_async():
    """OnTick that calls SendBuyAsync / OrderSendAsync must NOT trigger AP-22."""
    src = (
        "// digits-tested: 5,3\n"
        'void OnTick(void)\n'
        '  {\n'
        '   async_tm.SendBuyAsync(_Symbol, 0.01, 0.0, 0.0);\n'
        '  }\n'
    )
    findings = _findings_for(src, "AP-22")
    assert findings == []


def test_ap23_flags_ctrade_without_retcode_check():
    src = (
        "// digits-tested: 5,3\n"
        "#include <Trade/Trade.mqh>\n"
        "CTrade trade;\n"
        "void OnTick(void)\n"
        "  {\n"
        "   trade.Buy(0.01, NULL, 0.0, 1.0, 2.0);\n"
        "  }\n"
    )
    findings = _findings_for(src, "AP-23")
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_ap23_clean_with_safetrade_manager():
    src = (
        "// digits-tested: 5,3\n"
        '#include "CSafeTradeManager.mqh"\n'
        "CSafeTradeManager trade;\n"
        "void OnTick(void)\n"
        "  {\n"
        "   trade.Buy(0.01, _Symbol, 1.0, 2.0);\n"
        "  }\n"
    )
    assert _findings_for(src, "AP-23") == []


def test_ap24_flags_history_access_without_sync_guard():
    src = (
        "// digits-tested: 5,3\n"
        "int h_fast;\n"
        "int OnInit(){ h_fast = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE); return INIT_SUCCEEDED; }\n"
        "void OnTick(){ double fast[1]; CopyBuffer(h_fast, 0, 0, 1, fast); }\n"
    )
    findings = _findings_for(src, "AP-24")
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_ap24_clean_with_history_sync_guard():
    src = (
        "// digits-tested: 5,3\n"
        '#include "CHistorySync.mqh"\n'
        "CHistorySync history;\n"
        "int h_fast;\n"
        "int OnInit(){ if(!history.EnsureBars(_Symbol, _Period, 300)) return INIT_FAILED;"
        " h_fast = iMA(_Symbol, _Period, 20, 0, MODE_EMA, PRICE_CLOSE); return INIT_SUCCEEDED; }\n"
        "void OnTick(){ double fast[1]; CopyBuffer(h_fast, 0, 0, 1, fast); }\n"
    )
    assert _findings_for(src, "AP-24") == []


def test_ap25_flags_raw_delete_without_guard():
    src = (
        "// digits-tested: 5,3\n"
        "class CThing {};\n"
        "CThing *ptr;\n"
        "void OnDeinit(const int reason){ delete ptr; ptr = NULL; }\n"
    )
    findings = _findings_for(src, "AP-25")
    assert len(findings) == 1
    assert findings[0].severity == "WARN"


def test_ap25_clean_with_safe_delete():
    src = (
        "// digits-tested: 5,3\n"
        '#include "CMemorySafety.mqh"\n'
        "class CThing {};\n"
        "CThing *ptr;\n"
        "void OnDeinit(const int reason){ SAFE_DELETE(ptr); }\n"
    )
    assert _findings_for(src, "AP-25") == []


def test_ap22_skips_service_programs():
    """`#property service` programs use OnStart, not OnTick — out of scope."""
    src = (
        "// digits-tested: 5,3\n"
        "#property service\n"
        "void OnStart(void) {}\n"
    )
    findings = _findings_for(src, "AP-22")
    assert findings == []


def test_best_practice_findings_are_warn_only():
    """The 14 best-practice detectors must never emit ERROR — they are
    advisory and Plan v5 §7 mandates they do NOT gate ship."""
    src = (
        "// digits-tested: 5,3\n"
        "double sl_pips = 3;\n"
        "input int magic = 123456;\n"
        'string broker = "Exness";\n'
        '#include "CSafeTradeManager.mqh"\n'
        "CSafeTradeManager trade;\n"
        "void OnTick(){ trade.Buy(0.01, _Symbol, 1.0, 2.0); }\n"
    )
    findings = lint.lint_source("file.mq5", src)
    best_practice_codes = {c for c, _ in lint_best_practice.BEST_PRACTICE_DETECTORS}
    for f in findings:
        if f.code in best_practice_codes:
            assert f.severity == "WARN", f"{f.code} emitted {f.severity}, must be WARN"
