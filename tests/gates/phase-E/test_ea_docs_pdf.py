"""Tests for PR-18 PDF export and dashboard docs-embed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import scripts.vibecodekit_mql5.ea_docs_pdf as ea_docs_pdf
from scripts.vibecodekit_mql5 import auto_build, dashboard


# ─────────────────────────────────────────────────────────────────────────────
# find_chrome_binary discovery rules
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_chrome_cache() -> None:
    """Discovery is cached per-process — clear between tests so each
    case starts from a clean slate."""
    ea_docs_pdf._cache = (None, False)


def test_find_chrome_honours_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / "fake-chrome"
    fake.write_text("not actually a binary, but is_file() returns True")
    monkeypatch.setenv(ea_docs_pdf.ENV_CHROME_PATH, str(fake))
    # Defeat any real binary on the host:
    monkeypatch.setattr(ea_docs_pdf, "_DEVIN_CHROME_GLOBS", ())
    monkeypatch.setattr(ea_docs_pdf, "_PATH_CANDIDATES", ())
    assert ea_docs_pdf.find_chrome_binary() == str(fake)


def test_find_chrome_skips_devin_browser_shim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Devin VM ships a ``google-chrome`` shim that forwards URLs
    to the live Chrome via CDP — it is NOT a real headless-capable
    binary. ``find_chrome_binary`` must skip it even if ``shutil.which``
    returns it."""
    shim = tmp_path / "google-chrome"
    shim.write_text(
        '#!/bin/sh\n'
        'url=$(echo "$1" | /usr/bin/jq -rR @uri)\n'
        'curl -XPUT -fsSo /dev/null "http://localhost:29229/json/new?$url"\n'
    )
    monkeypatch.delenv(ea_docs_pdf.ENV_CHROME_PATH, raising=False)
    monkeypatch.setattr(ea_docs_pdf, "_DEVIN_CHROME_GLOBS", ())
    monkeypatch.setattr(ea_docs_pdf, "_PATH_CANDIDATES", ("google-chrome",))
    monkeypatch.setattr(ea_docs_pdf.shutil, "which", lambda _: str(shim))
    assert ea_docs_pdf.find_chrome_binary() is None


def test_find_chrome_returns_none_when_no_binary_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ea_docs_pdf.ENV_CHROME_PATH, raising=False)
    monkeypatch.setattr(ea_docs_pdf, "_DEVIN_CHROME_GLOBS", ())
    monkeypatch.setattr(ea_docs_pdf, "_PATH_CANDIDATES", ())
    assert ea_docs_pdf.find_chrome_binary() is None


# ─────────────────────────────────────────────────────────────────────────────
# render_pdf semantics
# ─────────────────────────────────────────────────────────────────────────────


def test_render_pdf_returns_false_when_no_chrome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ea_docs_pdf, "find_chrome_binary", lambda: None)
    html = tmp_path / "src.html"
    html.write_text("<html><body>hi</body></html>", encoding="utf-8")
    pdf = tmp_path / "out.pdf"
    assert ea_docs_pdf.render_pdf(html, pdf) is False
    assert not pdf.exists()


def test_render_pdf_returns_false_when_html_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ea_docs_pdf, "find_chrome_binary",
                        lambda: "/usr/bin/echo")
    pdf = tmp_path / "out.pdf"
    missing = tmp_path / "nope.html"
    assert ea_docs_pdf.render_pdf(missing, pdf) is False


