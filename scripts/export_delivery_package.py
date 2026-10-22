#!/usr/bin/env python3
"""Export approved research artifacts into the delivery baseline package.

The downstream agent-delivery-gate reads ``docs/input/models/`` and a manifest
whose paths are relative to ``docs/input/``. The research pipeline keeps its
authoring tree at the project root, so this step projects the approved spec,
BPMN, OWL, and graph artifacts into the consumer's layout. It never modifies
the authoring sources or the root ``models/baseline-manifest.json``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from create_baseline_manifest import DOC_NAMES
from model_spec_lib import load_spec, sha256_file, validate_spec

SPEC_DEST = "models/spec/model-spec.json"
MANIFEST_NAME = "baseline-manifest.json"


def resolve_path(raw: str, project_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else project_root / path


def copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.rglob("*")):
        if path.is_file():
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)


def manifest_entries(docs_dir: Path, models_dir: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for name in DOC_NAMES:
        path = docs_dir / name
        entries.append({
            "path": name,
            "sha256": sha256_file(path),
            "role": "projection",
        })
    for path in sorted(models_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.parent == models_dir and path.name == MANIFEST_NAME:
            continue
        relative = path.relative_to(docs_dir).as_posix()
        entries.append({
            "path": relative,
            "sha256": sha256_file(path),
            "role": "spec-source" if relative == SPEC_DEST else "projection",
        })
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Project approved research artifacts into docs/input/models/.")
    parser.add_argument("--project-root", default=".", help="Project root directory.")
    parser.add_argument("--spec", default="models/spec/model-spec.json",
                        help="Approved canonical model spec.")
    parser.add_argument("--bpmn-dir", default="models/bpmn", help="BPMN source directory.")
    parser.add_argument("--owl", default="models/ontology/project.owl",
                        help="Reviewed OWL ontology file.")
    parser.add_argument("--graph-dir", default="models/graph",
                        help="Validated requirements graph directory.")
    parser.add_argument("--docs-dir", default="docs/input",
                        help="Generated 00-07 directory.")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    spec_path = resolve_path(args.spec, project_root)
    bpmn_dir = resolve_path(args.bpmn_dir, project_root)
    owl_path = resolve_path(args.owl, project_root)
    graph_dir = resolve_path(args.graph_dir, project_root)
    docs_dir = resolve_path(args.docs_dir, project_root)
    models_dir = docs_dir / "models"

    try:
        spec = load_spec(spec_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"{spec_path}: cannot load model spec ({exc})", file=sys.stderr)
        return 1
    errors = validate_spec(spec, require_approved=True)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    missing = [str(docs_dir / name) for name in DOC_NAMES if not (docs_dir / name).is_file()]
    bpmn_files = sorted(bpmn_dir.glob("*.bpmn"))
    if not bpmn_files:
        missing.append(str(bpmn_dir / "*.bpmn"))
    if not owl_path.is_file():
        missing.append(str(owl_path))
    if not graph_dir.is_dir():
        missing.append(str(graph_dir))
    if missing:
        for path in missing:
            print(f"{path}: required delivery artifact is missing", file=sys.stderr)
        return 1

    try:
        models_dir.resolve().relative_to(docs_dir.resolve())
    except ValueError:
        print(f"{models_dir}: output directory must be inside {docs_dir}", file=sys.stderr)
        return 1

    if models_dir.exists():
        shutil.rmtree(models_dir)
    (models_dir / "spec").mkdir(parents=True)
    shutil.copy2(spec_path, models_dir / "spec" / "model-spec.json")

    copy_tree(bpmn_dir, models_dir / "bpmn")
    (models_dir / "ontology").mkdir(parents=True)
    shutil.copy2(owl_path, models_dir / "ontology" / owl_path.name)
    copy_tree(graph_dir, models_dir / "graph")

    manifest = {
        "baselineId": spec.get("meta", {}).get("baseline_id"),
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "specSource": SPEC_DEST,
        "hashAlgorithm": "sha256",
        "files": manifest_entries(docs_dir, models_dir),
    }
    manifest_path = models_dir / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(manifest_path)
    print(f"delivery package files: {len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
