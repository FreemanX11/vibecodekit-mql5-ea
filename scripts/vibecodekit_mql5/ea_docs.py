"""Orchestrator + CLI for the post-build EA documentation generator.

Top-level entrypoint for the PR-16 content layer:

* ``build_doc_content`` — assemble a ``DocContent`` from a validated
  ``EaSpec`` + raw ``.mq5`` source + build metadata. Pure function.
* ``render_markdown`` — parallel renderer to ``render_html_document``
  in ``ea_docs_render`` — produces a git-diffable, agent-readable
  ``<EAName>.docs.md``.
* ``main`` — ``mql5-ea-docs`` CLI: ``--out <dir>`` writes one or both
  of ``<EAName>.docs.html`` and ``<EAName>.docs.md``.

Out of scope for this PR (handled in PR-17 / PR-18):

* Pipeline integration into ``auto_build.run_pipeline``.
* Headless-Chrome PDF export.
* Dashboard embed.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .ea_docs_inputs import InputDecl, parse_inputs
from .ea_docs_notes import derive_take_notes
from .ea_docs_render import (
    DocContent,
    LayerSpec,
    ParamRow,
    TakeNote,
    TimelineStep,
    render_html_document,
    section_labels,
    table_headers,
)
from .spec_schema import EaSpec, validate


__all__ = [
    "BuildMeta",
    "build_doc_content",
    "render_markdown",
    "main",
]


@dataclass(frozen=True)
class BuildMeta:
    """Build-time metadata embedded in the docs frontmatter."""

    ea_version: str = "0.1.0"
    kit_version: str = "unknown"
    built_at: str = ""  # ISO-8601; empty → caller wants ``now``
    built_from: str = ""  # spec path or sha256
    compile_status: str = ""  # e.g. "ok (ex5 16498 bytes, 0 errors)"
    gate_status: str = ""  # e.g. "fail (Trader-17: 6/17)"

    @classmethod
    def now(cls, **kwargs: str) -> "BuildMeta":
        defaults = {
            "built_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
        }
        defaults.update(kwargs)
        return cls(**defaults)


# Layer titles + captions for the §2 "System Architecture" stack.
# Vietnamese is the project default; English is kept for parity.
# Code identifiers like ``magic registry`` / ``async order book`` are
# intentional borrow-words — they're MQL5 / trading-engine terms users
# read in MetaTrader docs, not English explanations to translate.
_OVERVIEW_LAYER_TEMPLATES: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "vi": {
        "risk": ("Quản lý vốn",
                 "Tính size + chặn DD ngày + veto correlation",
                 "pink", "robot"),
        "signals": ("Tổng hợp tín hiệu",
                    "{n} signal · fuse {logic} · {filters} filter",
                    "yellow", "code"),
        "execution": ("Thực thi lệnh",
                      "Stealth, magic registry, async order book",
                      "cyan", "browser"),
    },
    "en": {
        "risk": ("Risk Guard", "Position sizing + daily DD cap + correlation veto",
                 "pink", "robot"),
        "signals": ("Signal Fusion",
                    "{n} signal · {logic} fuse · {filters} filter",
                    "yellow", "code"),
        "execution": ("Execution",
                      "Stealth, magic registry, async order book",
                      "cyan", "browser"),
    },
}

_TIMELINE_LABELS = {
    "vi": ("Quét", "Soạn", "Kiểm", "Phát hành"),
    "en": ("Scan", "Compose", "Verify", "Ship"),
}

_TIMELINE_CAPTIONS = {
    # Verbs are Vietnamese; project-level CLI/stage nouns (``spec``,
    # ``scaffold``, ``lint``, ``gate``, ``dashboard``) stay as users see
    # them in the CLI per project convention.
    "vi": (
        "Đọc spec",
        "Sinh code từ scaffold",
        "Quét lint + cổng kiểm quyền",
        "Biên dịch + dashboard",
    ),
    "en": ("Read spec", "Render scaffold", "Lint + gate", "Compile + dashboard"),
}

# Decorative subtitle that sits above the manifesto card's main claim.
# Was Japanese decorative text in PR-15/16; user requested 100% Vietnamese
# in the Vietnamese docs while keeping the visual 「 」 bracket aesthetic.
_TITLE_SUBTITLE = {
    "vi": {
        "portfolio": "Danh mục",
        "default": "Hệ thống",
        "suffix": "Kiến trúc",
    },
    "en": {
        "portfolio": "Portfolio",
        "default": "System",
        "suffix": "Architecture",
    },
}


def build_doc_content(
    spec: EaSpec,
    mq5_text: str,
    build_meta: BuildMeta,
    lang: str = "vi",
) -> DocContent:
    """Compose the full ``DocContent`` model for one EA build."""
    lang = lang if lang in ("vi", "en") else "vi"

    frontmatter = {
        "ea_name": spec.name,
        "ea_version": build_meta.ea_version,
        "kit_version": build_meta.kit_version,
        "built_at": build_meta.built_at,
        "built_from": build_meta.built_from or "(spec inline)",
        "symbol": spec.symbol,
        "timeframe": spec.timeframe,
        "mode": spec.mode,
    }
    if build_meta.compile_status:
        frontmatter["compile"] = build_meta.compile_status
    if build_meta.gate_status:
        frontmatter["gate"] = build_meta.gate_status

    layer_templates = _OVERVIEW_LAYER_TEMPLATES[lang]
    signal_kinds = ", ".join(s.kind for s in spec.signals) or "(none)"
    overview = [
        LayerSpec(*layer_templates["risk"]),
        LayerSpec(
            layer_templates["signals"][0],
            layer_templates["signals"][1].format(
                n=len(spec.signals),
                logic=spec.signal_logic,
                filters=len(spec.filters),
            ),
            layer_templates["signals"][2],
            layer_templates["signals"][3],
        ),
        LayerSpec(*layer_templates["execution"]),
    ]
    # Tuck the raw signal-kind list into the closing HTML so the user
    # always sees what was wired in — no need to ``cat`` the .mq5.
    closing_html_fragment = _render_signals_summary(signal_kinds, lang)

    labels = _TIMELINE_LABELS[lang]
    captions = _TIMELINE_CAPTIONS[lang]
    timeline = [
        TimelineStep(labels[0], captions[0], icon="code"),
        TimelineStep(labels[1], captions[1], icon="gear"),
        TimelineStep(labels[2], captions[2], icon="spark"),
        TimelineStep(labels[3], captions[3], icon="rocket", highlight=True),
    ]

    params = [_input_to_param_row(d) for d in parse_inputs(mq5_text)]
    notes = derive_take_notes(spec, lang=lang)

    subtitle = _TITLE_SUBTITLE[lang]
    title_jp = (
        subtitle["portfolio"]
        if "portfolio" in spec.name.lower()
        else subtitle["default"]
    )
    title_en_suffix = subtitle["suffix"]

    return DocContent(
        title_main=spec.name.replace("_", " "),
        title_jp=title_jp,
        title_en=f"{spec.name} {title_en_suffix}",
        frontmatter=frontmatter,
        overview_layers=overview,
        strategy_timeline=timeline,
        params=params,
        notes=notes,
        closing_html=closing_html_fragment,
        lang=lang,
    )


def _input_to_param_row(decl: InputDecl) -> ParamRow:
    return ParamRow(
        group=decl.group,
        name=decl.name,
        type=decl.type,
        default=decl.default,
        note=decl.tooltip,
    )


def _render_signals_summary(signal_kinds: str, lang: str) -> str:
    """Tiny closing fragment showing the wired signal kinds verbatim.

    ``signal_kinds`` is user-controlled (via ``spec.signals[*].kind``);
    although the CLI path validates kinds against an allowlist, the
    public ``build_doc_content`` API accepts any ``EaSpec`` directly,
    so escape defensively here — same convention as every other
    renderer in ``ea_docs_render``.
    """
    label = _render_signals_summary_labels(lang)
    return (
        '<div class="block yellow">'
        f'<h3 class="h-card">{html.escape(label)}</h3>'
        f'<p class="t-caption" style="font-family:var(--font-mono)">'
        f'{html.escape(signal_kinds)}'
        '</p>'
        '</div>'
    )


# ────────────────────────────────────────────────────────────────────────────
# Markdown renderer
# ────────────────────────────────────────────────────────────────────────────


def render_markdown(content: DocContent) -> str:
    """Render ``DocContent`` as Markdown.

    Parallel to ``ea_docs_render.render_html_document`` — same data,
    git-diffable text format. Intended for agent consumption and
    side-by-side review in PRs. Section headers and table column
    labels are localized via ``content.lang``; code identifiers
    (``input`` names, MQL5 types, defaults) are rendered verbatim.
    """
    labels = section_labels(content.lang)
    th = table_headers(content.lang)
    lines: list[str] = []
    lines.append("---")
    for k, v in content.frontmatter.items():
        lines.append(f"{k}: {v}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {content.title_main}")
    if content.title_jp:
        lines.append(f"_「{content.title_jp}」_")
    if content.title_en:
        lines.append(f"_{content.title_en}_")
    lines.append("")

    if content.overview_layers:
        lines.append(f"## {labels['overview']}")
        lines.append("")
        for layer in content.overview_layers:
            lines.append(f"- **{layer.title}** — {layer.caption}")
        lines.append("")

    if content.strategy_timeline:
        lines.append(f"## {labels['strategy']}")
        lines.append("")
        flow = " → ".join(
            f"**{s.label}**" if s.highlight else s.label
            for s in content.strategy_timeline
        )
        lines.append(flow)
        lines.append("")
        for step in content.strategy_timeline:
            if step.caption:
                lines.append(f"- _{step.label}_: {step.caption}")
        lines.append("")

    if content.params:
        lines.append(f"## {labels['params']}")
        lines.append("")
        lines.append(f"| {th[0]} | {th[1]} | {th[2]} | {th[3]} | {th[4]} |")
        lines.append("|---|---|---|---|---|")
        for p in content.params:
            note = (p.note or "").replace("|", "\\|")
            lines.append(
                f"| {p.group or '-'} | `{p.name}` | `{p.type}` | "
                f"`{p.default}` | {note} |"
            )
        lines.append("")

    if content.notes:
        lines.append(f"## {labels['notes']}")
        lines.append("")
        sev_prefix = {
            "info": "ℹ️", "warn": "⚠️", "danger": "🔥",
        }
        for n in content.notes:
            prefix = sev_prefix.get(n.severity, "•")
            lines.append(f"> {prefix} **{n.title}**")
            lines.append(f"> {n.body}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _render_signals_summary_labels(lang: str) -> str:
    """Localized label for the closing "wired signals" fragment."""
    return {"vi": "Tín hiệu đã wire", "en": "Wired signals"}.get(lang, "Tín hiệu đã wire")


# ────────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────────


# Distribution name from ``pyproject.toml``. Do not confuse with the
# import-path module name ``vibecodekit_mql5`` (with underscore) —
# ``importlib.metadata.version`` keys off the *distribution* name.
_DIST_NAME = "vibecodekit-mql5-ea"


def _kit_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        return version(_DIST_NAME)
    except PackageNotFoundError:
        return "unknown"
    except ImportError:
        return "unknown"


def _load_spec_dict(spec_path: Path) -> dict:
    text = spec_path.read_text(encoding="utf-8")
    if spec_path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover — exercised via auto-build
            raise RuntimeError(
                "PyYAML is required to read .yaml specs"
            ) from exc
        return yaml.safe_load(text)
    return json.loads(text)


def _write_outputs(
    out_dir: Path,
    ea_name: str,
    content: DocContent,
    formats: Iterable[str],
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    if "html" in formats:
        path = out_dir / f"{ea_name}.docs.html"
        path.write_text(render_html_document(content), encoding="utf-8")
        written["html"] = str(path)
    if "md" in formats:
        path = out_dir / f"{ea_name}.docs.md"
        path.write_text(render_markdown(content), encoding="utf-8")
        written["md"] = str(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="mql5-ea-docs",
        description=(
            "Generate a post-build EA documentation deliverable "
            "(HTML + Markdown) from an ea-spec.yaml + the rendered .mq5."
        ),
    )
    parser.add_argument("spec", type=Path,
                        help="Path to the validated ea-spec.yaml / .json")
    parser.add_argument("mq5", type=Path,
                        help="Path to the rendered <EAName>.mq5 source")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output directory for .docs.html / .docs.md")
    parser.add_argument("--lang", choices=("vi", "en"), default="vi",
                        help="Documentation language (default: vi)")
    parser.add_argument(
        "--formats", default="html,md",
        help="Comma-separated list of output formats (html, md). "
             "Default: html,md",
    )
    parser.add_argument("--ea-version", default="0.1.0",
                        help="EA version string for the frontmatter")
    parser.add_argument("--compile-status", default="",
                        help="Compile status line for the frontmatter")
    parser.add_argument("--gate-status", default="",
                        help="Permission-gate status line for the frontmatter")
    args = parser.parse_args(argv)

    try:
        spec_dict = _load_spec_dict(args.spec)
        spec = validate(spec_dict)
        mq5_text = args.mq5.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError as exc:
        print(f"error: file not found: {exc}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    invalid = formats - {"html", "md"}
    if invalid:
        print(
            f"error: unknown formats: {sorted(invalid)} "
            "(supported: html, md)",
            file=sys.stderr,
        )
        return 2

    build_meta = BuildMeta.now(
        ea_version=args.ea_version,
        kit_version=_kit_version(),
        built_from=str(args.spec),
        compile_status=args.compile_status,
        gate_status=args.gate_status,
    )
    content = build_doc_content(spec, mq5_text, build_meta, lang=args.lang)
    written = _write_outputs(args.out, spec.name, content, formats)

    print(json.dumps({"ok": True, "outputs": written}, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# Make the TakeNote alias available for tests that want to assert types
# without re-importing from ea_docs_render.
TakeNote = TakeNote
