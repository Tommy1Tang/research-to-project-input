from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from model_spec_lib import load_spec, sha256_file, validate_spec


DOC_NAMES = [
    "00-项目概述.md",
    "01-能力目录.md",
    "02-领域模型.md",
    "03-状态机.md",
    "04-业务规则.md",
    "05-流程模型.md",
    "06-调研台账摘要.md",
    "07-待确认问题.md",
]
GRAPH_NAMES = [
    "requirements-graph.ttl",
    "requirements-graph-ontology.ttl",
    "requirements-shapes.ttl",
    "inferred-graph.ttl",
    "shacl-report.ttl",
    "reasoning-report.json",
    "sparql-results.json",
    "graph-validation-report.json",
]


def relative_path(path: Path, project_root: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def artifact(kind: str, path: Path, project_root: Path) -> dict[str, str]:
    return {
        "kind": kind,
        "path": relative_path(path, project_root),
        "sha256": sha256_file(path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a SHA-256 baseline manifest for model projections.")
    parser.add_argument("--spec", required=True, help="Path to approved model-spec.json.")
    parser.add_argument("--bpmn-dir", default="models/bpmn", help="BPMN directory.")
    parser.add_argument("--owl", required=True, help="OWL file.")
    parser.add_argument("--graph-dir", required=True, help="Validated requirements graph directory.")
    parser.add_argument("--docs-dir", default="docs/input", help="Generated 00-07 directory.")
    parser.add_argument("--output", default="models/baseline-manifest.json", help="Manifest output path.")
    parser.add_argument("--project-root", default=".", help="Root used for relative manifest paths.")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = load_spec(spec_path)
    errors = validate_spec(spec, require_approved=True)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    project_root = Path(args.project_root)
    bpmn_dir = Path(args.bpmn_dir)
    owl_path = Path(args.owl)
    graph_dir = Path(args.graph_dir)
    docs_dir = Path(args.docs_dir)
    meta = spec.get("meta", {})
    expected_bpmn = [bpmn_dir / f"{item['process_id']}.bpmn" for item in spec.get("processes", [])]
    expected_docs = [docs_dir / name for name in DOC_NAMES]
    expected_graph = [
        *(graph_dir / name for name in GRAPH_NAMES),
        graph_dir / "queries" / "query-manifest.json",
        *sorted((graph_dir / "queries").glob("*.rq")),
    ]
    review_files = [
        resolve_path(str(path), project_root)
        for path in meta.get("review_files", [])
    ]
    evidence_files = [
        resolve_path(str(item["file_or_link"]), project_root)
        for item in spec.get("evidence", [])
        if item.get("file_or_link") and "://" not in str(item.get("file_or_link"))
    ]
    required = [
        spec_path,
        *review_files,
        *evidence_files,
        *expected_bpmn,
        owl_path,
        *expected_graph,
        *expected_docs,
    ]
    missing = [path for path in required if not path.exists()]
    if missing:
        for path in missing:
            print(f"{path}: required baseline file is missing", file=sys.stderr)
        return 1

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "baseline_id": meta.get("baseline_id"),
        "model_version": meta.get("model_version"),
        "review_status": meta.get("review_status"),
        "reviewer": meta.get("reviewer"),
        "review_date": meta.get("review_date"),
        "source_spec": artifact("model-spec", spec_path, project_root),
        "review_sources": [
            *(artifact("modeling-review", path, project_root) for path in review_files),
            *(artifact("evidence", path, project_root) for path in evidence_files),
        ],
        "artifacts": [
            *(artifact("bpmn", path, project_root) for path in expected_bpmn),
            artifact("owl", owl_path, project_root),
            *(artifact("requirements-graph", path, project_root) for path in expected_graph),
            *(artifact("docs-input", path, project_root) for path in expected_docs),
        ],
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(output)
    return 0


def resolve_path(raw: str, project_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else project_root / path


if __name__ == "__main__":
    raise SystemExit(main())
