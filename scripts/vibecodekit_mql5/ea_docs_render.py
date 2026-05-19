"""Neo-Retro Dev Deck renderer for EA docs.

Pure-function renderer that turns docstring-style content into a
self-contained ``<EAName>.docs.html`` matching the design system
described in ``ea_docs_assets/style.css``.

Pipeline:

* ``render_html_document(content)`` builds a complete HTML page with CSS
  + pixel-art SVGs inlined — zero external assets, opens in any browser.
* PR-17 then feeds this HTML into headless Chromium via
  ``Page.printToPDF`` to produce the final ``<EAName>.docs.pdf``.
* A parallel Markdown renderer (PR-16) emits ``<EAName>.docs.md`` for
  git diff / agent consumption.

This module is intentionally split into small ``render_*`` component
functions so each can be unit-tested in isolation.

Wire format is stable across PR-15 → PR-18 — only the templates evolve.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Sequence

__all__ = [
    "DocContent",
    "LayerSpec",
    "TimelineStep",
    "ParamRow",
    "TakeNote",
    "load_asset",
    "load_icon",
    "render_frontmatter",
    "render_section_header",
    "render_manifesto",
    "render_layer_stack",
    "render_timeline",
    "render_param_table",
    "render_take_note",
    "render_html_document",
]

ASSETS_DIR = Path(__file__).parent / "ea_docs_assets"
ICONS_DIR = ASSETS_DIR / "icons"
CSS_PATH = ASSETS_DIR / "style.css"

ICON_NAMES = (
    "rocket", "gear", "robot", "code", "browser", "chat", "chevron", "spark",
)


# ────────────────────────────────────────────────────────────────────────────
# Data model — minimal, all pure-Python so callers can build content fixtures
# without touching the kit's full ``EaSpec``.
# ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LayerSpec:
    """One layer in a ``layer-stack`` architecture diagram."""

    title: str
    caption: str
    color: str = "cyan"  # pink | yellow | cyan | black
    icon: str = "gear"   # name from ICON_NAMES


@dataclass(frozen=True)
class TimelineStep:
    """One step in an evolution timeline."""

    label: str
    caption: str = ""
    icon: str = "chevron"
    highlight: bool = False


@dataclass(frozen=True)
class ParamRow:
    """One row of the ``param-table`` (an ``input`` declaration in .mq5)."""

    group: str
    name: str
    type: str
    default: str
    note: str = ""


@dataclass(frozen=True)
class TakeNote:
    """One annotated callout in §5 of the docs."""

    title: str
    body: str
    severity: str = "info"  # info | warn | danger
    icon: str = "spark"


@dataclass
class DocContent:
    """Full document model — what the renderer turns into HTML."""

    title_main: str  # main bold claim (e.g. "PORTFOLIO MEAN-REVERSION")
    title_jp: str = ""  # optional second-line accent (matches reference deck)
    title_en: str = ""  # optional small sub-label
    frontmatter: dict[str, str] = field(default_factory=dict)
    overview_layers: Sequence[LayerSpec] = ()
    strategy_timeline: Sequence[TimelineStep] = ()
    params: Sequence[ParamRow] = ()
    notes: Sequence[TakeNote] = ()
    closing_html: str = ""  # optional free-form HTML at the end


# ────────────────────────────────────────────────────────────────────────────
# Asset loading
# ────────────────────────────────────────────────────────────────────────────


def load_asset(relative_path: str) -> str:
    """Read a packaged asset under ``ea_docs_assets/`` as UTF-8 text."""
    target = (ASSETS_DIR / relative_path).resolve()
    if ASSETS_DIR.resolve() not in target.parents and target != ASSETS_DIR.resolve():
        raise ValueError(f"asset path escapes ea_docs_assets: {relative_path}")
    return target.read_text(encoding="utf-8")


def load_icon(name: str) -> str:
    """Load a pixel-art SVG by short name (e.g. ``rocket``).

    Returns raw ``<svg>...</svg>`` markup ready to inline.
    Unknown names fall back to the ``spark`` icon (never crashes).
    """
    if name not in ICON_NAMES:
        name = "spark"
    return load_asset(f"icons/{name}.svg")


# ────────────────────────────────────────────────────────────────────────────
# Component renderers
# ────────────────────────────────────────────────────────────────────────────


def render_frontmatter(values: dict[str, str]) -> str:
    """Render machine-readable ``key: value`` header block."""
    if not values:
        return ""
    lines = []
    for k, v in values.items():
        lines.append(
            f'<span class="key">{escape(str(k))}:</span> '
            f'<span class="value">{escape(str(v))}</span>'
        )
    body = "\n".join(lines)
    return f'<pre class="frontmatter">{body}</pre>'


def render_section_header(title: str, icon: str = "chevron") -> str:
    """Render a horizontal bar with title + pixel icon."""
    return (
        '<div class="section-header">'
        f'<span class="pixel-icon">{load_icon(icon)}</span>'
        f'<h2 class="h-section">{escape(title)}</h2>'
        '</div>'
    )


def render_manifesto(content: DocContent) -> str:
    """Render the hero / manifesto card (huge claim + decorative icons)."""
    title_jp = (
        f'<p class="title-jp">「{escape(content.title_jp)}」</p>'
        if content.title_jp else ""
    )
    title_en = (
        f'<p class="title-en">{escape(content.title_en)}</p>'
        if content.title_en else ""
    )
    deco_tl = f'<div class="deco tl">{load_icon("code")}</div>'
    deco_tr = f'<div class="deco tr">{load_icon("gear")}</div>'
    deco_br = f'<div class="deco br">{load_icon("rocket")}</div>'
    return (
        '<section class="manifesto">'
        f'{deco_tl}{deco_tr}{deco_br}'
        f'{title_jp}{title_en}'
        f'<h1 class="claim">{escape(content.title_main)}</h1>'
        '</section>'
    )


def render_layer_stack(layers: Sequence[LayerSpec]) -> str:
    """Render stacked architecture layers (one color block per layer)."""
    if not layers:
        return ""
    items = []
    for layer in layers:
        items.append(
            f'<div class="layer block {escape(layer.color)}">'
            f'<span class="pixel-icon lg">{load_icon(layer.icon)}</span>'
            f'<div class="label">'
            f'<h3 class="h-card">{escape(layer.title)}</h3>'
            f'<p class="t-caption">{escape(layer.caption)}</p>'
            f'</div>'
            f'</div>'
        )
    return f'<div class="layer-stack">{"".join(items)}</div>'


def render_timeline(steps: Sequence[TimelineStep]) -> str:
    """Render left → right progression of steps with arrow accents."""
    if not steps:
        return ""
    items: list[str] = []
    for i, step in enumerate(steps):
        cls = "step highlight" if step.highlight else "step"
        items.append(
            f'<div class="{cls}">'
            f'<span class="pixel-icon">{load_icon(step.icon)}</span>'
            f'<h3 class="h-card">{escape(step.label)}</h3>'
            f'<p class="t-caption">{escape(step.caption)}</p>'
            f'</div>'
        )
        if i != len(steps) - 1:
            items.append(f'<span class="arrow">{load_icon("chevron")}</span>')
    return f'<div class="timeline">{"".join(items)}</div>'


def render_param_table(rows: Sequence[ParamRow]) -> str:
    """Render the EA's ``input`` declarations as a styled table."""
    if not rows:
        return ""
    head = (
        '<thead><tr>'
        '<th>Name</th><th>Type</th><th>Default</th><th>Note</th>'
        '</tr></thead>'
    )
    body_rows: list[str] = []
    last_group: str | None = None
    for row in rows:
        if row.group and row.group != last_group:
            body_rows.append(
                f'<tr class="group-row"><td colspan="4">'
                f'{escape(row.group)}'
                '</td></tr>'
            )
            last_group = row.group
        body_rows.append(
            '<tr>'
            f'<td class="name">{escape(row.name)}</td>'
            f'<td class="type">{escape(row.type)}</td>'
            f'<td class="default">{escape(row.default)}</td>'
            f'<td>{escape(row.note)}</td>'
            '</tr>'
        )
    body = "<tbody>" + "".join(body_rows) + "</tbody>"
    return f'<table class="param-table">{head}{body}</table>'


