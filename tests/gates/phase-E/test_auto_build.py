"""Phase E — gate suite for the ``mql5-auto-build`` orchestrator.

The orchestrator chains build → lint → compile → permission-gate into a
single command. These tests cover:

    * spec loading (YAML + JSON, error cases)
    * spec validation (missing field, bad mode/preset/stack)
    * run_pipeline fail-fast at each stage boundary
    * report.json emission (always, even on failure)
    * CLI entrypoint exit codes
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
    "name": "AutoBuildTestEA",
    "preset": "stdlib",
    "stack": "netting",
    "symbol": "EURUSD",
    "timeframe": "H1",
    "mode": "personal",
}


def _write_yaml_spec(tmp_path: Path, spec: dict | None = None) -> Path:
    """Write a YAML spec to tmp_path/spec.yaml and return its path."""
    import yaml  # imported lazily; auto_build itself does the same

    payload = dict(spec or MINIMAL_SPEC)
    target = tmp_path / "spec.yaml"
    target.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return target


def _write_json_spec(tmp_path: Path, spec: dict | None = None) -> Path:
    payload = dict(spec or MINIMAL_SPEC)
    target = tmp_path / "spec.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return target


def _patch_compile_success(monkeypatch: pytest.MonkeyPatch, ex5_path: str = "") -> None:
    """Replace ``compile_mq5`` so tests don't need Wine."""

    def _fake_compile(_path, **_kwargs):
        return compile_mod.CompileResult(
            success=True,
            errors=[],
            warnings=[],
            ex5_path=ex5_path or str(_path.with_suffix(".ex5")),
        )

    monkeypatch.setattr(compile_mod, "compile_mq5", _fake_compile)


def _patch_compile_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_compile(_path, **_kwargs):
        return compile_mod.CompileResult(
            success=False,
            errors=["fake: syntax error at line 1"],
            warnings=["fake: deprecated identifier"],
        )

    monkeypatch.setattr(compile_mod, "compile_mq5", _fake_compile)


# ─────────────────────────────────────────────────────────────────────────────
# load_spec
# ─────────────────────────────────────────────────────────────────────────────

def test_load_spec_yaml_round_trips(tmp_path: Path) -> None:
    path = _write_yaml_spec(tmp_path)
    spec = auto_build.load_spec(path)
    assert spec["name"] == MINIMAL_SPEC["name"]
    assert spec["preset"] == "stdlib"
    assert spec["stack"] == "netting"


def test_load_spec_json_round_trips(tmp_path: Path) -> None:
    path = _write_json_spec(tmp_path)
    spec = auto_build.load_spec(path)
    assert spec["symbol"] == "EURUSD"
    assert spec["timeframe"] == "H1"


def test_load_spec_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        auto_build.load_spec(tmp_path / "nope.yaml")


def test_load_spec_non_mapping_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        auto_build.load_spec(bad)


# ─────────────────────────────────────────────────────────────────────────────
# validate_spec
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_spec_happy_path_does_not_raise() -> None:
    auto_build.validate_spec(dict(MINIMAL_SPEC))


def test_validate_spec_missing_field_lists_missing() -> None:
    incomplete = {k: v for k, v in MINIMAL_SPEC.items() if k != "stack"}
    with pytest.raises(ValueError, match="missing required fields.*stack"):
        auto_build.validate_spec(incomplete)


def test_validate_spec_empty_string_field() -> None:
    spec = dict(MINIMAL_SPEC, name="")
    with pytest.raises(ValueError, match=r"spec\.name must be a non-empty string"):
        auto_build.validate_spec(spec)


def test_validate_spec_bad_mode_rejected() -> None:
    spec = dict(MINIMAL_SPEC, mode="dictator")
    with pytest.raises(ValueError, match="spec.mode"):
        auto_build.validate_spec(spec)


def test_validate_spec_bad_preset_rejected() -> None:
    spec = dict(MINIMAL_SPEC, preset="not-a-real-preset")
    with pytest.raises(ValueError, match="spec.preset"):
        auto_build.validate_spec(spec)


def test_validate_spec_bad_stack_for_preset_rejected() -> None:
    # `stdlib` preset does not include the `ml-onnx` stack name.
    spec = dict(MINIMAL_SPEC, stack="ml-onnx-not-supported-here")
    with pytest.raises(ValueError, match="spec.stack"):
        auto_build.validate_spec(spec)


# ─────────────────────────────────────────────────────────────────────────────
# run_pipeline — happy path + skip flags
# ─────────────────────────────────────────────────────────────────────────────

def test_run_pipeline_skipping_compile_and_gate(tmp_path: Path) -> None:
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
    )
    assert report.ok is True
    stage_names = [s.name for s in report.stages]
    assert stage_names == ["build", "lint", "compile", "gate"]
    compile_stage = report.stages[2]
    gate_stage = report.stages[3]
    assert compile_stage.skipped is True
    assert gate_stage.skipped is True
    # The build stage must have produced the .mq5 in the project dir.
    assert (out / f"{MINIMAL_SPEC['name']}.mq5").is_file()


