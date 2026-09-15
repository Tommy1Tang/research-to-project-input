from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from generate_requirements_graph import build_requirements_graph
from graph_runtime import (
    DeductiveClosure,
    Graph,
    OWL,
    OWLRL_Semantics,
    RDF,
    REQ,
    URIRef,
    deterministic_turtle,
    load_rdf,
    shacl_validate,
)
from model_spec_lib import load_spec, validate_spec


def term_value(value: Any) -> dict[str, str]:
    result = {"value": str(value), "type": value.__class__.__name__}
    datatype = getattr(value, "datatype", None)
    language = getattr(value, "language", None)
    if datatype:
        result["datatype"] = str(datatype)
    if language:
        result["language"] = str(language)
    return result


def run_queries(
    graph: Graph,
    queries_dir: Path,
    manifest: dict[str, Any],
    require_approved: bool,
) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for item in manifest.get("queries", []):
        path = queries_dir / str(item["file"])
        query_text = path.read_text(encoding="utf-8")
        query_result = graph.query(query_text)
        columns = [str(value) for value in getattr(query_result, "vars", [])]
        rows = [
            {
                columns[index]: term_value(value)
                for index, value in enumerate(row)
                if value is not None
            }
            for row in query_result
        ]
        expectation = str(item.get("expectation"))
        severity = str(item.get("severity", "error"))
        blocking = expectation == "empty" or (
            expectation == "empty_when_approved" and require_approved
        )
        passed = not (blocking and rows)
        results.append(
            {
                "query_id": item.get("query_id"),
                "file": item.get("file"),
                "purpose": item.get("purpose"),
                "expectation": expectation,
                "severity": severity,
                "passed": passed,
                "row_count": len(rows),
                "rows": rows,
            }
        )
        if not passed:
            errors.append(
                f"{item.get('query_id')}: expected no result rows, found {len(rows)}"
            )
    return results, errors


def reasoning_violations(graph: Graph) -> list[str]:
    errors: list[str] = []
    for subject in graph.subjects(RDF.type, OWL.Nothing):
        errors.append(f"{subject}: inferred as owl:Nothing")
    for left, right in graph.subject_objects(OWL.disjointWith):
        left_instances = set(graph.subjects(RDF.type, left))
        right_instances = set(graph.subjects(RDF.type, right))
        for subject in sorted(left_instances & right_instances, key=str):
            errors.append(f"{subject}: instance of disjoint classes {left} and {right}")
    for prop in graph.subjects(RDF.type, OWL.FunctionalProperty):
        by_subject: dict[Any, set[Any]] = {}
        for subject, value in graph.subject_objects(prop):
            by_subject.setdefault(subject, set()).add(value)
        for subject, values in by_subject.items():
            if len(values) > 1:
                errors.append(
                    f"{subject}: functional property {prop} has {len(values)} values"
                )
    return sorted(set(errors))


def graph_diff(expected: Graph, actual: Graph) -> list[str]:
    expected_set = set(expected)
    actual_set = set(actual)
    errors: list[str] = []
    missing = sorted(expected_set - actual_set, key=lambda triple: tuple(map(str, triple)))
    extra = sorted(actual_set - expected_set, key=lambda triple: tuple(map(str, triple)))
    if missing:
        errors.append(f"requirements graph is missing {len(missing)} canonical triples")
    if extra:
        errors.append(f"requirements graph contains {len(extra)} non-canonical triples")
    return errors


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run canonical graph comparison, SHACL, OWL-RL reasoning, and SPARQL gates."
    )
    parser.add_argument("--spec", required=True)
    parser.add_argument("--graph", default="models/graph/requirements-graph.ttl")
    parser.add_argument("--shapes", default="models/graph/requirements-shapes.ttl")
    parser.add_argument("--ontology", default="models/graph/requirements-graph-ontology.ttl")
    parser.add_argument("--queries-dir", default="models/graph/queries")
    parser.add_argument("--report-dir", default="models/graph")
    parser.add_argument("--require-approved", action="store_true")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = load_spec(spec_path)
    errors = validate_spec(
        spec,
        require_approved=args.require_approved,
        require_reviewed=not args.require_approved,
    )
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    graph_path = Path(args.graph)
    data_graph = load_rdf(graph_path)
    expected_graph = build_requirements_graph(spec, spec_path)
    errors.extend(graph_diff(expected_graph, data_graph))

    shapes_graph = load_rdf(Path(args.shapes))
    ontology_graph = load_rdf(Path(args.ontology))
    conforms, shacl_graph, shacl_text = shacl_validate(
        data_graph,
        shacl_graph=shapes_graph,
        ont_graph=ontology_graph,
        inference="owlrl",
        advanced=True,
        meta_shacl=True,
        serialize_report_graph=False,
    )

    report_dir = Path(args.report_dir)
    deterministic_turtle(shacl_graph, report_dir / "shacl-report.ttl")
    if not conforms:
        errors.append("SHACL validation failed")

    inferred = Graph()
    for triple in data_graph:
        inferred.add(triple)
    for triple in ontology_graph:
        inferred.add(triple)
    before = len(inferred)
    DeductiveClosure(OWLRL_Semantics, axiomatic_triples=False).expand(inferred)
    inferred_count = len(inferred) - before
    deterministic_turtle(inferred, report_dir / "inferred-graph.ttl")
    reasoning_errors = reasoning_violations(inferred)
    errors.extend(reasoning_errors)

    manifest_path = Path(args.queries_dir) / "query-manifest.json"
    query_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    query_results, query_errors = run_queries(
        inferred, Path(args.queries_dir), query_manifest, args.require_approved
    )
    errors.extend(query_errors)

    reasoning_report = {
        "engine": "OWL-RL",
        "input_triples": before,
        "inferred_triples": inferred_count,
        "output_triples": len(inferred),
        "consistent": not reasoning_errors,
        "violations": reasoning_errors,
    }
    write_json(report_dir / "reasoning-report.json", reasoning_report)
    write_json(
        report_dir / "sparql-results.json",
        {
            "engine": "RDFLib SPARQL 1.1",
            "require_approved": args.require_approved,
            "queries": query_results,
        },
    )
    aggregate = {
        "graph_file": graph_path.as_posix(),
        "canonical_projection": not graph_diff(expected_graph, data_graph),
        "shacl": {
            "conforms": bool(conforms),
            "report": "shacl-report.ttl",
            "summary": str(shacl_text),
        },
        "reasoning": reasoning_report,
        "sparql": {
            "passed": not query_errors,
            "query_count": len(query_results),
            "failed_query_ids": [
                item["query_id"] for item in query_results if not item["passed"]
            ],
        },
        "approved_gate": args.require_approved,
        "valid": not errors,
        "errors": errors,
    }
    write_json(report_dir / "graph-validation-report.json", aggregate)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(
        "PASS canonical RDF projection, SHACL, OWL-RL reasoning, "
        f"and {len(query_results)} SPARQL queries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