def test_render_pdf_returns_false_on_chrome_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate Chrome dying mid-render — ``render_pdf`` must NOT
    raise; it must return False so the docs stage stays informational."""
    import subprocess

    monkeypatch.setattr(ea_docs_pdf, "find_chrome_binary",
                        lambda: "/usr/bin/false")

    class _FakeProc:
        returncode = 1
        stdout = b""
        stderr = b"boom"

    def _fake_run(*args: Any, **kwargs: Any) -> _FakeProc:
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    html = tmp_path / "src.html"
    html.write_text("<html/>", encoding="utf-8")
    pdf = tmp_path / "out.pdf"
    assert ea_docs_pdf.render_pdf(html, pdf) is False


def test_render_pdf_returns_false_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    monkeypatch.setattr(ea_docs_pdf, "find_chrome_binary",
                        lambda: "/usr/bin/sleep")

    def _raise_timeout(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    html = tmp_path / "src.html"
    html.write_text("<html/>", encoding="utf-8")
    pdf = tmp_path / "out.pdf"
    assert ea_docs_pdf.render_pdf(html, pdf) is False


def test_render_pdf_returns_true_when_chrome_writes_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import subprocess

    monkeypatch.setattr(ea_docs_pdf, "find_chrome_binary",
                        lambda: "/usr/bin/true")

    class _FakeProc:
        returncode = 0
        stdout = b""
        stderr = b""

    def _fake_run(cmd: list[str], **kwargs: Any) -> _FakeProc:
        # Pretend Chrome wrote the PDF by writing it ourselves.
        out_arg = next(c for c in cmd if c.startswith("--print-to-pdf="))
        Path(out_arg.split("=", 1)[1]).write_bytes(b"%PDF-1.4 fake")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    html = tmp_path / "src.html"
    html.write_text("<html/>", encoding="utf-8")
    pdf = tmp_path / "out.pdf"
    assert ea_docs_pdf.render_pdf(html, pdf) is True
    assert pdf.is_file() and pdf.stat().st_size > 0


# ─────────────────────────────────────────────────────────────────────────────
# attach_docs(formats=("pdf",)) wiring
# ─────────────────────────────────────────────────────────────────────────────


# Use the same minimal-but-valid spec as test_auto_build_docs_stage.py
# so we don't need to mock compile/build internals here.
_MINIMAL_SPEC: dict[str, Any] = {
    "name": "PdfTestEA",
    "preset": "stdlib",
    "stack": "netting",
    "symbol": "EURUSD",
    "timeframe": "H1",
    "mode": "personal",
}


def _patch_pdf_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the headless-Chrome call so the test doesn't depend on
    the host having a real Chrome installed."""
    from scripts.vibecodekit_mql5 import auto_build_docs_stage

    def _fake_render(html_path: Path, pdf_path: Path) -> bool:
        pdf_path.write_bytes(b"%PDF-1.4 stub")
        return True

    monkeypatch.setattr(
        auto_build_docs_stage.ea_docs_pdf_mod,
        "render_pdf",
        _fake_render,
    )


