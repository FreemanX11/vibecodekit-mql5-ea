"""Derive §5 "Take notes" callouts from a validated ``EaSpec``.

The renderer surfaces a section of opinionated annotations that warn the
trader about non-obvious behaviours of the EA they're about to ship.
These come from a **rule table** — each rule pattern-matches against
one of the optional spec blocks (PR-2 + PR-8: prop_firm / time_exit /
stealth / trailing / partial_close / correlation / swap_filter / logs)
or a signal/preset trait, and emits a localised note in VI or EN.

Pure function, deterministic, hermetic — no network, no env, no LLM.
Adding a new note = add one entry to ``_RULES``.

The output is a list of ``TakeNote`` objects defined in
``ea_docs_render`` so the renderer can drop them straight into HTML.
"""

from __future__ import annotations

from typing import Callable

from .ea_docs_render import TakeNote
from .spec_schema import EaSpec

__all__ = ["derive_take_notes", "SUPPORTED_LANGS"]


SUPPORTED_LANGS = ("vi", "en")


# Per-rule template: ``(predicate, title_template, body_template, severity, icon)``.
#
# Templates may reference ``{spec}`` (the full EaSpec) — render at the
# end via ``str.format``. ``predicate`` returns ``True`` when the rule
# should fire.
#
# Severity drives the take-note card colour (info=cyan, warn=yellow,
# danger=pink). Icon names match the 8 pixel-art icons shipped in
# ``ea_docs_assets/icons/``.

_Rule = tuple[
    Callable[[EaSpec], bool],
    dict[str, str],  # title — keyed by lang
    dict[str, str],  # body  — keyed by lang
    str,             # severity
    str,             # icon
]


def _has_signal_kind(spec: EaSpec, kind: str) -> bool:
    return any(getattr(s, "kind", "") == kind for s in spec.signals)


def _has_onnx(spec: EaSpec) -> bool:
    """ONNX inference is used either as a signal kind or via the ml-onnx preset."""
    return spec.preset == "ml-onnx" or _has_signal_kind(spec, "onnx_predict")


