from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REVIEW_FILES = [
    "00-建模范围.md",
    "01-流程建模台账.md",
    "02-领域建模台账.md",
    "03-状态与规则台账.md",
    "04-接口与消息台账.md",
    "05-证据与待确认问题.md",
    "06-模型审核记录.md",
]
MODELING_REVIEW_FILES = REVIEW_FILES[:6]
GENERATED_INPUT_FILES = [
    "00-项目概述.md",
    "01-能力目录.md",
    "02-领域模型.md",
    "03-状态机.md",
    "04-业务规则.md",
    "05-流程模型.md",
    "06-调研台账摘要.md",
    "07-待确认问题.md",
]


class PipelineError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PipelineError(f"Missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise PipelineError(f"Expected a JSON object: {path}")
    return data


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)


class Pipeline:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.skill_root = Path(__file__).resolve().parent.parent
        self.scripts = self.skill_root / "scripts"
        self.definition_path = self.skill_root / "references" / "pipeline-definition.json"
        self.definition = load_json(self.definition_path)
        self.state_rel = Path(str(self.definition["state_file"]))
        self.state_path = self.root / self.state_rel
        self.stage_rows = list(self.definition["stages"])
        self.stage_index = {row["id"]: int(row["index"]) for row in self.stage_rows}
        self.stage_by_id = {row["id"]: row for row in self.stage_rows}

    def load_state(self) -> dict[str, Any]:
        state = load_json(self.state_path)
        if state.get("pipeline_id") != self.definition.get("pipeline_id"):
            raise PipelineError(f"{self.state_path}: pipeline_id does not match this runner")
        stage = state.get("current_stage")
        if stage not in self.stage_index:
            raise PipelineError(f"{self.state_path}: unknown current_stage {stage!r}")
        return state

    def save_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = now_iso()
        write_json_atomic(self.state_path, state)

    def event(
        self,
        state: dict[str, Any],
        action: str,
        from_stage: str,
        to_stage: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        state.setdefault("events", []).append(
            {
                "sequence": len(state.get("events", [])) + 1,
                "timestamp": now_iso(),
                "action": action,
                "from_stage": from_stage,
                "to_stage": to_stage,
                "result": "passed",
                "details": details or {},
            }
        )
        state["current_stage"] = to_stage

    def path_record(self, path: Path) -> dict[str, str]:
        resolved = path.resolve()
        try:
            label = resolved.relative_to(self.root).as_posix()
        except ValueError:
            label = str(resolved)
        return {"path": label, "sha256": sha256(resolved)}

    def resolve_record(self, record: dict[str, str]) -> Path:
        path = Path(record["path"])
        return path if path.is_absolute() else self.root / path

    def record_group(self, state: dict[str, Any], group: str, paths: list[Path]) -> None:
        state.setdefault("artifacts", {})[group] = [
            self.path_record(path) for path in sorted(paths, key=lambda item: str(item))
        ]

    def require_stage(self, state: dict[str, Any], expected: str) -> None:
        actual = state["current_stage"]
        if actual != expected:
            next_action = self.stage_by_id[actual]["next_action"]
            raise PipelineError(
                f"Action is not allowed at stage {actual!r}; expected {expected!r}. "
                f"Current next action: {next_action}"
            )

    def run_script(self, name: str, arguments: list[str]) -> None:
        command = [sys.executable, str(self.scripts / name), *arguments]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        result = subprocess.run(
            command,
            cwd=self.root,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        if result.stdout:
            print(result.stdout.rstrip())
        if result.returncode:
            message = result.stderr.strip() or result.stdout.strip()
            raise PipelineError(f"{name} failed:\n{message}")

    def spec_path(self) -> Path:
        return self.root / str(self.definition["canonical_source"])

    def review_paths(self, names: list[str] | None = None) -> list[Path]:
        return [self.root / "models" / "review" / name for name in (names or REVIEW_FILES)]

    def load_spec(self) -> dict[str, Any]:
        return load_json(self.spec_path())

    def owl_path(self, spec: dict[str, Any] | None = None) -> Path:
        spec = spec or self.load_spec()
        ontology_id = str(spec.get("meta", {}).get("ontology_id") or "project-ontology")
        return self.root / "models" / "ontology" / f"{ontology_id}.owl"

    def graph_dir(self) -> Path:
        return self.root / "models" / "graph"

    def graph_path(self) -> Path:
        return self.graph_dir() / "requirements-graph.ttl"

    def graph_contract_paths(self) -> list[Path]:
        graph_dir = self.graph_dir()
        query_dir = graph_dir / "queries"
        return [
            graph_dir / "requirements-graph-ontology.ttl",
            graph_dir / "requirements-shapes.ttl",
            *sorted(query_dir.glob("*.rq")),
            query_dir / "query-manifest.json",
        ]

    def graph_validation_paths(self) -> list[Path]:
        graph_dir = self.graph_dir()
        return [
            graph_dir / "inferred-graph.ttl",
            graph_dir / "shacl-report.ttl",
            graph_dir / "reasoning-report.json",
            graph_dir / "sparql-results.json",
            graph_dir / "graph-validation-report.json",
        ]

    def init(self, install_hooks: bool) -> None:
        if self.state_path.exists():
            raise PipelineError(
                f"Pipeline already initialized: {self.state_path}. Use status or reopen; do not overwrite state."
            )
        self.run_script("validate_pipeline_control.py", [])
        template = load_json(self.skill_root / "assets" / "pipeline-state.template.json")
        timestamp = now_iso()
        template["pipeline_definition_version"] = self.definition["version"]
        template["runner_script"] = str(Path(__file__).resolve())
        template["created_at"] = timestamp
        template["updated_at"] = timestamp
        template["events"] = [
            {
                "sequence": 1,
                "timestamp": timestamp,
                "action": "init",
                "from_stage": "",
                "to_stage": "initialized",
                "result": "passed",
                "details": {},
            }
        ]
        self.save_state(template)
        if install_hooks:
            self.install_hooks()
        print(f"Initialized pipeline at {self.state_path}")

    def install_hooks(self) -> None:
        codex_dir = self.root / ".codex"
        hook_dir = codex_dir / "hooks"
        hook_dir.mkdir(parents=True, exist_ok=True)
        guard_target = hook_dir / "research_pipeline_guard.py"
        shutil.copy2(self.scripts / "pipeline_guard.py", guard_target)

        hooks_path = codex_dir / "hooks.json"
        if hooks_path.exists():
            config = load_json(hooks_path)
        else:
            config = {"description": "Project-local Codex lifecycle hooks.", "hooks": {}}
        hooks = config.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise PipelineError(f"{hooks_path}: hooks must be a JSON object")

        python = str(Path(sys.executable).resolve()).replace('"', '\\"')
        guard = str(guard_target.resolve()).replace('"', '\\"')
        commands = {
            "PreToolUse": f'"{python}" "{guard}" --mode pre-tool',
            "Stop": f'"{python}" "{guard}" --mode stop',
        }
        for event_name, command in commands.items():
            groups = hooks.setdefault(event_name, [])
            exists = any(
                "research_pipeline_guard.py" in str(handler.get("command", ""))
                for group in groups
                for handler in group.get("hooks", [])
                if isinstance(handler, dict)
            )
            if exists:
                continue
            group: dict[str, Any] = {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": 10,
                    }
                ]
            }
            if event_name == "PreToolUse":
                group["matcher"] = "Bash|apply_patch|Edit|Write"
            groups.append(group)
        write_json_atomic(hooks_path, config)
        print(
            f"Installed project hooks at {hooks_path}. "
            "Review/trust the changed hook definition in Codex before relying on it."
        )

    def register_research(self, files: list[str]) -> None:
        state = self.load_state()
        self.require_stage(state, "initialized")
        if not files:
            raise PipelineError("At least one --file is required")
        paths: list[Path] = []
        for value in files:
            candidate = Path(value)
            path = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
            if not path.is_file():
                raise PipelineError(f"Research file does not exist: {path}")
            paths.append(path)
        state["research_files"] = [self.path_record(path) for path in paths]
        self.event(
            state,
            "register-research",
            "initialized",
            "research_registered",
            {"file_count": len(paths)},
        )
        self.save_state(state)
        print(f"Registered {len(paths)} research file(s)")

    def scaffold_review(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "research_registered")
        self.run_script("scaffold_modeling_review.py", ["--output", "models/review"])
        paths = self.review_paths()
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise PipelineError("Modeling scaffold is incomplete: " + ", ".join(missing))
        self.event(state, "scaffold-review", "research_registered", "modeling_scaffolded")
        self.save_state(state)

    def ensure_review_completed(self, names: list[str]) -> list[Path]:
        from scaffold_modeling_review import FILES

        paths = self.review_paths(names)
        for path in paths:
            if not path.is_file():
                raise PipelineError(f"Missing review file: {path}")
            original = FILES[path.name].replace("\r\n", "\n").strip()
            current = path.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
            if current == original:
                raise PipelineError(f"Review file is still an untouched scaffold: {path}")
            if not current:
                raise PipelineError(f"Review file is empty: {path}")
        return paths

    def approve(
        self,
        gate: str,
        reviewer: str,
        review_date: str,
        note: str,
        human_confirmed: bool,
    ) -> None:
        if not human_confirmed:
            raise PipelineError(
                "Approval requires --human-confirmed after a person has reviewed the named artifacts"
            )
        if not reviewer.strip() or not review_date.strip() or not note.strip():
            raise PipelineError("Approval requires reviewer, review_date, and a non-empty note")
        state = self.load_state()
        if gate == "modeling":
            self.require_stage(state, "modeling_scaffolded")
            paths = self.ensure_review_completed(MODELING_REVIEW_FILES)
            approval = {
                "actor_type": "human",
                "reviewer": reviewer,
                "review_date": review_date,
                "approval_note": note,
                "recorded_at": now_iso(),
                "artifact_hashes": [self.path_record(path) for path in paths],
            }
            state["approvals"]["modeling"] = approval
            self.record_group(state, "modeling_review", paths)
            self.event(
                state,
                "approve-modeling",
                "modeling_scaffolded",
                "modeling_review_approved",
                {"reviewer": reviewer, "review_date": review_date},
            )
            self.save_state(state)
            print("Recorded human approval for modeling Markdown")
            return

        if gate != "models":
            raise PipelineError(f"Unknown approval gate: {gate}")
        self.require_stage(state, "models_generated")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Cannot approve drifted model artifacts:\n" + "\n".join(errors))
        review_record = self.ensure_review_completed(["06-模型审核记录.md"])[0]
        review_text = review_record.read_text(encoding="utf-8")
        if reviewer not in review_text:
            raise PipelineError("06-模型审核记录.md must contain the named reviewer")
        if "通过" not in review_text and "approved" not in review_text.lower():
            raise PipelineError("06-模型审核记录.md must contain an approved/通过 conclusion")
        if not any(token in review_text for token in ("RDF", "需求图", "requirements-graph")):
            raise PipelineError(
                "06-模型审核记录.md must explicitly include the unified RDF requirements graph"
            )

        spec = self.load_spec()
        meta = spec.setdefault("meta", {})
        meta["review_status"] = "approved"
        meta["reviewer"] = reviewer
        meta["review_date"] = review_date
        expected_review_files = [f"models/review/{name}" for name in REVIEW_FILES]
        meta["review_files"] = expected_review_files
        write_json_atomic(self.spec_path(), spec)
        self.run_script(
            "validate_model_spec.py",
            [str(self.spec_path()), "--require-approved"],
        )
        self.run_script(
            "generate_requirements_graph.py",
            [
                "--spec",
                str(self.spec_path()),
                "--output",
                str(self.graph_path()),
                "--shapes-output",
                str(self.graph_dir() / "requirements-shapes.ttl"),
                "--queries-output",
                str(self.graph_dir() / "queries"),
            ],
        )
        self.run_script(
            "validate_graph_engineering.py",
            [
                "--spec",
                str(self.spec_path()),
                "--graph",
                str(self.graph_path()),
                "--shapes",
                str(self.graph_dir() / "requirements-shapes.ttl"),
                "--ontology",
                str(self.graph_dir() / "requirements-graph-ontology.ttl"),
                "--queries-dir",
                str(self.graph_dir() / "queries"),
                "--report-dir",
                str(self.graph_dir()),
                "--require-approved",
            ],
        )
        owl = self.owl_path(spec)
        self.run_script(
            "generate_bpmn_from_spec.py",
            ["--spec", str(self.spec_path()), "--output-dir", "models/bpmn"],
        )
        self.run_script(
            "generate_owl_from_spec.py",
            ["--spec", str(self.spec_path()), "--output", str(owl)],
        )
        self.run_script(
            "validate_model_artifacts.py",
            ["models/bpmn", str(owl)],
        )
        bpmn_paths = sorted((self.root / "models" / "bpmn").glob("*.bpmn"))
        state["approvals"]["models"] = {
            "actor_type": "human",
            "reviewer": reviewer,
            "review_date": review_date,
            "approval_note": note,
            "recorded_at": now_iso(),
            "candidate_artifact_hashes": [
                *state["artifacts"].get("requirements_graph", []),
                *state["artifacts"].get("graph_validation", []),
                *state["artifacts"].get("bpmn", []),
                *state["artifacts"].get("owl", []),
            ],
        }
        self.record_group(state, "modeling_review", self.review_paths())
        self.record_group(state, "model_spec", [self.spec_path()])
        self.record_group(state, "requirements_graph", [self.graph_path()])
        self.record_group(state, "graph_contracts", self.graph_contract_paths())
        self.record_group(state, "graph_validation", self.graph_validation_paths())
        self.record_group(state, "bpmn", bpmn_paths)
        self.record_group(state, "owl", [owl])
        self.event(
            state,
            "approve-models",
            "models_generated",
            "models_approved",
            {"reviewer": reviewer, "review_date": review_date},
        )
        self.save_state(state)
        print(
            "Recorded human model approval and regenerated approved "
            "RDF graph, BPMN, and OWL"
        )

    def validate_spec(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "modeling_review_approved")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Upstream review artifacts drifted:\n" + "\n".join(errors))
        self.run_script(
            "validate_model_spec.py",
            [str(self.spec_path()), "--require-reviewed"],
        )
        spec = self.load_spec()
        declared = set(spec.get("meta", {}).get("review_files", []))
        required = {f"models/review/{name}" for name in REVIEW_FILES}
        if not required.issubset(declared):
            missing = sorted(required - declared)
            raise PipelineError("model-spec.json is missing review_files: " + ", ".join(missing))
        self.record_group(state, "model_spec", [self.spec_path()])
        self.event(state, "validate-spec", "modeling_review_approved", "spec_reviewed")
        self.save_state(state)

    def generate_graph(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "spec_reviewed")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Cannot generate graph from a drifted source:\n" + "\n".join(errors))
        self.run_script(
            "generate_requirements_graph.py",
            [
                "--spec",
                str(self.spec_path()),
                "--output",
                str(self.graph_path()),
                "--shapes-output",
                str(self.graph_dir() / "requirements-shapes.ttl"),
                "--queries-output",
                str(self.graph_dir() / "queries"),
            ],
        )
        contracts = self.graph_contract_paths()
        missing = [str(path) for path in [self.graph_path(), *contracts] if not path.is_file()]
        if missing:
            raise PipelineError("Graph generation is incomplete: " + ", ".join(missing))
        self.record_group(state, "requirements_graph", [self.graph_path()])
        self.record_group(state, "graph_contracts", contracts)
        self.event(state, "generate-graph", "spec_reviewed", "graph_generated")
        self.save_state(state)

    def validate_graph(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "graph_generated")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Cannot validate a drifted graph package:\n" + "\n".join(errors))
        self.run_script(
            "validate_graph_engineering.py",
            [
                "--spec",
                str(self.spec_path()),
                "--graph",
                str(self.graph_path()),
                "--shapes",
                str(self.graph_dir() / "requirements-shapes.ttl"),
                "--ontology",
                str(self.graph_dir() / "requirements-graph-ontology.ttl"),
                "--queries-dir",
                str(self.graph_dir() / "queries"),
                "--report-dir",
                str(self.graph_dir()),
            ],
        )
        reports = self.graph_validation_paths()
        missing = [str(path) for path in reports if not path.is_file()]
        if missing:
            raise PipelineError("Graph validation reports are incomplete: " + ", ".join(missing))
        self.record_group(state, "graph_validation", reports)
        self.event(state, "validate-graph", "graph_generated", "graph_validated")
        self.save_state(state)

    def generate_models(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "graph_validated")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Cannot generate from a drifted source:\n" + "\n".join(errors))
        spec = self.load_spec()
        owl = self.owl_path(spec)
        self.run_script(
            "generate_bpmn_from_spec.py",
            ["--spec", str(self.spec_path()), "--output-dir", "models/bpmn"],
        )
        self.run_script(
            "generate_owl_from_spec.py",
            ["--spec", str(self.spec_path()), "--output", str(owl)],
        )
        self.run_script("validate_model_artifacts.py", ["models/bpmn", str(owl)])
        bpmn_paths = sorted((self.root / "models" / "bpmn").glob("*.bpmn"))
        if not bpmn_paths:
            raise PipelineError("No BPMN files were generated")
        self.record_group(state, "bpmn", bpmn_paths)
        self.record_group(state, "owl", [owl])
        self.event(state, "generate-models", "graph_validated", "models_generated")
        self.save_state(state)

    def generate_input(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "models_approved")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Cannot generate input from drifted approved models:\n" + "\n".join(errors))
        owl = self.owl_path()
        self.run_script(
            "generate_project_input_from_spec.py",
            [
                "--spec",
                str(self.spec_path()),
                "--output",
                "docs/input",
                "--requirements-graph",
                str(self.graph_path()),
                "--bpmn-dir",
                "models/bpmn",
                "--owl",
                str(owl),
                "--overwrite",
            ],
        )
        docs = [self.root / "docs" / "input" / name for name in GENERATED_INPUT_FILES]
        missing = [str(path) for path in docs if not path.is_file()]
        if missing:
            raise PipelineError("Generated development input is incomplete: " + ", ".join(missing))
        self.record_group(state, "development_input", docs)
        self.event(
            state,
            "generate-input",
            "models_approved",
            "development_input_generated",
        )
        self.save_state(state)

    def finalize(self, state: dict[str, Any]) -> None:
        self.require_stage(state, "development_input_generated")
        errors = self.validate_state(state, run_final=False)
        if errors:
            raise PipelineError("Cannot finalize a drifted pipeline:\n" + "\n".join(errors))
        owl = self.owl_path()
        manifest = self.root / "models" / "baseline-manifest.json"
        delivery_manifest = self.root / "docs" / "input" / "models" / "baseline-manifest.json"
        self.run_script(
            "create_baseline_manifest.py",
            [
                "--spec",
                str(self.spec_path()),
                "--bpmn-dir",
                "models/bpmn",
                "--owl",
                str(owl),
                "--graph-dir",
                str(self.graph_dir()),
                "--docs-dir",
                "docs/input",
                "--output",
                str(manifest),
                "--project-root",
                str(self.root),
            ],
        )
        self.run_script(
            "export_delivery_package.py",
            [
                "--project-root",
                str(self.root),
                "--spec",
                str(self.spec_path()),
                "--bpmn-dir",
                "models/bpmn",
                "--owl",
                str(owl),
                "--graph-dir",
                str(self.graph_dir()),
                "--docs-dir",
                "docs/input",
            ],
        )
        self.run_script(
            "validate_traceability.py",
            [
                "--spec",
                str(self.spec_path()),
                "--bpmn-dir",
                "models/bpmn",
                "--owl",
                str(owl),
                "--graph-dir",
                str(self.graph_dir()),
                "--docs-dir",
                "docs/input",
                "--manifest",
                str(manifest),
                "--project-root",
                str(self.root),
            ],
        )
        self.record_group(state, "baseline_manifest", [manifest, delivery_manifest])
        self.event(
            state,
            "finalize",
            "development_input_generated",
            "development_ready",
        )
        self.save_state(state)

    def run_stage(self, requested_action: str | None) -> None:
        state = self.load_state()
        stage = state["current_stage"]
        expected = self.stage_by_id[stage]["next_action"]
        if requested_action and requested_action != expected:
            raise PipelineError(
                f"Requested action {requested_action!r} is not allowed; expected {expected!r}"
            )
        if stage == "research_registered":
            self.scaffold_review(state)
        elif stage == "modeling_review_approved":
            self.validate_spec(state)
        elif stage == "spec_reviewed":
            self.generate_graph(state)
        elif stage == "graph_generated":
            self.validate_graph(state)
        elif stage == "graph_validated":
            self.generate_models(state)
        elif stage == "models_approved":
            self.generate_input(state)
        elif stage == "development_input_generated":
            self.finalize(state)
        elif stage in {"modeling_scaffolded", "models_generated"}:
            raise PipelineError(
                f"Stage {stage!r} is a human gate. Use approve only after a person reviews the artifacts."
            )
        elif stage == "initialized":
            raise PipelineError("Register research files before running an automated stage")
        else:
            self.validate(quiet=False)

    def validate_records(self, records: list[dict[str, str]], label: str) -> list[str]:
        errors: list[str] = []
        for record in records:
            path = self.resolve_record(record)
            if not path.is_file():
                errors.append(f"{label}: missing {path}")
                continue
            actual = sha256(path)
            if actual != record.get("sha256"):
                errors.append(f"{label}: SHA-256 drift {path}")
        return errors

    def validate_state(self, state: dict[str, Any], run_final: bool) -> list[str]:
        errors = self.validate_records(state.get("research_files", []), "research")
        rank = self.stage_index[state["current_stage"]]
        groups = state.get("artifacts", {})
        thresholds = [
            ("modeling_review", "modeling_review_approved"),
            ("model_spec", "spec_reviewed"),
            ("requirements_graph", "graph_generated"),
            ("graph_contracts", "graph_generated"),
            ("graph_validation", "graph_validated"),
            ("bpmn", "models_generated"),
            ("owl", "models_generated"),
            ("development_input", "development_input_generated"),
            ("baseline_manifest", "development_ready"),
        ]
        for group, threshold in thresholds:
            if rank >= self.stage_index[threshold]:
                records = groups.get(group, [])
                if not records:
                    errors.append(f"{group}: no artifact hashes recorded")
                else:
                    errors.extend(self.validate_records(records, group))
        if run_final and state["current_stage"] == "development_ready" and not errors:
            owl = self.owl_path()
            manifest = self.root / "models" / "baseline-manifest.json"
            command = [
                sys.executable,
                str(self.scripts / "validate_traceability.py"),
                "--spec",
                str(self.spec_path()),
                "--bpmn-dir",
                "models/bpmn",
                "--owl",
                str(owl),
                "--graph-dir",
                str(self.graph_dir()),
                "--docs-dir",
                "docs/input",
                "--manifest",
                str(manifest),
                "--project-root",
                str(self.root),
            ]
            result = subprocess.run(
                command,
                cwd=self.root,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONUTF8": "1"},
            )
            if result.returncode:
                errors.append("traceability validation failed: " + (result.stderr.strip() or result.stdout.strip()))
        return errors

    def validate(self, quiet: bool) -> None:
        state = self.load_state()
        errors = self.validate_state(state, run_final=True)
        if errors:
            raise PipelineError("\n".join(errors))
        if not quiet:
            print(f"PASS pipeline state and artifacts at stage {state['current_stage']}")

    def status(self, as_json: bool) -> None:
        state = self.load_state()
        stage = self.stage_by_id[state["current_stage"]]
        errors = self.validate_state(state, run_final=state["current_stage"] == "development_ready")
        result = {
            "pipeline_id": state["pipeline_id"],
            "current_stage": state["current_stage"],
            "stage_type": stage["type"],
            "next_action": stage["next_action"],
            "valid": not errors,
            "errors": errors,
            "modeling_approval": state.get("approvals", {}).get("modeling"),
            "model_approval": state.get("approvals", {}).get("models"),
        }
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Stage: {result['current_stage']} ({result['stage_type']})")
            print(f"Next action: {result['next_action']}")
            print(f"Integrity: {'PASS' if result['valid'] else 'FAIL'}")
            for error in errors:
                print(f"- {error}")

    def next(self, as_json: bool) -> None:
        state = self.load_state()
        stage = self.stage_by_id[state["current_stage"]]
        action = stage["next_action"]
        commands = {
            "register-research": "pipeline_runner.py --project-root . register-research --file <research-file>",
            "scaffold-review": "pipeline_runner.py --project-root . run-stage",
            "approve-modeling": (
                "pipeline_runner.py --project-root . approve --gate modeling "
                "--reviewer <name> --review-date YYYY-MM-DD --note <decision> --human-confirmed"
            ),
            "validate-spec": "pipeline_runner.py --project-root . run-stage",
            "generate-graph": "pipeline_runner.py --project-root . run-stage",
            "validate-graph": "pipeline_runner.py --project-root . run-stage",
            "generate-models": "pipeline_runner.py --project-root . run-stage",
            "approve-models": (
                "pipeline_runner.py --project-root . approve --gate models "
                "--reviewer <name> --review-date YYYY-MM-DD --note <decision> --human-confirmed"
            ),
            "generate-input": "pipeline_runner.py --project-root . run-stage",
            "finalize": "pipeline_runner.py --project-root . run-stage",
            "validate": "pipeline_runner.py --project-root . validate",
        }
        result = {
            "current_stage": state["current_stage"],
            "stage_type": stage["type"],
            "next_action": action,
            "description": stage["description"],
            "command": commands[action],
        }
        if as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Next action: {action}")
            print(stage["description"])
            print(commands[action])

    def reopen(self, target: str, reason: str) -> None:
        state = self.load_state()
        current = state["current_stage"]
        if target not in self.stage_index:
            raise PipelineError(f"Unknown target stage: {target}")
        if self.stage_index[target] >= self.stage_index[current]:
            raise PipelineError("reopen target must be earlier than the current stage")
        if target not in {"initialized", "research_registered", "modeling_scaffolded", "modeling_review_approved"}:
            raise PipelineError(
                "Reopen only to initialized, research_registered, modeling_scaffolded, "
                "or modeling_review_approved"
            )
        if not reason.strip():
            raise PipelineError("reopen requires a non-empty --reason")

        if self.stage_index[target] < self.stage_index["modeling_review_approved"]:
            state["approvals"]["modeling"] = None
            state["artifacts"]["modeling_review"] = []
        if self.stage_index[target] < self.stage_index["models_approved"]:
            state["approvals"]["models"] = None
        clear_thresholds = {
            "model_spec": "spec_reviewed",
            "requirements_graph": "graph_generated",
            "graph_contracts": "graph_generated",
            "graph_validation": "graph_validated",
            "bpmn": "models_generated",
            "owl": "models_generated",
            "development_input": "development_input_generated",
            "baseline_manifest": "development_ready",
        }
        for group, threshold in clear_thresholds.items():
            if self.stage_index[target] < self.stage_index[threshold]:
                state["artifacts"][group] = []
        self.event(
            state,
            "reopen",
            current,
            target,
            {"reason": reason},
        )
        self.save_state(state)
        print(f"Reopened pipeline from {current} to {target}; downstream files are stale until regenerated")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stateful controller for the research-to-project-input pipeline."
    )
    parser.add_argument("--project-root", default=".", help="Target project root.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize state and project-local hooks.")
    init_parser.add_argument("--no-hooks", action="store_true", help="Do not install Codex hooks.")

    subparsers.add_parser("install-hooks", help="Install or refresh project-local Codex hooks.")

    register = subparsers.add_parser("register-research", help="Register and hash research files.")
    register.add_argument("--file", action="append", required=True, help="Research file; repeat as needed.")

    status = subparsers.add_parser("status", help="Show stage, next action, approvals, and drift.")
    status.add_argument("--json", action="store_true", help="Emit JSON.")

    next_parser = subparsers.add_parser("next", help="Show the only valid next action.")
    next_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    run_stage = subparsers.add_parser("run-stage", help="Run the current automated stage.")
    run_stage.add_argument("--action", help="Optional expected action; fails if it is not current.")

    approve = subparsers.add_parser("approve", help="Record an explicit human approval gate.")
    approve.add_argument("--gate", choices=["modeling", "models"], required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--review-date", required=True)
    approve.add_argument("--note", required=True)
    approve.add_argument("--human-confirmed", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate current state and artifact integrity.")
    validate.add_argument("--quiet", action="store_true")

    reopen = subparsers.add_parser("reopen", help="Move backward after a controlled change request.")
    reopen.add_argument("--to", required=True, dest="target")
    reopen.add_argument("--reason", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        pipeline = Pipeline(Path(args.project_root))
        if args.command == "init":
            pipeline.init(install_hooks=not args.no_hooks)
        elif args.command == "install-hooks":
            pipeline.install_hooks()
        elif args.command == "register-research":
            pipeline.register_research(args.file)
        elif args.command == "status":
            pipeline.status(args.json)
        elif args.command == "next":
            pipeline.next(args.json)
        elif args.command == "run-stage":
            pipeline.run_stage(args.action)
        elif args.command == "approve":
            pipeline.approve(
                args.gate,
                args.reviewer,
                args.review_date,
                args.note,
                args.human_confirmed,
            )
        elif args.command == "validate":
            pipeline.validate(args.quiet)
        elif args.command == "reopen":
            pipeline.reopen(args.target, args.reason)
        else:
            raise PipelineError(f"Unhandled command: {args.command}")
    except PipelineError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
