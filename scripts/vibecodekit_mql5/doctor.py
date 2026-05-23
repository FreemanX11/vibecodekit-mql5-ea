"""/mql5-doctor — kit installation + environment health check.

Phase E command.  Validates that everything the kit needs is reachable
on the current machine: Python toolchain, Wine when running MetaEditor
through Wine, ``MetaEditor.exe`` itself, the kit's package
importability, the presence of the 28+ reference docs, and that **every
scaffold archetype** under ``scaffolds/<preset>/<stack>/`` ships its
``EAName.mq5`` (auto-derived at run time so new archetypes are picked
up without code edits).

Exit code 0 = healthy.  Non-zero = at least one check failed.  The
JSON output enumerates every check so a CI workflow can decide which
to treat as fatal.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_MODULES = [
    "vibecodekit_mql5.compile",
    "vibecodekit_mql5.lint",
    "vibecodekit_mql5.build",
    "vibecodekit_mql5.pip_normalize",
]

# Checks that depend on a working Wine + MetaEditor + terminal stack.
# In soft mode (``--soft``) these are surfaced as warnings instead of
# failures so docs-only / lint-only CI environments without Wine can still
# exit 0. Python toolchain, kit-package imports, references, and scaffolds
# remain hard checks under both modes.
_OPTIONAL_CHECKS: frozenset[str] = frozenset({
    "wine", "metaeditor-bin", "terminal-bin",
})

# Standard MetaTrader 5 binary locations Devin's setup-wine-metaeditor.sh leaves
# behind. Doctor uses these as a fallback when the corresponding env var is not
# set, so a fresh shell that hasn't sourced ~/.mql5-env still gets a green check.
_METAEDITOR_PROBES: tuple[str, ...] = (
    "$METAEDITOR_PATH",
    "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe",
    "$HOME/.wine-mql5/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe",
    "$HOME/.wine/drive_c/Program Files/MetaTrader 5/MetaEditor64.exe",
)
_TERMINAL_PROBES: tuple[str, ...] = (
    "$MQL5_TERMINAL_PATH",
    "$WINEPREFIX/drive_c/Program Files/MetaTrader 5/terminal64.exe",
    "$HOME/.wine-mql5/drive_c/Program Files/MetaTrader 5/terminal64.exe",
    "$HOME/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe",
)


def _probe(paths: tuple[str, ...]) -> Path | None:
    """Return the first existing path after expanding env vars / ``~``.

    Empty / unset env vars (e.g. ``$METAEDITOR_PATH`` when never exported) are
    skipped so they don't show up in the report as a bogus failure detail.
    """
    for raw in paths:
        expanded = os.path.expandvars(os.path.expanduser(raw))
        if expanded == raw and raw.startswith("$"):
            continue  # env var unset
        p = Path(expanded)
        if p.is_file():
            return p
    return None

# Baseline list of scaffolds that MUST exist for the kit to be coherent.
# These are the original 11 archetypes shipped before Phase 2A. They stay
# explicit here so removals of any of them is caught even if the
# ``scaffolds/`` directory listing accidentally regresses.
_BASELINE_SCAFFOLDS: tuple[str, ...] = (
    "stdlib/netting", "stdlib/hedging", "stdlib/python-bridge",
    "wizard-composable/netting", "portfolio-basket/netting",
    "portfolio-basket/hedging", "ml-onnx/python-bridge",
    "hft-async/netting",
    "service-llm-bridge/cloud-api",
    "service-llm-bridge/self-hosted-ollama",
    "service-llm-bridge/embedded-onnx-llm",
)


def discover_scaffolds(repo_root: Path = REPO_ROOT) -> list[str]:
    """Return every ``<preset>/<stack>`` pair under ``scaffolds/``.

    Auto-derived from the filesystem so new archetypes are validated by
    doctor without requiring a code edit here. The baseline 11 from
    ``_BASELINE_SCAFFOLDS`` are union-merged in case the directory walk
    misses something (e.g. broken symlinks). The result is sorted for
    deterministic output.
    """
    found: set[str] = set(_BASELINE_SCAFFOLDS)
    scaffolds_root = repo_root / "scaffolds"
    if scaffolds_root.is_dir():
        for preset_dir in scaffolds_root.iterdir():
            if not preset_dir.is_dir():
                continue
            for stack_dir in preset_dir.iterdir():
                if not stack_dir.is_dir():
                    continue
                found.add(f"{preset_dir.name}/{stack_dir.name}")
    return sorted(found)


# Backwards-compat module-level constant. Older callers (tests, MCP) may
# still ``import REQUIRED_SCAFFOLDS``; keep it pointing at the discovered
# list so they automatically pick up newly added archetypes too.
REQUIRED_SCAFFOLDS: list[str] = discover_scaffolds()


@dataclass
class DoctorReport:
    checks: list[dict] = field(default_factory=list)
    ok: bool = True

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            self.ok = False

    def is_ok(self, *, soft: bool = False) -> bool:
        """Aggregate health across checks.

        In soft mode the Wine / MetaEditor / terminal checks no longer
        flip the report. Every other check still does. This lets
        docs-only or lint-only CI jobs that don't ship Wine pass the
        doctor gate without ignoring failures elsewhere.
        """
        if not soft:
            return self.ok
        for c in self.checks:
            if c["ok"]:
                continue
            if c["name"] not in _OPTIONAL_CHECKS:
                return False
        return True


def run_doctor(repo_root: Path = REPO_ROOT) -> DoctorReport:
    rep = DoctorReport()
    rep.add("python-version", sys.version_info >= (3, 10),
            f"{sys.version_info.major}.{sys.version_info.minor}")

    metaeditor = _probe(_METAEDITOR_PROBES)
    needs_wine = not sys.platform.startswith("win") or (
        metaeditor is not None
        and ".wine" in metaeditor.as_posix().lower()
    )
    wine = shutil.which("wine")
    rep.add(
        "wine",
        wine is not None if needs_wine else True,
        str(wine) if wine else ("not required on Windows native" if not needs_wine else "PATH"),
    )
    rep.add(
        "metaeditor-bin",
        metaeditor is not None,
        str(metaeditor) if metaeditor else "not found in any of: "
        + ", ".join(_METAEDITOR_PROBES),
    )
    terminal = _probe(_TERMINAL_PROBES)
    rep.add(
        "terminal-bin",
        terminal is not None,
        str(terminal) if terminal else "not found in any of: "
        + ", ".join(_TERMINAL_PROBES),
    )
    for mod in REQUIRED_MODULES:
        try:
            importlib.import_module(mod)
            rep.add(f"import:{mod}", True)
        except ImportError as exc:
            rep.add(f"import:{mod}", False, str(exc))
    refs_dir = repo_root / "docs" / "references"
    rep.add("references-dir", refs_dir.exists(), str(refs_dir))
    if refs_dir.exists():
        n = len(list(refs_dir.glob("*.md")))
        rep.add("references-count", n >= 28, f"{n} refs")
    for scaffold in discover_scaffolds(repo_root):
        p = repo_root / "scaffolds" / scaffold / "EAName.mq5"
        rep.add(f"scaffold:{scaffold}", p.exists(), str(p))
    return rep


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mql5-doctor")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument(
        "--soft",
        action="store_true",
        help=(
            "Treat Wine / MetaEditor / terminal probes as warnings instead "
            "of failures. Exit 0 when only those optional checks fail. "
            "Useful for docs-only or lint-only CI environments."
        ),
    )
    args = parser.parse_args(argv)
    rep = run_doctor(Path(args.repo_root))
    ok = rep.is_ok(soft=args.soft)
    payload: dict[str, object] = {"ok": ok, "checks": rep.checks}
    if args.soft:
        payload["soft"] = True
        payload["strict_ok"] = rep.ok
    print(json.dumps(payload, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