_RULES: list[_Rule] = [
    # --- prop_firm ----------------------------------------------------
    (
        lambda s: s.prop_firm is not None and s.prop_firm.daily_dd_pct is not None,
        {
            "vi": "Prop-firm: daily drawdown {spec.prop_firm.daily_dd_pct}%",
            "en": "Prop-firm: daily drawdown cap {spec.prop_firm.daily_dd_pct}%",
        },
        {
            "vi": ("EA tự dừng giao dịch khi DD trong ngày chạm ngưỡng. "
                   "Giám sát equity real-time, đừng phụ thuộc hoàn toàn vào logic EA — "
                   "broker disconnect là rủi ro lớn nhất."),
            "en": ("EA halts trading when intraday DD hits this threshold. "
                   "Monitor equity in real time — broker disconnects are the "
                   "biggest residual risk."),
        },
        "danger",
        "robot",
    ),
    (
        lambda s: s.prop_firm is not None and s.prop_firm.weekend_flat,
        {
            "vi": "Prop-firm: bắt buộc flat cuối tuần",
            "en": "Prop-firm: weekend flat required",
        },
        {
            "vi": ("EA đóng toàn bộ vị thế trước phiên đóng cửa thứ 6. "
                   "Đảm bảo broker timezone đúng — múi sai sẽ flat sai giờ."),
            "en": ("EA closes every position before Friday close. "
                   "Verify broker timezone — a mismatch flats at the wrong hour."),
        },
        "warn",
        "gear",
    ),

    # --- time_exit ----------------------------------------------------
    (
        lambda s: (s.time_exit is not None
                   and s.time_exit.close_on_friday
                   and s.time_exit.friday_close_hour is not None),
        {
            "vi": "Time-exit: flat thứ 6 lúc {spec.time_exit.friday_close_hour}h",
            "en": "Time-exit: Friday flat at {spec.time_exit.friday_close_hour}h",
        },
        {
            "vi": ("Giả định broker timezone GMT+2 (mặc định của hầu hết broker EU). "
                   "Nếu broker bạn dùng GMT+0/GMT+3, sửa giờ tương ứng."),
            "en": ("Assumes broker timezone GMT+2 (default for most EU brokers). "
                   "Adjust the hour if your broker runs GMT+0 / GMT+3."),
        },
        "info",
        "chevron",
    ),
    (
        lambda s: (s.time_exit is not None
                   and s.time_exit.max_trade_hours is not None),
        {
            "vi": "Time-exit: max hold {spec.time_exit.max_trade_hours}h",
            "en": "Time-exit: max hold {spec.time_exit.max_trade_hours}h",
        },
        {
            "vi": ("Lệnh tự đóng nếu giữ quá ngưỡng này. Phù hợp với "
                   "scalp/intraday — sửa nếu strategy là swing."),
            "en": ("Trades auto-close past this age. Suitable for scalp/intraday — "
                   "adjust if strategy is swing."),
        },
        "info",
        "spark",
    ),

    # --- stealth ------------------------------------------------------
    (
        lambda s: s.stealth is not None and s.stealth.split_orders,
        {
            "vi": "Stealth: split orders đang BẬT",
            "en": "Stealth: split orders ENABLED",
        },
        {
            "vi": ("Lệnh lớn được chia nhỏ + jitter slippage. "
                   "Cộng dồn ~0.1-0.5 pip cost mỗi round-trip — cân nhắc khi SL nhỏ."),
            "en": ("Large orders split + slippage jitter. "
                   "Adds ~0.1-0.5 pip cost per round-trip — careful with tight SLs."),
        },
        "warn",
        "rocket",
    ),
    (
        lambda s: s.stealth is not None and s.stealth.avoid_round_numbers,
        {
            "vi": "Stealth: tránh round numbers",
            "en": "Stealth: avoid round numbers",
        },
        {
            "vi": ("SL/TP né các mức round (1.1000, 1.2000). "
                   "Có thể làm SL lệch vài pip so với spec — không phải bug."),
            "en": ("SL/TP avoids round levels (1.1000, 1.2000). "
                   "Actual stops may drift a few pips from spec — not a bug."),
        },
        "info",
        "spark",
    ),

    # --- trailing -----------------------------------------------------
    (
        lambda s: (s.trailing is not None
                   and s.trailing.enabled
                   and s.trailing.mode == "atr"),
        {
            "vi": "Trailing: ATR-adaptive (mult {spec.trailing.atr_mult})",
            "en": "Trailing: ATR-adaptive (mult {spec.trailing.atr_mult})",
        },
        {
            "vi": ("Trailing stop bám theo ATR — SL rộng hơn trong vol cao, "
                   "ngắn hơn khi yên. Test trên cả regime trending và ranging."),
            "en": ("Trailing stop scales with ATR — wider in high-vol regimes, "
                   "tighter when quiet. Test on both trending and ranging data."),
        },
        "info",
        "gear",
    ),

    # --- partial_close ------------------------------------------------
    (
        lambda s: (s.partial_close is not None
                   and s.partial_close.enabled
                   and bool(s.partial_close.levels)),
        {
            "vi": "Partial close ({levels} level)",
            "en": "Partial close ({levels} level)",
        },
        {
            "vi": ("EA đóng từng phần khi profit chạm các mốc. "
                   "Phù hợp tâm lý nhưng làm expectancy giảm — backtest kỹ."),
            "en": ("EA scales out at profit milestones. "
                   "Comforting psychologically, but cuts expectancy — "
                   "backtest carefully."),
        },
        "info",
        "chevron",
    ),

    # --- correlation --------------------------------------------------
    (
        lambda s: (s.correlation is not None
                   and s.correlation.max_correlated_positions is not None),
        {
            "vi": "Correlation veto (max {spec.correlation.max_correlated_positions})",
            "en": "Correlation veto (max {spec.correlation.max_correlated_positions})",
        },
        {
            "vi": ("EA chặn vào lệnh khi đã có quá nhiều cặp tương quan mở. "
                   "Cần symbol_group đầy đủ để hiệu quả — kiểm tra danh sách."),
            "en": ("EA blocks entries when too many correlated pairs are open. "
                   "Effectiveness depends on a complete symbol_group — verify."),
        },
        "info",
        "browser",
    ),

    # --- swap_filter --------------------------------------------------
    (
        lambda s: (s.swap_filter is not None
                   and s.swap_filter.skip_wednesday_triple_swap),
        {
            "vi": "Swap: skip triple-swap thứ 4",
            "en": "Swap: skip Wednesday triple-swap",
        },
        {
            "vi": ("Hầu hết broker tính swap ×3 hôm thứ 4 (rollover thứ 7). "
                   "Một số broker rollover khác hôm — verify trước khi live."),
            "en": ("Most brokers charge 3× swap on Wednesday (Saturday rollover). "
                   "Some brokers roll over on different days — verify before live."),
        },
        "warn",
        "gear",
    ),

    # --- logs ---------------------------------------------------------
    (
        lambda s: s.logs is not None and s.logs.redact_account_numbers,
        {
            "vi": "Logs: tự động ẩn account number",
            "en": "Logs: account numbers redacted",
        },
        {
            "vi": "Log file an toàn để chia sẻ với support — không lộ account.",
            "en": "Log file is safe to share with support — no account number exposed.",
        },
        "info",
        "chat",
    ),

    # --- signals / preset --------------------------------------------
    (
        lambda s: _has_onnx(s),
        {
            "vi": "ONNX inference (yêu cầu MT5 build ≥ 5572)",
            "en": "ONNX inference (requires MT5 build ≥ 5572)",
        },
        {
            "vi": ("EA load model ONNX khi runtime — đảm bảo MT5 đủ mới. "
                   "Model file phải đặt trong MQL5/Files/ trước khi compile."),
            "en": ("EA loads an ONNX model at runtime — make sure MT5 is fresh. "
                   "Model file must live under MQL5/Files/ before compile."),
        },
        "warn",
        "robot",
    ),
    (
        lambda s: s.mode == "enterprise",
        {
            "vi": "Mode: enterprise (7-layer permission gate)",
            "en": "Mode: enterprise (7-layer permission gate)",
        },
        {
            "vi": ("Permission gate enterprise yêu cầu Trader-17 đầy đủ trước khi ship. "
                   "Scaffold không có logic giao dịch thật → fail là đúng."),
            "en": ("Enterprise permission gate requires full Trader-17 before shipping. "
                   "Scaffolds with no real trade wiring will fail by design."),
        },
        "info",
        "code",
    ),
]


def derive_take_notes(spec: EaSpec, lang: str = "vi") -> list[TakeNote]:
    """Run the rule table against ``spec`` and return localised notes.

    ``lang`` falls back to ``vi`` for any value outside ``SUPPORTED_LANGS``.
    """
    if lang not in SUPPORTED_LANGS:
        lang = "vi"

    notes: list[TakeNote] = []
    for predicate, title_tpl, body_tpl, severity, icon in _RULES:
        try:
            fires = predicate(spec)
        except (AttributeError, TypeError):
            fires = False
        if not fires:
            continue

        # ``levels`` is the only variable some templates need but isn't
        # accessible via dotted lookup; precompute and merge.
        levels = (
            len(spec.partial_close.levels)
            if spec.partial_close is not None else 0
        )
        try:
            title = title_tpl[lang].format(spec=spec, levels=levels)
            body = body_tpl[lang].format(spec=spec, levels=levels)
        except (KeyError, AttributeError):
            continue
        notes.append(
            TakeNote(title=title, body=body, severity=severity, icon=icon)
        )

    return notes
