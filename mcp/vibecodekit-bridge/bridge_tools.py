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

from vibecodekit_mql5 import auto_build, spec_from_prompt, spec_schema
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
    "spec.from_prompt":   _tool_spec_from_prompt,
    "spec.validate":      _tool_spec_validate,
    "build.auto":         _tool_build_auto,
    "verify.permission":  _tool_verify_permission,
}
