"""vibecodekit-bridge tool implementations.

Thin shims over the kit's public modules so the MCP layer stays under
~250 LOC. Each tool's contract is documented in the ``inputSchema`` /
``description`` fields of ``TOOL_SCHEMAS`` so an LLM agent reading
``tools/list`` knows exactly how to call them.

PR-1 ships four tools — the minimum surface needed to drive the full
``prompt → spec → build → permission gate`` loop from a CLI agent:

* ``spec.from_prompt``     wrap ``spec_from_prompt.parse``
* ``spec.validate``        wrap ``spec_schema.validate``
* ``build.auto``           wrap ``auto_build.run_pipeline``
* ``verify.permission``    wrap ``permission.orchestrator.run``

Later PRs will extend ``DISPATCH`` with the remaining ~20 verify /
review / backtest tools without changing the wire format.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from vibecodekit_mql5 import (
    audit as audit_mod,
    auto_build,
    broker_safety as broker_safety_mod,
    compile as compile_mod,
    lint as lint_mod,
    lint_best_practice as lint_bp_mod,
    method_hiding_check as method_hiding_mod,
    spec_from_prompt,
    spec_schema,
    trader_check as trader_check_mod,
)
from vibecodekit_mql5 import build as build_mod
from vibecodekit_mql5.permission import orchestrator as orch_mod


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "spec.from_prompt",
        "description": (
            "Translate a free-text EA description into a validated ea-spec.yaml. "
            "Deterministic regex parser — gaps fall back to schema defaults unless "
            "strict=true. Returns yaml + dict + lists of inferred/defaulted fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Free-text description of the EA."},
                "strict": {"type": "boolean", "default": False},
            },
            "required": ["prompt"],
        },
    },
    {
        "name": "spec.validate",
        "description": (
            "Validate a spec dict against the ea-spec.yaml schema. "
            "Returns ok + normalized EaSpec dict + collected errors. "
            "Errors list is empty iff ok=true."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "Parsed spec dict (see spec_schema.py)."},
                "check_presets": {"type": "boolean", "default": True},
            },
            "required": ["spec"],
        },
    },
    {
        "name": "build.auto",
        "description": (
            "Run the kit's full auto-build pipeline: scaffold render → lint (23 AP "
            "detectors) → MetaEditor compile (skippable) → permission gate (7 layers, "
            "skippable) → dashboard. Returns the same report.json the CLI writes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {"type": "object", "description": "Validated spec dict."},
                "out_dir": {"type": "string", "description": "Absolute path for the rendered project."},
                "skip_compile": {"type": "boolean", "default": False},
                "skip_gate": {"type": "boolean", "default": False},
                "skip_dashboard": {"type": "boolean", "default": True},
                "force": {"type": "boolean", "default": False},
                "publish_cmd": {"type": "string", "description": "Optional dashboard publish command."},
            },
            "required": ["spec", "out_dir"],
        },
    },
    {
        "name": "verify.permission",
        "description": (
            "Run the 7-layer permission orchestrator against a rendered .mq5. "
            "Mode personal runs layers 1/2/3/4/7; team adds 5; enterprise runs 1-7. "
            "Fail-fast: returns at the first FAIL layer with a structured report."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5 file."},
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "default": "personal",
                },
                "compile_log": {"type": "string", "description": "Optional MetaEditor compile log path."},
                "trader_check_report": {"type": "string", "description": "Optional trader-check JSON path."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.lint",
        "description": (
            "Run the 8 critical-tier anti-pattern detectors (AP-1/3/5/15/17/18/20/21) "
            "against an .mq5/.mqh. Returns ok + errors + warnings (Finding format). "
            "ok=true iff no ERROR-severity finding."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5/.mqh."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.lint_best_practice",
        "description": (
            "Run the 14 best-practice anti-pattern detectors (AP-2/4/6/7/8/9/10/11/"
            "12/13/14/16/19/22) against an .mq5/.mqh. All findings are WARN severity. "
            "Returns findings grouped by AP code."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5/.mqh."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.method_hiding",
        "description": (
            "Detect method-hiding (CExpert-subclass-without-using-directive). "
            "Severity is ERROR when target_build >= 5260, WARN otherwise. "
            "Returns ok + list of HidingIssue (file/line/derived/base/method)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5."},
                "target_build": {"type": "integer", "default": 5260},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.trader17",
        "description": (
            "Run the 17-point Trader checklist on an .mq5. "
            "Pass threshold: ≥5/17 for personal/team, 17/17 for enterprise. "
            "Any FAIL fails the verdict regardless of mode. Returns ok + per-check "
            "results (PASS/WARN/FAIL/N/A) + summary string."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5."},
                "mode": {
                    "type": "string",
                    "enum": ["personal", "team", "enterprise"],
                    "default": "personal",
                },
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.compile",
        "description": (
            "Compile an .mq5/.mqh via MetaEditor (Wine on Linux). Returns ok + "
            "errors + warnings + ex5_path. Convenience over metaeditor.compile so "
            "agents have one bridge for the full verify suite."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5/.mqh."},
            },
            "required": ["source"],
        },
    },
    {
        "name": "verify.broker_safety",
        "description": (
            "Check fill-policy / lot-step / min-lot / magic-range against a broker "
            "symbol-info JSON. Returns 4 PASS/WARN/FAIL flags + notes. Magic range "
            "is kit-reserved 70000-79999 per plan v5 §6."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Absolute path to the .mq5."},
                "symbol_info": {
                    "type": "object",
                    "description": (
                        "Broker symbol info JSON. Expected keys: filling_modes (list of "
                        "'FOK'/'IOC'/'RETURN'), volume_min (float), volume_step (float)."
                    ),
                },
            },
            "required": ["source", "symbol_info"],
        },
    },
    {
        "name": "verify.audit",
        "description": (
            "Run the kit conformance battery (~70 probes): every public module "
            "imports, every scaffold renders, every reference doc has front-matter, "
            "every methodology template exists. Returns ok + probes list (name/ok/"
            "detail)."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


def _tool_spec_from_prompt(args: dict[str, Any]) -> dict[str, Any]:
    prompt = args["prompt"]
    strict = bool(args.get("strict", False))
    result = spec_from_prompt.parse(prompt)
    if strict and result.defaulted:
        return {
            "ok": False,
            "error": f"strict mode: fields fell back to defaults: {result.defaulted}",
            "spec": result.spec,
            "yaml": spec_from_prompt.to_yaml(result.spec),
            "inferred": list(result.inferred),
            "defaulted": list(result.defaulted),
        }
    return {
        "ok": True,
        "spec": result.spec,
        "yaml": spec_from_prompt.to_yaml(result.spec),
        "inferred": list(result.inferred),
        "defaulted": list(result.defaulted),
    }


def _tool_spec_validate(args: dict[str, Any]) -> dict[str, Any]:
    spec = args["spec"]
    check_presets = bool(args.get("check_presets", True))
    valid_presets = build_mod.PRESETS if check_presets else None
    try:
        ea = spec_schema.validate(spec, valid_presets=valid_presets)
    except spec_schema.SpecValidationError as exc:
        return {"ok": False, "errors": str(exc).split("; "), "spec": None}
    return {"ok": True, "errors": [], "spec": ea.to_dict()}


def _tool_build_auto(args: dict[str, Any]) -> dict[str, Any]:
    spec = args["spec"]
    out_dir = Path(args["out_dir"]).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # Validate first so we never feed a junk spec into the renderer.
    try:
        ea = spec_schema.validate(spec, valid_presets=build_mod.PRESETS)
    except spec_schema.SpecValidationError as exc:
        return {"ok": False, "stage": "validate", "errors": str(exc).split("; ")}
    report = auto_build.run_pipeline(
        spec=spec,
        out_dir=out_dir,
        skip_compile=bool(args.get("skip_compile", False)),
        skip_gate=bool(args.get("skip_gate", False)),
        skip_dashboard=bool(args.get("skip_dashboard", True)),
        force=bool(args.get("force", False)),
        ea_spec=ea,
        publish_cmd=args.get("publish_cmd"),
    )
    return report.to_dict()


def _finding_to_dict(f: Any) -> dict[str, Any]:
    return {
        "path": f.path, "line": f.line, "col": f.col,
        "severity": f.severity, "code": f.code, "message": f.message,
    }


def _tool_verify_lint(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    findings = lint_mod.lint_file(source)
    errors = [f for f in findings if f.severity == "ERROR"]
    warnings = [f for f in findings if f.severity == "WARN"]
    return {
        "ok": not errors,
        "n_errors": len(errors), "n_warnings": len(warnings),
        "errors":   [_finding_to_dict(f) for f in errors],
        "warnings": [_finding_to_dict(f) for f in warnings],
    }


def _tool_verify_lint_best_practice(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    raw = source.read_text(encoding="utf-8", errors="replace")
    # Strip comments the way the critical-AP linter does; the best-practice
    # detectors expect both the raw and the comment-stripped source.
    src = lint_mod._strip_comments(raw)
    grouped: dict[str, list[dict[str, Any]]] = {}
    total = 0
    for code, detector in lint_bp_mod.BEST_PRACTICE_DETECTORS:
        findings = detector(str(source), raw, src)
        grouped[code] = [_finding_to_dict(f) for f in findings]
        total += len(findings)
    # WARN-only tier — ok is always True; this is informational.
    return {"ok": True, "n_warnings": total, "by_code": grouped}


def _tool_verify_method_hiding(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    target_build = int(args.get("target_build", 5260))
    report = method_hiding_mod.check_method_hiding(source, target_build=target_build)
    return {
        "ok": report.ok,
        "path": report.path,
        "target_build": report.target_build,
        "issues": [
            {
                "file": i.file, "line": i.line,
                "derived_class": i.derived_class, "base_class": i.base_class,
                "method": i.method, "severity": i.severity, "fix_hint": i.fix_hint,
            }
            for i in report.issues
        ],
    }


def _tool_verify_trader17(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    mode = args.get("mode", "personal")
    text = source.read_text(encoding="utf-8", errors="replace")
    result = trader_check_mod.evaluate(text)
    ok = trader_check_mod.verdict(result, mode=mode)
    summary = result.pop("_summary", "")
    return {"ok": ok, "mode": mode, "summary": summary, "checks": result}


def _tool_verify_compile(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    report = compile_mod.compile_mq5(source)
    return {
        "ok": bool(report.success),
        "errors": list(report.errors),
        "warnings": list(report.warnings),
        "ex5_path": report.ex5_path,
    }


def _tool_verify_broker_safety(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    symbol_info = args.get("symbol_info") or {}
    if not isinstance(symbol_info, dict):
        return {"ok": False, "error": "symbol_info must be a JSON object"}
    text = source.read_text(encoding="utf-8", errors="replace")
    result = broker_safety_mod.evaluate(text, symbol_info)
    return {"ok": result.all_pass, **result.to_dict()}


def _tool_verify_audit(args: dict[str, Any]) -> dict[str, Any]:
    rep = audit_mod.run_audit()
    return {
        "ok": rep.ok,
        "total": len(rep.probes),
        "passed": sum(1 for p in rep.probes if p.ok),
        "probes": [{"name": p.name, "ok": p.ok, "detail": p.detail} for p in rep.probes],
    }


def _tool_verify_permission(args: dict[str, Any]) -> dict[str, Any]:
    source = Path(args["source"]).resolve()
    if not source.is_file():
        return {"ok": False, "error": f"source not found: {source}"}
    ns = argparse.Namespace(
        source=source,
        mode=args.get("mode", "personal"),
        compile_log=Path(args["compile_log"]) if args.get("compile_log") else None,
        trader_check_report=Path(args["trader_check_report"]) if args.get("trader_check_report") else None,
        state_dir=Path(".rri-state"),
        matrix=None,
        multibroker=None,
        journal=None,
    )
    report = orch_mod.run(ns)
    return report.to_dict()


DISPATCH = {
    "spec.from_prompt":         _tool_spec_from_prompt,
    "spec.validate":            _tool_spec_validate,
    "build.auto":               _tool_build_auto,
    "verify.permission":        _tool_verify_permission,
    "verify.lint":              _tool_verify_lint,
    "verify.lint_best_practice": _tool_verify_lint_best_practice,
    "verify.method_hiding":     _tool_verify_method_hiding,
    "verify.trader17":          _tool_verify_trader17,
    "verify.compile":           _tool_verify_compile,
    "verify.broker_safety":     _tool_verify_broker_safety,
    "verify.audit":             _tool_verify_audit,
}
