"""Phase E — gate suite for the docs stage of ``mql5-auto-build`` (PR-17).

The docs stage is informational: it runs after dashboard, never turns a
green build red, and is fully skippable via ``--no-docs``. These tests
pin:

* the stage runs by default and writes both ``<EA>.docs.html`` and
  ``<EA>.docs.md``,
* ``--no-docs`` cleanly skips it (``report.docs.skipped == True``),
* ``--docs-lang en|vi`` switches language without touching anything else,
* ``--docs-formats html``/``md`` lets the caller pick exactly one,
* the docs frontmatter pulls real compile + gate verdicts from the
  preceding stages,
* a build failure never crashes the docs guard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibecodekit_mql5 import auto_build
from vibecodekit_mql5 import compile as compile_mod


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


MINIMAL_SPEC: dict = {
    "name": "AutoBuildDocsEA",
    "preset": "stdlib",
    "stack": "netting",
    "symbol": "EURUSD",
    "timeframe": "H1",
    "mode": "personal",
}


def _write_yaml_spec(tmp_path: Path, spec: dict | None = None) -> Path:
    import yaml

    payload = dict(spec or MINIMAL_SPEC)
    target = tmp_path / "spec.yaml"
    target.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return target


def _patch_compile_success(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_compile(_path, **_kwargs):
        return compile_mod.CompileResult(
            success=True,
            errors=[],
            warnings=[],
            ex5_path=str(_path.with_suffix(".ex5")),
        )

    monkeypatch.setattr(compile_mod, "compile_mq5", _fake_compile)


# ─────────────────────────────────────────────────────────────────────────────
# run_pipeline — docs stage default ON
# ─────────────────────────────────────────────────────────────────────────────


def test_pipeline_writes_docs_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_compile_success(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_gate=True,  # gate needs orch fixtures — skip to keep the test light
        ea_spec=auto_build.validate_spec(dict(MINIMAL_SPEC)),
    )
    assert report.ok
    assert report.docs is not None
    assert report.docs.get("ok") is True
    assert report.docs.get("lang") == "vi"
    assert (out / f"{MINIMAL_SPEC['name']}.docs.html").is_file()
    assert (out / f"{MINIMAL_SPEC['name']}.docs.md").is_file()


def test_pipeline_no_docs_flag_skips_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_compile_success(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_gate=True,
        skip_docs=True,
        ea_spec=auto_build.validate_spec(dict(MINIMAL_SPEC)),
    )
    assert report.ok
    assert report.docs == {"skipped": True}
    assert not (out / f"{MINIMAL_SPEC['name']}.docs.html").exists()
    assert not (out / f"{MINIMAL_SPEC['name']}.docs.md").exists()


def test_pipeline_respects_docs_lang_en(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_compile_success(monkeypatch)
    out = tmp_path / "build"
    auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_gate=True,
        ea_spec=auto_build.validate_spec(dict(MINIMAL_SPEC)),
        docs_lang="en",
    )
    md = (out / f"{MINIMAL_SPEC['name']}.docs.md").read_text(encoding="utf-8")
    # English captions live in ea_docs._TIMELINE_CAPTIONS — pick one that
    # only appears on the English side.
    assert "Read spec" in md


def test_pipeline_respects_docs_formats_md_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_compile_success(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_gate=True,
        ea_spec=auto_build.validate_spec(dict(MINIMAL_SPEC)),
        docs_formats=("md",),
    )
    assert report.docs is not None
    assert list(report.docs.get("outputs", {}).keys()) == ["md"]
    assert (out / f"{MINIMAL_SPEC['name']}.docs.md").is_file()
    assert not (out / f"{MINIMAL_SPEC['name']}.docs.html").exists()


def test_pipeline_docs_frontmatter_carries_compile_and_gate_verdicts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The docs frontmatter should mirror what the preceding stages
    actually produced — not hard-coded fixture values."""
    _patch_compile_success(monkeypatch)
    out = tmp_path / "build"
    auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_gate=True,  # this should surface as gate: skipped in frontmatter
        ea_spec=auto_build.validate_spec(dict(MINIMAL_SPEC)),
    )
    md_text = (out / f"{MINIMAL_SPEC['name']}.docs.md").read_text(encoding="utf-8")
    assert "compile: ok" in md_text
    assert "gate: skipped" in md_text


