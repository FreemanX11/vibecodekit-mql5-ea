"""Docs stage helpers for the ``mql5-auto-build`` pipeline (PR-17).

Extracted from ``auto_build`` to keep that module under the 400-LOC
audit cap. Both helpers are intentionally side-effect-only — they
mutate ``report.docs`` in place and never raise.

* :func:`attach_docs` runs the renderer and writes
  ``<EAName>.docs.html`` / ``.docs.md`` into ``out_dir``. Informational
  stage: any failure is recorded on ``report.docs`` without flipping
  the pipeline verdict.
* :func:`docs_status_lines` pulls compile + gate verdicts out of the
  preceding ``StageResult``s for inclusion in the docs frontmatter.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import ea_docs as ea_docs_mod
from . import spec_schema

if TYPE_CHECKING:
    from .auto_build import PipelineReport, StageResult


__all__ = ["attach_docs", "docs_status_lines"]


def attach_docs(
    report: "PipelineReport",
    out_dir: Path,
    *,
    skip: bool,
    ea_spec: spec_schema.EaSpec | None,
    lang: str,
    formats: tuple[str, ...],
    spec: dict[str, Any],
    mq5_path: Path | None,
) -> None:
    """Render ``<EAName>.docs.html`` + ``<EAName>.docs.md`` and stash on report.

    Never raises; on failure the docs block records the error and the
    overall pipeline outcome is unchanged. Like the dashboard step,
    the docs step is informational — a broken renderer must not turn
    a green build red.

    When ``ea_spec`` is ``None`` (e.g. a caller that bypassed
    ``validate_spec``) or ``mq5_path`` is missing, the stage is
    recorded as ``error`` so the failure is auditable.
    """
    if skip:
        report.docs = {"skipped": True}
        return
    if ea_spec is None:
        report.docs = {"error": "docs render skipped: spec not validated"}
        return
    if mq5_path is None or not mq5_path.is_file():
        report.docs = {"error": "docs render skipped: .mq5 not available"}
        return
    try:
        compile_status, gate_status = docs_status_lines(report.stages)
        build_meta = ea_docs_mod.BuildMeta.now(
            ea_version=str(spec.get("version", "0.1.0")),
            kit_version=ea_docs_mod._kit_version(),
            built_from=str(spec.get("name", "(inline)")),
            compile_status=compile_status,
            gate_status=gate_status,
        )
        mq5_text = mq5_path.read_text(encoding="utf-8", errors="replace")
        content = ea_docs_mod.build_doc_content(
            ea_spec, mq5_text, build_meta, lang=lang,
        )
        written: dict[str, str] = {}
        out_dir.mkdir(parents=True, exist_ok=True)
        if "html" in formats:
            from .ea_docs_render import render_html_document

            html_path = out_dir / f"{ea_spec.name}.docs.html"
            html_path.write_text(
                render_html_document(content), encoding="utf-8",
            )
            written["html"] = str(html_path)
        if "md" in formats:
            md_path = out_dir / f"{ea_spec.name}.docs.md"
            md_path.write_text(
                ea_docs_mod.render_markdown(content), encoding="utf-8",
            )
            written["md"] = str(md_path)
        report.docs = {
            "ok": True,
            "lang": lang,
            "formats": list(formats),
            "outputs": written,
        }
    except (OSError, ValueError) as exc:
        # Same rationale as the dashboard guard — informational stage,
        # never red-list a green build.
        report.docs = {"error": f"docs render failed: {exc}"}


def docs_status_lines(stages: "list[StageResult]") -> tuple[str, str]:
    """Pull compile + gate verdicts out of the report for the docs frontmatter.

    The two stages store their failure shapes differently:

    * ``_stage_compile`` records ``detail['errors']`` as a list of compile
      error strings (plus ``warnings`` + ``ex5_path``). There is no
      ``'error'`` (singular) key.
    * ``_stage_gate`` records ``detail['layers']`` — the permission
      orchestrator's ``OrchestratorReport.layers`` list. The orchestrator
      fail-fasts on the first failing layer, so the last entry in that
      list is the offender; its ``error`` / ``reason`` field (whichever
      exists) is what should land in the frontmatter.

    Both of these were previously read via ``stage.detail.get('error')``
    which always returned ``None``, leaving the frontmatter with a
    generic ``"fail (failed)"`` regardless of what actually went wrong.
    """
    compile_line, gate_line = "", ""
    for stage in stages:
        if stage.name == "compile":
            if stage.skipped:
                compile_line = "skipped"
            else:
                ex5 = stage.detail.get("ex5_path")
                if stage.ok:
                    compile_line = f"ok ({ex5})" if ex5 else "ok"
                else:
                    compile_line = f"fail ({_summarize_compile_errors(stage.detail)})"
        elif stage.name == "gate":
            if stage.skipped:
                gate_line = "skipped"
            elif stage.ok:
                gate_line = "ok"
            else:
                gate_line = f"fail ({_summarize_gate_failure(stage.detail)})"
    return compile_line, gate_line


def _summarize_compile_errors(detail: dict) -> str:
    """Compact ``stage.detail['errors']`` (list[str]) into one line."""
    errs = detail.get("errors") or []
    if not errs:
        return "failed"
    # Keep the docs frontmatter tight — first 2 messages is usually
    # enough to identify the root cause; the rest live in the build log.
    joined = "; ".join(str(e).strip() for e in errs[:2] if str(e).strip())
    if len(errs) > 2:
        joined = f"{joined}; +{len(errs) - 2} more"
    return joined or "failed"


def _summarize_gate_failure(detail: dict) -> str:
    """Find the offending layer in ``stage.detail['layers']``.

    Layers carry either an ``error`` or a ``reason`` field on failure
    (per the permission orchestrator). Return ``"Layer-{N}: {msg}"``
    so the docs frontmatter mirrors what users see in the dashboard.
    """
    layers = detail.get("layers") or []
    failed = [layer for layer in layers if not layer.get("ok", False)]
    if not failed:
        return "failed"
    bad = failed[-1]  # orchestrator fail-fasts, so the last failed layer is the cause
    layer_id = bad.get("layer", "?")
    msg = bad.get("error") or bad.get("reason") or "failed"
    return f"Layer-{layer_id}: {msg}"
