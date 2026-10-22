from __future__ import annotations

import json
import copy
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def run(
    command: list[str],
    expected: int = 0,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        input=input_text,
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"Unexpected exit code {result.returncode}, expected {expected}\n"
            f"COMMAND: {' '.join(command)}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def main() -> int:
    scripts = Path(__file__).resolve().parent
    skill = scripts.parent
    sample = json.loads((skill / "assets" / "model-spec.example.json").read_text(encoding="utf-8"))
    run([sys.executable, str(scripts / "validate_pipeline_control.py")])

    with tempfile.TemporaryDirectory(prefix="research-to-project-input-") as temp:
        root = Path(temp)
        spec_path = root / "models" / "spec" / "model-spec.json"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_text(
            json.dumps(sample, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for review_file in sample["meta"]["review_files"]:
            path = root / review_file
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# {path.stem}\n\nApproved test source.\n", encoding="utf-8")

        bpmn_dir = root / "models" / "bpmn"
        owl_path = root / "models" / "ontology" / "work-order-ontology.owl"
        graph_dir = root / "models" / "graph"
        docs_dir = root / "docs" / "input"
        manifest = root / "models" / "baseline-manifest.json"

        run([sys.executable, str(scripts / "validate_model_spec.py"), str(spec_path), "--require-approved"])
        run(
            [
                sys.executable,
                str(scripts / "generate_requirements_graph.py"),
                "--spec",
                str(spec_path),
                "--output",
                str(graph_dir / "requirements-graph.ttl"),
                "--shapes-output",
                str(graph_dir / "requirements-shapes.ttl"),
                "--queries-output",
                str(graph_dir / "queries"),
            ]
        )
        run(
            [
                sys.executable,
                str(scripts / "validate_graph_engineering.py"),
                "--spec",
                str(spec_path),
                "--graph",
                str(graph_dir / "requirements-graph.ttl"),
                "--shapes",
                str(graph_dir / "requirements-shapes.ttl"),
                "--ontology",
                str(graph_dir / "requirements-graph-ontology.ttl"),
                "--queries-dir",
                str(graph_dir / "queries"),
                "--report-dir",
                str(graph_dir),
                "--require-approved",
            ]
        )
        run(
            [
                sys.executable,
                str(scripts / "generate_bpmn_from_spec.py"),
                "--spec",
                str(spec_path),
                "--output-dir",
                str(bpmn_dir),
            ]
        )
        run(
            [
                sys.executable,
                str(scripts / "generate_owl_from_spec.py"),
                "--spec",
                str(spec_path),
                "--output",
                str(owl_path),
            ]
        )
        run(
            [
                sys.executable,
                str(scripts / "generate_project_input_from_spec.py"),
                "--spec",
                str(spec_path),
                "--output",
                str(docs_dir),
                "--requirements-graph",
                str(graph_dir / "requirements-graph.ttl"),
                "--bpmn-dir",
                str(bpmn_dir),
                "--owl",
                str(owl_path),
                "--overwrite",
            ]
        )
        baseline_command = [
            sys.executable,
            str(scripts / "create_baseline_manifest.py"),
            "--spec",
            str(spec_path),
            "--bpmn-dir",
            str(bpmn_dir),
            "--owl",
            str(owl_path),
            "--graph-dir",
            str(graph_dir),
            "--docs-dir",
            str(docs_dir),
            "--output",
            str(manifest),
            "--project-root",
            str(root),
        ]
        run(baseline_command)

        delivery_dir = docs_dir / "models"
        export_command = [
            sys.executable,
            str(scripts / "export_delivery_package.py"),
            "--project-root",
            str(root),
            "--spec",
            str(spec_path),
            "--bpmn-dir",
            str(bpmn_dir),
            "--owl",
            str(owl_path),
            "--graph-dir",
            str(graph_dir),
            "--docs-dir",
            str(docs_dir),
        ]
        run(export_command)
        delivery_manifest_path = delivery_dir / "baseline-manifest.json"
        delivery_manifest = json.loads(delivery_manifest_path.read_text(encoding="utf-8"))
        if delivery_manifest.get("baselineId") != sample["meta"]["baseline_id"]:
            raise RuntimeError("Delivery manifest baselineId does not match the spec.")
        listed = {
            entry["path"]: entry["sha256"]
            for entry in delivery_manifest.get("files", [])
        }
        required = {
            "00-项目概述.md",
            "07-待确认问题.md",
            "models/spec/model-spec.json",
            "models/bpmn/PROC-RESULT-PREP.bpmn",
            f"models/ontology/{owl_path.name}",
        }
        missing = sorted(required - set(listed))
        if missing:
            raise RuntimeError(f"Delivery manifest is missing required files: {missing}")
        if "models/baseline-manifest.json" in listed:
            raise RuntimeError("Delivery manifest must not list itself.")
        for relative, digest in listed.items():
            path = docs_dir / relative
            if not path.is_file():
                raise RuntimeError(f"Delivery manifest lists a missing file: {relative}")
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise RuntimeError(f"Delivery manifest hash mismatch: {relative}")

        stale = delivery_dir / "stale.txt"
        stale.write_text("stale\n", encoding="utf-8")
        run(export_command)
        if stale.exists():
            raise RuntimeError("Delivery export did not clear stale package files.")

        validation_command = [
            sys.executable,
            str(scripts / "validate_traceability.py"),
            "--spec",
            str(spec_path),
            "--bpmn-dir",
            str(bpmn_dir),
            "--owl",
            str(owl_path),
            "--graph-dir",
            str(graph_dir),
            "--docs-dir",
            str(docs_dir),
            "--manifest",
            str(manifest),
            "--project-root",
            str(root),
        ]
        run(validation_command)

        capability_doc = docs_dir / "01-能力目录.md"
        original_capability_doc = capability_doc.read_text(encoding="utf-8")
        capability_doc.write_text(
            original_capability_doc + "\n漂移测试\n",
            encoding="utf-8",
        )
        drift_result = run(validation_command, expected=1)
        if "SHA-256 drift" not in drift_result.stderr:
            raise RuntimeError("Negative test did not report SHA-256 drift.")
        run(baseline_command)
        rebaselined_drift = run(validation_command, expected=1)
        if "not an exact projection" not in rebaselined_drift.stderr:
            raise RuntimeError("Rebaselined Markdown drift bypassed semantic projection validation.")
        capability_doc.write_text(original_capability_doc, encoding="utf-8")
        run(baseline_command)

        review_path = root / sample["meta"]["review_files"][0]
        original_review = review_path.read_text(encoding="utf-8")
        review_path.write_text(original_review + "\n审核源漂移\n", encoding="utf-8")
        review_drift = run(validation_command, expected=1)
        if "SHA-256 drift" not in review_drift.stderr:
            raise RuntimeError("Review-source drift test did not report SHA-256 drift.")
        review_path.write_text(original_review, encoding="utf-8")
        run(baseline_command)

        bpmn_path = bpmn_dir / "PROC-RESULT-PREP.bpmn"
        original_bpmn = bpmn_path.read_text(encoding="utf-8")
        bpmn_path.write_text(
            original_bpmn.replace("工单结果数据准备流程", "错误流程名称", 1),
            encoding="utf-8",
        )
        run(baseline_command)
        bpmn_drift = run(validation_command, expected=1)
        if "BPMN projection is not an exact projection" not in bpmn_drift.stderr:
            raise RuntimeError("Rebaselined BPMN semantic drift bypassed validation.")
        bpmn_path.write_text(original_bpmn, encoding="utf-8")
        run(baseline_command)

        graph_path = graph_dir / "requirements-graph.ttl"
        original_graph = graph_path.read_text(encoding="utf-8")
        graph_path.write_text(
            original_graph.replace("工单结果数据准备流程", "错误统一需求图名称", 1),
            encoding="utf-8",
        )
        run(baseline_command)
        graph_drift = run(validation_command, expected=1)
        if "canonical triples" not in graph_drift.stderr:
            raise RuntimeError("Rebaselined unified graph drift bypassed canonical projection validation.")
        graph_path.write_text(original_graph, encoding="utf-8")
        run(baseline_command)

        reviewed = copy.deepcopy(sample)
        reviewed["meta"]["review_status"] = "reviewed"
        reviewed_path = root / "models" / "spec" / "reviewed-model-spec.json"
        reviewed_path.write_text(
            json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(reviewed_path),
                "--require-reviewed",
            ]
        )
        run(
            [
                sys.executable,
                str(scripts / "generate_bpmn_from_spec.py"),
                "--spec",
                str(reviewed_path),
                "--output-dir",
                str(root / "reviewed-bpmn"),
            ]
        )
        run(
            [
                sys.executable,
                str(scripts / "generate_project_input_from_spec.py"),
                "--spec",
                str(reviewed_path),
                "--output",
                str(root / "reviewed-docs"),
            ],
            expected=1,
        )
        bypass_result = run(
            [
                sys.executable,
                str(scripts / "generate_project_input_from_spec.py"),
                "--spec",
                str(reviewed_path),
                "--output",
                str(root / "bypass-docs"),
                "--allow-unapproved",
            ],
            expected=2,
        )
        if "unrecognized arguments: --allow-unapproved" not in bypass_result.stderr:
            raise RuntimeError("Unapproved development-input bypass was not removed.")

        high_blocker = copy.deepcopy(sample)
        high_blocker["questions"][0]["blocking_level"] = "High"
        high_path = root / "models" / "spec" / "high-blocker.json"
        high_path.write_text(
            json.dumps(high_blocker, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        high_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(high_path),
                "--require-approved",
            ],
            expected=1,
        )
        if "open High blocker" not in high_result.stderr:
            raise RuntimeError("High blocker gate did not fail.")

        broken_trace = copy.deepcopy(sample)
        broken_trace["entities"][0]["node_ids"].remove("GW-TASK-COMPLETE")
        broken_path = root / "models" / "spec" / "broken-trace.json"
        broken_path.write_text(
            json.dumps(broken_trace, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        trace_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(broken_path),
                "--require-approved",
            ],
            expected=1,
        )
        if "bidirectional node trace drift" not in trace_result.stderr:
            raise RuntimeError("Bidirectional trace gate did not fail.")

        unreachable = copy.deepcopy(sample)
        unreachable["processes"][0]["flows"] = [
            flow
            for flow in unreachable["processes"][0]["flows"]
            if flow["flow_id"] not in {"FLOW-004", "FLOW-005"}
        ]
        unreachable_path = root / "models" / "spec" / "unreachable.json"
        unreachable_path.write_text(
            json.dumps(unreachable, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        unreachable_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(unreachable_path),
                "--require-approved",
            ],
            expected=1,
        )
        if "unreachable" not in unreachable_result.stderr:
            raise RuntimeError("Unreachable-node gate did not fail.")

        closed_without_resolution = copy.deepcopy(sample)
        closed_without_resolution["questions"][0]["blocking_level"] = "High"
        closed_without_resolution["questions"][0]["status"] = "Closed"
        closed_path = root / "models" / "spec" / "closed-without-resolution.json"
        closed_path.write_text(
            json.dumps(closed_without_resolution, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        closed_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(closed_path),
                "--require-approved",
            ],
            expected=1,
        )
        if "missing required field 'resolution'" not in closed_result.stderr:
            raise RuntimeError("Closed-question evidence gate did not fail.")

        unsupported = copy.deepcopy(sample)
        unsupported["processes"][0]["nodes"][2]["evidence_ids"] = []
        unsupported_path = root / "models" / "spec" / "unsupported-node.json"
        unsupported_path.write_text(
            json.dumps(unsupported, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        unsupported_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(unsupported_path),
                "--require-approved",
            ],
            expected=1,
        )
        if "requires evidence_ids or question_ids" not in unsupported_result.stderr:
            raise RuntimeError("Evidence-or-question gate did not fail.")

        non_chinese = copy.deepcopy(sample)
        non_chinese["processes"][0]["name"] = "Result Preparation Process"
        non_chinese_path = root / "models" / "spec" / "non-chinese-label.json"
        non_chinese_path.write_text(
            json.dumps(non_chinese, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        non_chinese_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_spec.py"),
                str(non_chinese_path),
                "--require-approved",
            ],
            expected=1,
        )
        if "must contain a Chinese business label" not in non_chinese_result.stderr:
            raise RuntimeError("Chinese BPMN/OWL business-label gate did not fail.")

        original_owl = owl_path.read_text(encoding="utf-8")
        owl_path.write_text(
            original_owl.replace('xml:lang="zh-CN"', 'xml:lang="en"', 1),
            encoding="utf-8",
        )
        owl_language_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_artifacts.py"),
                str(owl_path),
            ],
            expected=1,
        )
        if "xml:lang='zh-CN'" not in owl_language_result.stderr:
            raise RuntimeError("OWL zh-CN label gate did not fail.")
        owl_path.write_text(original_owl, encoding="utf-8")

        owl_path.write_text(
            original_owl.replace(
                '<owl:Class rdf:about="https://example.com/ontology/work-order#工单">',
                '<owl:Class rdf:about="https://example.com/ontology/work-order#WorkOrder">',
                1,
            ),
            encoding="utf-8",
        )
        owl_iri_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_artifacts.py"),
                str(owl_path),
            ],
            expected=1,
        )
        if "must use a Chinese IRI local name" not in owl_iri_result.stderr:
            raise RuntimeError("OWL Chinese business-IRI gate did not fail.")
        owl_path.write_text(original_owl, encoding="utf-8")

        owl_path.write_text(
            original_owl.replace(
                "urn:research-to-project-input:trace#稳定标识",
                "urn:research-to-project-input:trace#stableId",
                1,
            ),
            encoding="utf-8",
        )
        owl_arc_iri_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_artifacts.py"),
                str(owl_path),
            ],
            expected=1,
        )
        if "must use a Chinese IRI local name" not in owl_arc_iri_result.stderr:
            raise RuntimeError("OWL Chinese custom-arc IRI gate did not fail.")
        owl_path.write_text(original_owl, encoding="utf-8")

        owl_path.write_text(
            original_owl.replace(
                "<trace:稳定标识>ENT-TEST-TASK</trace:稳定标识>",
                "<trace:稳定标识 />",
                1,
            ),
            encoding="utf-8",
        )
        owl_stable_id_result = run(
            [
                sys.executable,
                str(scripts / "validate_model_artifacts.py"),
                str(owl_path),
            ],
            expected=1,
        )
        if "exactly one non-empty trace:稳定标识" not in owl_stable_id_result.stderr:
            raise RuntimeError("OWL stable-ID annotation gate did not fail.")
        owl_path.write_text(original_owl, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="research-pipeline-runner-") as temp:
        root = Path(temp)
        runner = scripts / "pipeline_runner.py"
        guard_name = "research_pipeline_guard.py"
        common = [sys.executable, str(runner), "--project-root", str(root)]

        run([*common, "init"])
        if not (root / ".codex" / "hooks.json").is_file():
            raise RuntimeError("Pipeline init did not install project-local hooks.")
        premature = run([*common, "run-stage"], expected=1)
        if "Register research files" not in premature.stderr:
            raise RuntimeError("Initialized stage did not block premature automation.")

        research = root / "research.md"
        research.write_text("# Research\n\nConfirmed source.\n", encoding="utf-8")
        run([*common, "register-research", "--file", str(research)])
        run([*common, "run-stage", "--action", "scaffold-review"])

        unconfirmed = run(
            [
                *common,
                "approve",
                "--gate",
                "modeling",
                "--reviewer",
                "Test Reviewer",
                "--review-date",
                "2026-07-30",
                "--note",
                "Reviewed modeling scope",
            ],
            expected=1,
        )
        if "--human-confirmed" not in unconfirmed.stderr:
            raise RuntimeError("Modeling approval did not require explicit human confirmation.")

        review_dir = root / "models" / "review"
        for name in [
            "00-建模范围.md",
            "01-流程建模台账.md",
            "02-领域建模台账.md",
            "03-状态与规则台账.md",
            "04-接口与消息台账.md",
            "05-证据与待确认问题.md",
        ]:
            path = review_dir / name
            path.write_text(
                path.read_text(encoding="utf-8") + "\nConfirmed modeling content.\n",
                encoding="utf-8",
            )
        run(
            [
                *common,
                "approve",
                "--gate",
                "modeling",
                "--reviewer",
                "Test Reviewer",
                "--review-date",
                "2026-07-30",
                "--note",
                "Reviewed modeling scope",
                "--human-confirmed",
            ]
        )

        reviewed = copy.deepcopy(sample)
        reviewed["meta"]["review_status"] = "reviewed"
        reviewed["meta"]["reviewer"] = "Test Reviewer"
        reviewed["meta"]["review_date"] = "2026-07-30"
        spec_path = root / "models" / "spec" / "model-spec.json"
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(
            json.dumps(reviewed, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        run([*common, "run-stage", "--action", "validate-spec"])
        run([*common, "run-stage", "--action", "generate-graph"])
        run([*common, "run-stage", "--action", "validate-graph"])
        run([*common, "run-stage", "--action", "generate-models"])

        human_gate = run([*common, "run-stage"], expected=1)
        if "human gate" not in human_gate.stderr:
            raise RuntimeError("Model approval gate was crossed by run-stage.")

        bpmn_path = root / "models" / "bpmn" / "PROC-RESULT-PREP.bpmn"
        candidate_bpmn = bpmn_path.read_text(encoding="utf-8")
        bpmn_path.write_text(candidate_bpmn + "\n<!-- drift -->\n", encoding="utf-8")
        drifted_approval = run(
            [
                *common,
                "approve",
                "--gate",
                "models",
                "--reviewer",
                "Test Reviewer",
                "--review-date",
                "2026-07-30",
                "--note",
                "Approved candidate models",
                "--human-confirmed",
            ],
            expected=1,
        )
        if "drifted model artifacts" not in drifted_approval.stderr:
            raise RuntimeError("Model approval did not reject candidate drift.")
        bpmn_path.write_text(candidate_bpmn, encoding="utf-8")

        model_review = review_dir / "06-模型审核记录.md"
        model_review.write_text(
            model_review.read_text(encoding="utf-8")
            + "\n| REVIEW-TEST | models/graph + models/bpmn + models/ontology | RDF/BPMN/OWL | 1.0.0 | "
            "Test Reviewer | 2026-07-30 | 通过 | 无 | 全部测试范围 |\n",
            encoding="utf-8",
        )
        run(
            [
                *common,
                "approve",
                "--gate",
                "models",
                "--reviewer",
                "Test Reviewer",
                "--review-date",
                "2026-07-30",
                "--note",
                "Approved candidate models",
                "--human-confirmed",
            ]
        )
        run([*common, "run-stage", "--action", "generate-input"])
        run([*common, "run-stage", "--action", "finalize"])
        run([*common, "validate"])

        status = run([*common, "status", "--json"])
        status_data = json.loads(status.stdout)
        if status_data["current_stage"] != "development_ready" or not status_data["valid"]:
            raise RuntimeError("Pipeline runner did not reach a valid development_ready state.")

        installed_guard = root / ".codex" / "hooks" / guard_name
        blocked_payload = json.dumps(
            {
                "cwd": str(root),
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {
                    "command": "*** Update File: docs/input/01-能力目录.md\n+manual drift\n"
                },
            },
            ensure_ascii=False,
        )
        blocked = run(
            [sys.executable, str(installed_guard), "--mode", "pre-tool"],
            input_text=blocked_payload,
        )
        blocked_data = json.loads(blocked.stdout)
        decision = blocked_data["hookSpecificOutput"]["permissionDecision"]
        if decision != "deny":
            raise RuntimeError("PreToolUse guard did not deny direct generated-file editing.")

        capability_doc = root / "docs" / "input" / "01-能力目录.md"
        capability_doc.write_text(
            capability_doc.read_text(encoding="utf-8") + "\nmanual drift\n",
            encoding="utf-8",
        )
        runner_drift = run([*common, "validate"], expected=1)
        if "SHA-256 drift" not in runner_drift.stderr:
            raise RuntimeError("Pipeline state validation did not detect generated-document drift.")
        stop_payload = json.dumps(
            {
                "cwd": str(root),
                "hook_event_name": "Stop",
                "tool_name": "",
                "tool_input": {},
            },
            ensure_ascii=False,
        )
        stop_result = run(
            [sys.executable, str(installed_guard), "--mode", "stop"],
            input_text=stop_payload,
        )
        stop_data = json.loads(stop_result.stdout)
        if stop_data.get("decision") != "block":
            raise RuntimeError("Stop guard did not block a drifted pipeline turn.")

    print(
        "PASS self-test: state machine, human gates, hooks, generation, semantic "
        "traceability, High blockers, baseline, and drift detection"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