def test_pipeline_docs_records_error_when_build_fails(
    tmp_path: Path,
) -> None:
    """A build-stage failure (e.g. bad scaffold) must not crash the
    docs guard; it should record an error block and leave the
    pipeline result unchanged."""
    bad_spec = dict(MINIMAL_SPEC)
    bad_spec["stack"] = "invalid-stack-that-does-not-exist"
    out = tmp_path / "build"
    # validate_spec will raise on this before run_pipeline gets it;
    # we bypass to exercise the build-stage failure code path directly.
    report = auto_build.run_pipeline(
        bad_spec,
        out,
        skip_compile=True,
        skip_gate=True,
        ea_spec=None,  # forces the "spec not validated" guard
    )
    assert report.ok is False
    assert report.docs is not None
    # Guard must record a reason, not crash.
    assert "error" in report.docs


# ─────────────────────────────────────────────────────────────────────────────
# CLI flags
# ─────────────────────────────────────────────────────────────────────────────


def test_cli_no_docs_flag_skips_stage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _patch_compile_success(monkeypatch)
    spec_path = _write_yaml_spec(tmp_path)
    out = tmp_path / "build"
    rc = auto_build.main([
        "--spec", str(spec_path),
        "--out-dir", str(out),
        "--no-gate",
        "--no-docs",
    ])
    assert rc == 0
    captured = capsys.readouterr().out
    payload = json.loads(captured.split("\n\n")[0]) if "\n\n" in captured else None
    # main() prints the report JSON to stdout; just confirm it serializes.
    assert payload is None or payload["docs"] == {"skipped": True}
    assert not (out / f"{MINIMAL_SPEC['name']}.docs.html").exists()
    assert not (out / f"{MINIMAL_SPEC['name']}.docs.md").exists()


def test_cli_docs_lang_en_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _patch_compile_success(monkeypatch)
    spec_path = _write_yaml_spec(tmp_path)
    out = tmp_path / "build"
    rc = auto_build.main([
        "--spec", str(spec_path),
        "--out-dir", str(out),
        "--no-gate",
        "--docs-lang", "en",
    ])
    assert rc == 0
    md = (out / f"{MINIMAL_SPEC['name']}.docs.md").read_text(encoding="utf-8")
    assert "Read spec" in md


def test_cli_docs_formats_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_compile_success(monkeypatch)
    spec_path = _write_yaml_spec(tmp_path)
    out = tmp_path / "build"
    rc = auto_build.main([
        "--spec", str(spec_path),
        "--out-dir", str(out),
        "--no-gate",
        "--docs-formats", "md",
    ])
    assert rc == 0
    assert (out / f"{MINIMAL_SPEC['name']}.docs.md").is_file()
    assert not (out / f"{MINIMAL_SPEC['name']}.docs.html").exists()


