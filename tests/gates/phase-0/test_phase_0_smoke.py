"""Phase 0 smoke tests — bootstrap acceptance gate.

5 tests that verify the Wine + MetaEditor + Python + CI environment is ready.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_wine_version_8_or_above():
    """Test 1: Wine version must be >= 8.0."""
    if not shutil.which("wine"):
        pytest.skip("Wine not installed (likely Windows runner; skip)")
    result = subprocess.run(["wine", "--version"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, f"wine --version failed: {result.stderr}"
    match = re.search(r"(\d+)\.(\d+)", result.stdout)
    assert match, f"Cannot parse Wine version from: {result.stdout!r}"
    major, minor = int(match.group(1)), int(match.group(2))
    assert major >= 8, f"Wine {major}.{minor} too old; need >= 8.0"


def test_metaeditor_compile_demo_mq5(tmp_path):
    """Test 2: MetaEditor compiles a minimal .mq5 with 0 errors."""
    metaeditor = os.environ.get("METAEDITOR_PATH")
    if not metaeditor:
        # Try Linux Wine path. The MT5 installer writes "MetaEditor64.exe"
        # (mixed case); rglob is case-sensitive on Linux, so match both forms.
        wineprefix = os.environ.get("WINEPREFIX", str(Path.home() / ".wine-mql5"))
        candidates: list[Path] = []
        if Path(wineprefix).exists():
            for pattern in ("metaeditor64.exe", "MetaEditor64.exe"):
                candidates.extend(Path(wineprefix).rglob(pattern))
        if candidates:
            metaeditor = str(candidates[0])
    if not metaeditor:
        pytest.skip("METAEDITOR_PATH not set; skipping compile smoke")

    demo_mq5 = REPO_ROOT / "tests" / "fixtures" / "demo_smoke.mq5"
    assert demo_mq5.exists(), f"Demo fixture missing: {demo_mq5}"

    # Copy to tmp and compile
    work = tmp_path / "demo_smoke.mq5"
    work.write_text(demo_mq5.read_text())
    log = tmp_path / "compile.log"

    if sys.platform.startswith("linux"):
        cmd = ["xvfb-run", "-a", "wine", metaeditor, f"/compile:{work}", f"/log:{log}"]
    else:
        cmd = [metaeditor, f"/compile:{work}", f"/log:{log}"]

    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # MetaEditor returns various exit codes; check log content for success
    if log.exists():
        log_text = log.read_text(encoding="utf-16-le", errors="ignore")
        if "0 error" in log_text.lower() or "0 errors" in log_text.lower():
            return  # pass
    pytest.fail(f"MetaEditor compile may have failed; check {log}")


def test_xvfb_headless_works():
    """Test 3: xvfb-run is available and works."""
    if not sys.platform.startswith("linux"):
        pytest.skip("xvfb is Linux-only")
    if not shutil.which("xvfb-run"):
        pytest.fail("xvfb-run not in PATH; install xvfb package")
    result = subprocess.run(
        ["xvfb-run", "-a", "echo", "OK"],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, f"xvfb-run failed: {result.stderr}"
    assert "OK" in result.stdout


def test_python_venv_pytest():
    """Test 4: pytest is installed and version >= 7."""
    import pytest as _pytest
    version = tuple(int(x) for x in _pytest.__version__.split(".")[:2])
    assert version >= (7, 0), f"pytest {_pytest.__version__} too old; need >= 7.0"


def test_ci_workflow_yaml_valid():
    """Test 5: .github/workflows/ci.yml is valid YAML."""
    ci = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.exists(), f"CI workflow missing: {ci}"
    with ci.open() as f:
        data = yaml.safe_load(f)
    assert "jobs" in data, "CI yaml has no 'jobs' key"
    assert "linux-tests" in data["jobs"], "CI yaml missing linux-tests job"
    assert "windows-tests" in data["jobs"], "CI yaml missing windows-tests job"