def test_run_pipeline_with_mocked_compile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_compile_success(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_compile=False,
        skip_gate=True,
    )
    # The lint stage emits 1 WARN (AP-22 placeholder signal), no errors —
    # so it must still pass.
    lint_stage = next(s for s in report.stages if s.name == "lint")
    assert lint_stage.ok is True
    assert lint_stage.detail["n_errors"] == 0
    compile_stage = next(s for s in report.stages if s.name == "compile")
    assert compile_stage.ok is True
    assert compile_stage.skipped is False
    assert compile_stage.detail["ex5_path"].endswith(".ex5")


# ─────────────────────────────────────────────────────────────────────────────
# run_pipeline — fail-fast at each stage
# ─────────────────────────────────────────────────────────────────────────────

def test_run_pipeline_fail_fast_on_build_failure(tmp_path: Path) -> None:
    out = tmp_path / "build"
    out.mkdir()
    (out / "marker").write_text("preexisting", encoding="utf-8")
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_compile=True,
        skip_gate=True,
        force=False,
    )
    assert report.ok is False
    # Only the build stage should have run; later stages must be absent.
    assert [s.name for s in report.stages] == ["build"]
    assert report.stages[0].ok is False
    assert "error" in report.stages[0].detail


def test_run_pipeline_fail_fast_on_compile_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_compile_failure(monkeypatch)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC),
        out,
        skip_compile=False,
        skip_gate=True,  # ensure if compile passed gate would have run
    )
    assert report.ok is False
    names = [s.name for s in report.stages]
    assert names == ["build", "lint", "compile"]
    compile_stage = report.stages[-1]
    assert compile_stage.ok is False
    assert "fake: syntax error at line 1" in compile_stage.detail["errors"]


def test_run_pipeline_runs_gate_when_compile_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --no-compile is set the gate must still run (layer 2 will skip)."""
    # Stub the orchestrator to a deterministic pass so the test is hermetic.
    from vibecodekit_mql5.permission import orchestrator as orch_mod

    def _fake_run(_ns):
        return orch_mod.OrchestratorReport(
            mode="personal",
            ok=True,
            layers=[{"layer": 1, "ok": True}, {"layer": 2, "ok": True, "skipped": True}],
        )

    monkeypatch.setattr(orch_mod, "run", _fake_run)
    out = tmp_path / "build"
    report = auto_build.run_pipeline(
        dict(MINIMAL_SPEC), out, skip_compile=True, skip_gate=False
    )
    gate = next(s for s in report.stages if s.name == "gate")
    assert gate.ok is True
    assert gate.skipped is False
    assert gate.detail["mode"] == "personal"
    assert report.ok is True


# ─────────────────────────────────────────────────────────────────────────────
# Report file
# ─────────────────────────────────────────────────────────────────────────────

def test_report_json_emitted_even_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_compile_failure(monkeypatch)
    spec_path = _write_yaml_spec(tmp_path)
    out_dir = tmp_path / "out"
    rc = auto_build.main([
        "--spec", str(spec_path),
        "--out-dir", str(out_dir),
        "--no-gate",
    ])
    assert rc == 1
    report_file = out_dir / "auto-build-report.json"
    assert report_file.is_file(), "report.json must be written on failure too"
    data = json.loads(report_file.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["spec"]["name"] == MINIMAL_SPEC["name"]
    # Stages list captures every stage that ran before the abort.
    assert {s["name"] for s in data["stages"]} >= {"build", "lint", "compile"}


# ─────────────────────────────────────────────────────────────────────────────
# CLI entrypoint
# ─────────────────────────────────────────────────────────────────────────────

def test_main_returns_2_when_spec_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    rc = auto_build.main(["--spec", str(tmp_path / "ghost.yaml")])
    assert rc == 2
    err = capsys.readouterr().err
    assert "spec not found" in err


def test_main_returns_2_when_spec_invalid(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    bad = _write_yaml_spec(tmp_path, dict(MINIMAL_SPEC, preset="garbage"))
    rc = auto_build.main(["--spec", str(bad)])
    assert rc == 2
    err = capsys.readouterr().err
    assert "spec.preset" in err


def test_main_happy_path_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_compile_success(monkeypatch)
    from vibecodekit_mql5.permission import orchestrator as orch_mod
    monkeypatch.setattr(
        orch_mod,
        "run",
        lambda _ns: orch_mod.OrchestratorReport(mode="personal", ok=True, layers=[]),
    )
    spec_path = _write_yaml_spec(tmp_path)
    out_dir = tmp_path / "out"
    rc = auto_build.main([
        "--spec", str(spec_path),
        "--out-dir", str(out_dir),
    ])
    assert rc == 0
    # JSON pipeline report is printed to stdout for the calling shell.
    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed["ok"] is True
    assert parsed["out_dir"] == str(out_dir)


def test_main_default_out_dir_is_cwd_slash_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Without --out-dir, the project is written to CWD / spec.name."""
    _patch_compile_success(monkeypatch)
    from vibecodekit_mql5.permission import orchestrator as orch_mod
    monkeypatch.setattr(
        orch_mod,
        "run",
        lambda _ns: orch_mod.OrchestratorReport(mode="personal", ok=True, layers=[]),
    )
    spec_path = _write_yaml_spec(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    rc = auto_build.main(["--spec", str(spec_path)])
    assert rc == 0
    expected_dir = cwd / MINIMAL_SPEC["name"]
    assert (expected_dir / "auto-build-report.json").is_file()
