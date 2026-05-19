"""Tests for the MQL5 ``input`` declaration parser (PR-16).

Covers everything the kit's scaffolds actually emit:

* plain ``input <type> <name> = <default>;``
* ``sinput`` (static input)
* trailing ``// tooltip`` comments
* ``input group "Group Label";`` boundaries
* float defaults, negative numbers, enum types
* edge cases: blank lines, banner comments, no inputs at all
"""

from __future__ import annotations

from scripts.vibecodekit_mql5.ea_docs_inputs import InputDecl, parse_inputs


def test_empty_text_returns_empty_list() -> None:
    assert parse_inputs("") == []


def test_single_int_input() -> None:
    rows = parse_inputs("input int InpMagic = 42;")
    assert rows == [InputDecl(
        group="",
        name="InpMagic",
        type="int",
        default="42",
        tooltip="",
        line_number=1,
    )]


def test_input_with_inline_tooltip() -> None:
    rows = parse_inputs("input double InpRiskPct = 0.5; // % equity per trade")
    assert len(rows) == 1
    assert rows[0].name == "InpRiskPct"
    assert rows[0].type == "double"
    assert rows[0].default == "0.5"
    assert rows[0].tooltip == "% equity per trade"


def test_sinput_supported() -> None:
    rows = parse_inputs("sinput bool InpDebug = false;")
    assert len(rows) == 1
    assert rows[0].name == "InpDebug"
    assert rows[0].type == "bool"
    assert rows[0].default == "false"


def test_group_boundaries() -> None:
    src = '''
input group "Risk";
input double InpRiskPct = 0.5;
input int    InpSLPips  = 30;

input group "Filter";
input int    InpMaxSpread = 2;
'''
    rows = parse_inputs(src)
    assert [r.name for r in rows] == ["InpRiskPct", "InpSLPips", "InpMaxSpread"]
    assert rows[0].group == "Risk"
    assert rows[1].group == "Risk"
    assert rows[2].group == "Filter"


def test_enum_type_kept_verbatim() -> None:
    rows = parse_inputs("input ENUM_TIMEFRAMES InpTF = PERIOD_H1;")
    assert len(rows) == 1
    assert rows[0].type == "ENUM_TIMEFRAMES"
    assert rows[0].default == "PERIOD_H1"


def test_float_default_with_sign() -> None:
    rows = parse_inputs("input double InpATRMult = 2.5;")
    assert rows[0].default == "2.5"


def test_negative_default_preserved() -> None:
    rows = parse_inputs("input double InpMaxSwap = -1.5; // pips / day")
    assert rows[0].default == "-1.5"
    assert rows[0].tooltip == "pips / day"


def test_string_default_preserved_with_quotes() -> None:
    rows = parse_inputs('input string InpComment = "MyEA";')
    assert rows[0].default == '"MyEA"'
    assert rows[0].type == "string"


def test_blank_and_comment_lines_skipped() -> None:
    src = '''
//+------------------------------------------------------------------+
//|                                              MyEA.mq5            |
//+------------------------------------------------------------------+

// All the inputs below are user-tunable.
input int InpMagic = 42;
'''
    rows = parse_inputs(src)
    assert len(rows) == 1
    assert rows[0].name == "InpMagic"


def test_input_group_alone_is_not_a_declaration() -> None:
    """An ``input group`` line should set context but not emit a row."""
    src = '''
input group "Risk";
'''
    rows = parse_inputs(src)
    assert rows == []


def test_multiple_groups_preserve_order() -> None:
    src = '''
input group "A";
input int X = 1;
input group "B";
input int Y = 2;
input group "C";
input int Z = 3;
'''
    rows = parse_inputs(src)
    assert [(r.name, r.group) for r in rows] == [
        ("X", "A"),
        ("Y", "B"),
        ("Z", "C"),
    ]


def test_line_numbers_are_one_based() -> None:
    src = "\n\ninput int X = 1;\n"
    rows = parse_inputs(src)
    assert rows[0].line_number == 3


def test_input_decl_to_dict_roundtrip() -> None:
    d = InputDecl(
        group="Risk", name="X", type="int", default="1", tooltip="hi",
        line_number=5,
    )
    out = d.to_dict()
    assert out == {
        "group": "Risk",
        "name": "X",
        "type": "int",
        "default": "1",
        "tooltip": "hi",
        "line_number": 5,
    }


def test_realistic_scaffold_input_block() -> None:
    """Sanity-check on a multi-section block that mirrors what the
    ``wizard-composable`` scaffold actually emits."""
    src = '''
input group "Risk";
input double InpRiskPct      = 0.5;   // % equity per trade
input int    InpSLPips       = 30;
input int    InpTPPips       = 60;
input int    InpMaxOpenPos   = 3;

input group "Filter";
input int    InpMaxSpread    = 2;     // pips, skip if exceeded
input bool   InpNewsFilter   = true;

input group "Stealth";
sinput bool  InpSplitOrders  = false;
sinput double InpSlippageJitter = 0.5;
'''
    rows = parse_inputs(src)
    names = [r.name for r in rows]
    assert names == [
        "InpRiskPct", "InpSLPips", "InpTPPips", "InpMaxOpenPos",
        "InpMaxSpread", "InpNewsFilter",
        "InpSplitOrders", "InpSlippageJitter",
    ]
    # Groups propagate correctly.
    groups = [r.group for r in rows]
    assert groups[:4] == ["Risk"] * 4
    assert groups[4:6] == ["Filter"] * 2
    assert groups[6:8] == ["Stealth"] * 2
    # Tooltip captured.
    risk_pct = next(r for r in rows if r.name == "InpRiskPct")
    assert risk_pct.tooltip == "% equity per trade"
