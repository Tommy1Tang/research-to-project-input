from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


STATE_REL = Path(".requirements-pipeline/pipeline-state.json")
STAGE_RANK = {
    "initialized": 0,
    "research_registered": 1,
    "modeling_scaffolded": 2,
    "modeling_review_approved": 3,
    "spec_reviewed": 4,
    "graph_generated": 5,
    "graph_validated": 6,
    "models_generated": 7,
    "models_approved": 8,
    "development_input_generated": 9,
    "development_ready": 10,
}


def find_project_root(cwd: Path) -> Path | None:
    current = cwd.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / STATE_REL).is_file():
            return candidate
    return None


def deny(reason: str) -> int:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


def normalized(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False).replace("\\", "/").lower()


def protected_markers(stage: str) -> list[str]:
    markers = [
        ".requirements-pipeline/pipeline-state.json",
        "models/bpmn/",
        "models/ontology/",
        "models/graph/",
        "docs/input/",
        "models/baseline-manifest.json",
    ]
    rank = STAGE_RANK.get(stage, 0)
    if rank >= STAGE_RANK["modeling_review_approved"]:
        markers.extend(
            [
                "models/review/00-建模范围.md",
                "models/review/01-流程建模台账.md",
                "models/review/02-领域建模台账.md",
                "models/review/03-状态与规则台账.md",
                "models/review/04-接口与消息台账.md",
                "models/review/05-证据与待确认问题.md",
            ]
        )
    if rank >= STAGE_RANK["spec_reviewed"]:
        markers.append("models/spec/model-spec.json")
    if rank >= STAGE_RANK["models_approved"]:
        markers.append("models/review/06-模型审核记录.md")
    return [marker.lower() for marker in markers]


def looks_like_write(tool_name: str, text: str) -> bool:
    lowered = tool_name.lower()
    if lowered in {"apply_patch", "edit", "write"}:
        return True
    if any(token in lowered for token in ("write", "edit", "delete", "move", "copy", "create")):
        return True
    patterns = [
        r"\bset-content\b",
        r"\badd-content\b",
        r"\bout-file\b",
        r"\bcopy-item\b",
        r"\bmove-item\b",
        r"\bremove-item\b",
        r"\bnew-item\b",
        r"\btee\b",
        r">",
        r"\bgenerate_bpmn_from_spec\.py\b",
        r"\bgenerate_owl_from_spec\.py\b",
        r"\bgenerate_requirements_graph\.py\b",
        r"\bvalidate_graph_engineering\.py\b",
        r"\bgenerate_project_input_from_spec\.py\b",
        r"\bcreate_baseline_manifest\.py\b",
    ]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def pre_tool(payload: dict[str, Any], root: Path, state: dict[str, Any]) -> int:
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input", {})
    text = normalized(tool_input)
    if "pipeline_runner.py" in text:
        return 0
    markers = protected_markers(str(state.get("current_stage", "initialized")))
    touched = [marker for marker in markers if marker in text]
    if not touched or not looks_like_write(tool_name, text):
        return 0
    return deny(
        "Requirements pipeline protected artifact write blocked. "
        "Use pipeline_runner.py, or run pipeline_runner.py reopen before editing reviewed sources. "
        f"Matched: {', '.join(touched)}"
    )


def stop(root: Path, state: dict[str, Any]) -> int:
    runner = Path(str(state.get("runner_script", "")))
    if not runner.is_file():
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "Requirements pipeline runner is missing; restore the installed skill before ending.",
                },
                ensure_ascii=False,
            )
        )
        return 0
    result = subprocess.run(
        [
            sys.executable,
            str(runner),
            "--project-root",
            str(root),
            "validate",
            "--quiet",
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.returncode:
        reason = result.stderr.strip() or result.stdout.strip()
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "Requirements pipeline integrity check failed: " + reason,
                },
                ensure_ascii=False,
            )
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["pre-tool", "stop"], required=True)
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    cwd = Path(str(payload.get("cwd") or "."))
    root = find_project_root(cwd)
    if root is None:
        return 0
    try:
        state = json.loads((root / STATE_REL).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if args.mode == "pre-tool":
        return pre_tool(payload, root, state)
    return stop(root, state)


if __name__ == "__main__":
    raise SystemExit(main())