def test_cli_rejects_invalid_docs_format(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    spec_path = _write_yaml_spec(tmp_path)
    rc = auto_build.main([
        "--spec", str(spec_path),
        "--out-dir", str(tmp_path / "build"),
        "--no-gate", "--no-docs",
        "--docs-formats", "pdf,docx",  # neither supported by PR-17
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "docs-formats" in err
    assert "pdf" in err or "docx" in err


def test_cli_rejects_invalid_docs_lang(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    spec_path = _write_yaml_spec(tmp_path)
    # argparse rejects bad choices with SystemExit(2) before main() returns.
    with pytest.raises(SystemExit) as exc:
        auto_build.main([
            "--spec", str(spec_path),
            "--out-dir", str(tmp_path / "build"),
            "--docs-lang", "klingon",
        ])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "docs-lang" in err
    assert "klingon" in err


# ─────────────────────────────────────────────────────────────────────────────
# Report serialization
# ─────────────────────────────────────────────────────────────────────────────


def test_report_to_dict_includes_docs_field() -> None:
    """``report.json`` must always carry a ``docs`` field (possibly None)
    so downstream consumers can rely on the schema."""
    report = auto_build.PipelineReport(spec={}, out_dir=".")
    payload = report.to_dict()
    assert "docs" in payload
    assert payload["docs"] is None


# ─────────────────────────────────────────────────────────────────────────────
# docs_status_lines — PR-17.1 regression tests
# ─────────────────────────────────────────────────────────────────────────────


def test_docs_status_lines_summarizes_real_compile_errors() -> None:
    """Pin the regression fixed in PR-17.1: compile-stage failure detail
    is ``{'errors': [...], 'warnings': [...], 'ex5_path': ''}`` — the
    earlier code looked up the wrong key (``'error'``, singular) and
    always wrote ``"fail (failed)"`` no matter what MetaEditor said."""
    from vibecodekit_mql5 import auto_build_docs_stage as docs_stage

    stages = [
        auto_build.StageResult(
            name="compile",
            ok=False,
            detail={
                "errors": ["foo.mq5(12,3): undeclared identifier 'Bar'"],
                "warnings": [],
                "ex5_path": "",
            },
        ),
    ]
    compile_line, _ = docs_stage.docs_status_lines(stages)
    assert "undeclared identifier" in compile_line
    assert "failed" not in compile_line  # generic fallback must NOT appear


def test_docs_status_lines_truncates_long_compile_error_lists() -> None:
    """3+ compile errors should collapse to ``"first; second; +N more"``
    so the docs frontmatter stays one line."""
    from vibecodekit_mql5 import auto_build_docs_stage as docs_stage

    stages = [
        auto_build.StageResult(
            name="compile",
            ok=False,
            detail={"errors": ["err A", "err B", "err C", "err D"]},
        ),
    ]
    compile_line, _ = docs_stage.docs_status_lines(stages)
    assert "err A" in compile_line
    assert "err B" in compile_line
    assert "+2 more" in compile_line


def test_docs_status_lines_summarizes_real_gate_failure() -> None:
    """Pin the regression fixed in PR-17.1: gate-stage detail is
    ``{'mode': ..., 'layers': [...]}`` — no ``'error'`` key. The fix
    walks ``layers`` and returns the offender's id + error/reason."""
    from vibecodekit_mql5 import auto_build_docs_stage as docs_stage

    stages = [
        auto_build.StageResult(
            name="gate",
            ok=False,
            detail={
                "mode": "enterprise",
                "layers": [
                    {"layer": 1, "ok": True},
                    {"layer": 2, "ok": True},
                    {"layer": 4, "ok": False,
                     "error": "Trader-17: 6/17 checks passed"},
                ],
            },
        ),
    ]
    _, gate_line = docs_stage.docs_status_lines(stages)
    assert "Layer-4" in gate_line
    assert "Trader-17" in gate_line


def test_docs_status_lines_handles_gate_with_reason_field() -> None:
    """Some layers (e.g. layer-6 quality-matrix with no --matrix arg)
    skip via a ``reason`` field instead of ``error`` — handle both."""
    from vibecodekit_mql5 import auto_build_docs_stage as docs_stage

    stages = [
        auto_build.StageResult(
            name="gate",
            ok=False,
            detail={
                "mode": "enterprise",
                "layers": [
                    {"layer": 6, "ok": False,
                     "reason": "no --matrix provided"},
                ],
            },
        ),
    ]
    _, gate_line = docs_stage.docs_status_lines(stages)
    assert "Layer-6" in gate_line
    assert "no --matrix provided" in gate_line


def test_docs_status_lines_compile_skipped_and_gate_skipped() -> None:
    """The healthy 'no errors' path remains green."""
    from vibecodekit_mql5 import auto_build_docs_stage as docs_stage

    stages = [
        auto_build.StageResult(name="compile", ok=True, skipped=True),
        auto_build.StageResult(name="gate", ok=True, skipped=True),
    ]
    assert docs_stage.docs_status_lines(stages) == ("skipped", "skipped")