def render_take_note(note: TakeNote) -> str:
    """Render one annotated callout (used in §5 Take notes)."""
    severity = note.severity if note.severity in ("info", "warn", "danger") else "info"
    return (
        f'<div class="take-note {severity}">'
        f'<div class="icon">'
        f'<span class="pixel-icon lg">{load_icon(note.icon)}</span>'
        f'</div>'
        f'<div class="body">'
        f'<h3 class="h-card">{escape(note.title)}</h3>'
        f'<p>{escape(note.body)}</p>'
        f'</div>'
        f'</div>'
    )


def render_html_document(content: DocContent) -> str:
    """Render the full ``<!doctype html>`` page.

    All assets (CSS + SVG icons) are inlined so the output is a single
    self-contained file. Safe to ship via email, mount on a static host,
    or feed to headless Chrome for ``--print-to-pdf``.
    """
    css = load_asset("style.css")
    fm = render_frontmatter(content.frontmatter)
    manifesto = render_manifesto(content)

    sections: list[str] = []
    if content.overview_layers:
        sections.append(render_section_header("System Architecture", "robot"))
        sections.append(render_layer_stack(content.overview_layers))
    if content.strategy_timeline:
        sections.append(render_section_header("Strategy Evolution", "rocket"))
        sections.append(render_timeline(content.strategy_timeline))
    if content.params:
        sections.append(render_section_header("EA Inputs", "code"))
        sections.append(render_param_table(content.params))
    if content.notes:
        sections.append(render_section_header("Take Notes", "spark"))
        for note in content.notes:
            sections.append(render_take_note(note))
    if content.closing_html:
        sections.append(content.closing_html)

    body = (
        '<main>'
        f'{fm}'
        f'{manifesto}'
        f'{"".join(sections)}'
        '</main>'
    )
    head = (
        '<!doctype html>'
        '<html lang="vi">'
        '<head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{escape(content.title_main)}</title>'
        f'<style>{css}</style>'
        '</head>'
    )
    return f'{head}<body>{body}</body></html>'
