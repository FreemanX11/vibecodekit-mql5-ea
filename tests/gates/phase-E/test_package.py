"""Phase E — ship-ready package manifest + zip artifacts."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from vibecodekit_mql5 import package as package_mod


def _write(path: Path, data: bytes | str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return path


def _sample_out_dir(tmp_path: Path) -> Path:
    out = tmp_path / "ShipEA"
    _write(out / "ShipEA.mq5", "// ea")
    _write(out / "ShipEA.ex5", b"\x00EX5")
    _write(out / "ShipEA.log", b"\xff\xfecompile")
    _write(out / "CPipNormalizer.mqh", "// include")
    _write(out / "README.md", "# scaffold")
    _write(out / "Sets" / "default.set", "InpMagic=1\n")
    _write(out / "auto-build-report.json", "{}")
    _write(out / "quality-matrix.html", "<html></html>")
    _write(out / "ShipEA.docs.html", "<html>docs</html>")
    _write(out / "ShipEA.docs.md", "# docs")
    _write(out / "model.onnx", b"onnx")
    _write(out / "returns.csv", "ret\n0.01\n")
    _write(out / "notes.txt", "ignored")
    return out


def test_package_collects_artifacts_by_ship_group(tmp_path: Path) -> None:
    out = _sample_out_dir(tmp_path)
    spec = _write(tmp_path / "ea-spec.yaml", "name: ShipEA\n")

    manifest = package_mod.build_manifest(
        out,
        zip_path=out / "ShipEA-ship.zip",
        spec_path=spec,
        created_at="2026-01-01T00:00:00Z",
    )
    by_path = {a.path: a for a in manifest.artifacts}

    assert by_path["ShipEA.ex5"].group == "runtime"
    assert by_path["Sets/default.set"].kind == "tester-set"
    assert by_path["ShipEA.mq5"].group == "source"
    assert by_path["CPipNormalizer.mqh"].kind == "include"
    assert by_path["auto-build-report.json"].group == "review"
    assert by_path["quality-matrix.html"].kind == "quality-dashboard"
    assert by_path["model.onnx"].kind == "onnx"
    assert by_path["returns.csv"].kind == "csv"
    assert by_path[str(spec)].group == "repro"
    assert "notes.txt" not in by_path
    assert manifest.groups["runtime"] == ["Sets/default.set", "ShipEA.ex5"]


def test_package_manifest_records_sha256_and_writes_zip(tmp_path: Path) -> None:
    out = _sample_out_dir(tmp_path)
    spec = _write(tmp_path / "ea-spec.yaml", "name: ShipEA\n")
    manifest = package_mod.package_out_dir(out, spec_path=spec)
    manifest_path = out / "manifest.json"
    zip_path = out / "ShipEA-ship.zip"

    assert manifest_path.is_file()
    assert zip_path.is_file()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = next(a for a in data["artifacts"] if a["path"] == "ShipEA.mq5")
    assert source["sha256"] == hashlib.sha256((out / "ShipEA.mq5").read_bytes()).hexdigest()

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "ShipEA.ex5" in names
    assert "Sets/default.set" in names
    assert "repro/ea-spec.yaml" in names
    assert "notes.txt" not in names

    assert manifest.zip_path == str(zip_path)


def test_package_cli_returns_manifest_json(tmp_path: Path, capsys) -> None:
    out = _sample_out_dir(tmp_path)
    rc = package_mod.main(["--out-dir", str(out)])
    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert rc == 0
    assert data["package_version"] == 1
    assert (out / "manifest.json").is_file()
    assert (out / "ShipEA-ship.zip").is_file()