def test_pipeline_writes_pdf_when_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_pdf_success(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(_MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
        ea_spec=auto_build.validate_spec(dict(_MINIMAL_SPEC)),
        docs_formats=("html", "md", "pdf"),
    )
    assert report.docs is not None and report.docs.get("ok") is True
    outputs = report.docs["outputs"]
    assert "pdf" in outputs
    pdf_path = Path(outputs["pdf"])
    assert pdf_path.is_file() and pdf_path.read_bytes().startswith(b"%PDF")


def test_pipeline_records_pdf_error_when_chrome_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``--docs-formats pdf`` is requested but no Chrome binary
    is found, the build must still succeed and the docs block must
    surface ``pdf_error`` describing the override env-var."""
    from scripts.vibecodekit_mql5 import auto_build_docs_stage

    monkeypatch.setattr(
        auto_build_docs_stage.ea_docs_pdf_mod, "render_pdf",
        lambda *a, **k: False,
    )
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(_MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
        ea_spec=auto_build.validate_spec(dict(_MINIMAL_SPEC)),
        docs_formats=("html", "md", "pdf"),
    )
    assert report.ok  # pdf failure must NEVER red-list the build
    assert report.docs and report.docs.get("ok") is True
    assert "pdf" not in report.docs["outputs"]
    assert "pdf_error" in report.docs
    assert "MQL5_CHROME_PATH" in report.docs["pdf_error"]


def test_pipeline_pdf_only_keeps_pdf_drops_temp_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--docs-formats pdf`` (no html, no md) should produce just
    the PDF; the staging HTML used for Chrome must be removed."""
    _patch_pdf_success(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(_MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
        ea_spec=auto_build.validate_spec(dict(_MINIMAL_SPEC)),
        docs_formats=("pdf",),
    )
    assert report.docs and report.docs["outputs"].keys() == {"pdf"}
    assert (out / f"{_MINIMAL_SPEC['name']}.docs.pdf").is_file()
    assert not (out / f"{_MINIMAL_SPEC['name']}.docs.html").exists()
    assert not (out / f"{_MINIMAL_SPEC['name']}.docs.md").exists()


def test_cli_rejects_unknown_format_keeps_pdf_allowed() -> None:
    """CLI validation: pdf is now a valid format, but unknown ones
    still exit 2."""
    rc = auto_build.main([
        "--spec", "/nonexistent.yaml",
        "--out-dir", "/tmp/none",
        "--docs-formats", "html,docx",
    ])
    assert rc == 2


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard docs-embed
# ─────────────────────────────────────────────────────────────────────────────


def test_dashboard_renders_docs_card_with_all_three_links() -> None:
    digest = dashboard.PipelineDigest(
        name="MyEA",
        ok=True,
        stages=[],
        docs_links={
            "html": "MyEA.docs.html",
            "md": "MyEA.docs.md",
            "pdf": "MyEA.docs.pdf",
        },
    )
    html = dashboard.render_from_pipeline(digest)
    assert 'class="ea-docs-embed"' in html
    assert "MyEA — EA Docs" in html
    assert 'href="MyEA.docs.html"' in html
    assert 'href="MyEA.docs.pdf"' in html
    assert 'href="MyEA.docs.md"' in html


def test_dashboard_omits_docs_card_when_no_links() -> None:
    digest = dashboard.PipelineDigest(name="MyEA", ok=True, stages=[])
    html = dashboard.render_from_pipeline(digest)
    assert "ea-docs-embed" not in html
    # Existing matrix HTML still present:
    assert "mql5 quality matrix" in html


def test_dashboard_escapes_ea_name_in_card() -> None:
    """Pin XSS guard: ea_name is user-controlled (via spec.name)."""
    digest = dashboard.PipelineDigest(
        name="<script>alert(1)</script>",
        ok=True,
        stages=[],
        docs_links={"html": "x.docs.html"},
    )
    html = dashboard.render_from_pipeline(digest)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_dashboard_renders_partial_links() -> None:
    """If only PDF was rendered (no html/md), card still appears."""
    digest = dashboard.PipelineDigest(
        name="MyEA",
        ok=True,
        stages=[],
        docs_links={"pdf": "MyEA.docs.pdf"},
    )
    html = dashboard.render_from_pipeline(digest)
    assert 'class="ea-docs-embed"' in html
    assert 'href="MyEA.docs.pdf"' in html
    assert 'href="MyEA.docs.html"' not in html


def test_pipeline_dashboard_picks_up_docs_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: dashboard HTML on disk contains an embed card
    pointing to the docs files that the docs stage will write next."""
    out = tmp_path / "build"
    auto_build.run_pipeline(
        dict(_MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
        ea_spec=auto_build.validate_spec(dict(_MINIMAL_SPEC)),
    )
    dash_html = (out / "quality-matrix.html").read_text(encoding="utf-8")
    assert "ea-docs-embed" in dash_html
    assert f'href="{_MINIMAL_SPEC["name"]}.docs.html"' in dash_html
    assert f'href="{_MINIMAL_SPEC["name"]}.docs.md"' in dash_html


def test_pipeline_dashboard_omits_embed_when_docs_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--no-docs`` should propagate to the dashboard so the embed
    card disappears — promising a link to a file that won't exist
    would be misleading."""
    out = tmp_path / "build"
    auto_build.run_pipeline(
        dict(_MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
        skip_docs=True,
        ea_spec=auto_build.validate_spec(dict(_MINIMAL_SPEC)),
    )
    dash_html = (out / "quality-matrix.html").read_text(encoding="utf-8")
    assert "ea-docs-embed" not in dash_html
