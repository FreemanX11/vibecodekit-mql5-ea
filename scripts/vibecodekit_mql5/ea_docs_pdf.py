"""Headless-Chrome PDF export for ``<EAName>.docs.html`` (PR-18).

Intentionally a thin wrapper: the renderer in :mod:`ea_docs_render`
already produces a self-contained, printable HTML document (every
asset inlined, ``@page`` rules baked in, no network dependencies).
This module just feeds that HTML to whichever Chromium-class binary
the host happens to have and captures the resulting PDF.

Design rules
------------

1. **Never raise.** Callers (``auto_build_docs_stage.attach_docs``)
   treat the docs stage as informational and rely on a clean
   ``True / False`` return so a missing Chrome binary cannot red-list
   an otherwise green build.

2. **No new runtime dependencies.** Pure ``subprocess`` + ``shutil``;
   we don't pull in Playwright, ``pyppeteer``, or ``selenium``. Devin
   sessions ship Chrome for Testing already; teams without it can
   still call the full kit with ``--docs-formats html,md``.

3. **Deterministic discovery.** The lookup order is:

   1. ``MQL5_CHROME_PATH`` environment variable (explicit override).
   2. The Devin sandbox's Chrome for Testing
      (``/opt/.devin/chrome/chrome/linux-*/chrome-linux64/chrome``).
   3. Playwright's bundled Chromium
      (``/opt/.devin/playwright_browsers/chromium-*/chrome-linux/chrome``).
   4. ``shutil.which`` for ``chromium``, ``chromium-browser``,
      ``chrome``, ``google-chrome-stable``.
   5. **Skipped on purpose:** ``shutil.which("google-chrome")`` —
      on Devin VMs this resolves to ``/opt/.devin/browser.sh``, a
      thin shim that only forwards URLs to the running Chrome via
      CDP. It is not a real ``--headless`` capable binary.

   The first hit that actually exists wins. Discovery is cached for
   the process lifetime to avoid repeated globbing during pipeline
   smoke tests.

4. **Bounded subprocess.** 60s timeout; on timeout / non-zero exit /
   missing output file we return ``False`` and the caller stamps an
   ``error`` entry on ``report.docs`` — same convention as every
   other informational helper in this package.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from glob import glob
from pathlib import Path

__all__ = ["render_pdf", "find_chrome_binary"]


ENV_CHROME_PATH: str = "MQL5_CHROME_PATH"
"""Explicit override read by :func:`find_chrome_binary`. Set this in a
Devin blueprint when you want to pin a specific Chrome build (e.g. to
match the version your CI runners ship)."""

PDF_TIMEOUT_SECONDS: int = 60
"""Hard cap on the headless render subprocess. The whole ``.docs.html``
fits in ~50 KB and inlines every asset, so any render that legitimately
takes longer than 60s is a configuration error (e.g. Chrome stuck
trying to phone home through a dead proxy)."""

_DEVIN_CHROME_GLOBS: tuple[str, ...] = (
    "/opt/.devin/chrome/chrome/linux-*/chrome-linux64/chrome",
    "/opt/.devin/playwright_browsers/chromium-*/chrome-linux/chrome",
)

_PATH_CANDIDATES: tuple[str, ...] = (
    "chromium",
    "chromium-browser",
    "chrome",
    "google-chrome-stable",
    # NB: ``google-chrome`` is intentionally NOT here — see module
    # docstring for why.
)

_cache: tuple[str | None, bool] = (None, False)
"""``(path, hit)`` cache. ``hit=False`` means we've already searched
and found nothing, so subsequent calls short-circuit."""


def find_chrome_binary() -> str | None:
    """Locate a usable headless-Chrome binary or return ``None``.

    See module docstring for the discovery order. Cached per-process.
    """
    global _cache
    cached_path, cached_hit = _cache
    if cached_hit:
        return cached_path

    env_override = os.environ.get(ENV_CHROME_PATH)
    if env_override and Path(env_override).is_file():
        _cache = (env_override, True)
        return env_override

    for pattern in _DEVIN_CHROME_GLOBS:
        for match in sorted(glob(pattern), reverse=True):  # prefer newest
            if Path(match).is_file():
                _cache = (match, True)
                return match

    for name in _PATH_CANDIDATES:
        found = shutil.which(name)
        if found and Path(found).is_file():
            # Defensive: skip Devin's URL-forwarding shim if someone has
            # symlinked ``chromium`` to it.
            try:
                head = Path(found).read_text(encoding="utf-8", errors="replace")[:200]
            except OSError:
                head = ""
            if "/opt/.devin/browser.sh" in head or "json/new?" in head:
                continue
            _cache = (found, True)
            return found

    _cache = (None, True)
    return None


def render_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Render ``html_path`` to ``pdf_path`` via headless Chrome.

    Returns ``True`` on success (``pdf_path`` written, non-empty),
    ``False`` otherwise. **Never raises.**

    Callers should treat the return value as advisory — the docs stage
    is informational, so a failed PDF must not change the pipeline
    verdict.
    """
    chrome = find_chrome_binary()
    if not chrome:
        return False
    if not html_path.is_file():
        return False
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    # Resolve to file:// URI so Chrome reads the local document
    # regardless of CWD. The renderer in PR-15 inlined all assets so
    # we never need ``--allow-file-access-from-files``.
    try:
        uri = html_path.resolve().as_uri()
    except ValueError:
        return False
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        # Pinning the page size lets the renderer's ``@page`` rule
        # produce identical output across Chrome versions; otherwise
        # Chrome falls back to the locale-default which differs
        # between Linux distros.
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        uri,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=PDF_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if proc.returncode != 0:
        return False
    return pdf_path.is_file() and pdf_path.stat().st_size > 0
