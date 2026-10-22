from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

from model_spec_lib import (
    all_known_ids,
    load_spec,
    sha256_file,
    text_list,
    validate_spec,
)
from generate_bpmn_from_spec import build_bpmn
from generate_owl_from_spec import TRACE_TERMS, build_owl
from generate_project_input_from_spec import (
    FILES,
    generate_00,
    generate_01,
    generate_02,
    generate_03,
    generate_04,
    generate_05,
    generate_06,
    generate_07,
    generated_header,
    rule_id,
)

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


BPMN_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}
OWL_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "trace": "urn:research-to-project-input:trace#",
}
RDF_ABOUT = f"{{{OWL_NS['rdf']}}}about"
RDF_RESOURCE = f"{{{OWL_NS['rdf']}}}resource"
DOC_COVERAGE = {
    "00-项目概述.md": ("roles", "scenarios"),
    "01-能力目录.md": ("capabilities",),
    "02-领域模型.md": ("entities", "relations", "fields"),
    "03-状态机.md": ("states",),
    "04-业务规则.md": ("rules",),
    "05-流程模型.md": ("processes", "nodes", "flows", "exceptions", "interfaces"),
    "06-调研台账摘要.md": ("evidence",),
    "07-待确认问题.md": ("questions",),
}
TRACE_ATTR_MAP = {
    "capabilityIds": "capability_ids",
    "entityIds": "entity_ids",
    "ruleIds": "rule_ids",
    "stateIds": "state_ids",
    "interfaceIds": "interface_ids",
    "exceptionIds": "exception_ids",
    "evidenceIds": "evidence_ids",
    "questionIds": "question_ids",
}
TRACE_PROPERTY_NAMES = {
    "baselineId": "基线标识",
    "modelVersion": "模型版本",
    "processId": "流程标识",
    "nodeId": "节点标识",
    "scenarioIds": "场景标识",
    "roleIds": "角色标识",
    "capabilityIds": "能力标识",
    "entityIds": "实体标识",
    "ruleIds": "规则标识",
    "stateIds": "状态标识",
    "interfaceIds": "接口标识",
    "exceptionIds": "异常标识",
    "evidenceIds": "证据标识",
    "questionIds": "待确认问题标识",
}


def fragment(value: str) -> str:
    if "#" in value:
        value = value.rsplit("#", 1)[1]
    elif "/" in value:
        value = value.rsplit("/", 1)[1]
    return unquote(value)


def owl_stable_id(element: ET.Element) -> str:
    stable_id = element.find(f"trace:{TRACE_TERMS['stableId']}", OWL_NS)
    return (stable_id.text or "").strip() if stable_id is not None else ""


def index_owl_resources(
    root: ET.Element,
    xpath: str,
    owl_path: Path,
    errors: list[str],
) -> dict[str, ET.Element]:
    indexed: dict[str, ET.Element] = {}
    for item in root.findall(xpath, OWL_NS):
        resource_iri = item.get(RDF_ABOUT, "")
        stable_id = owl_stable_id(item)
        if not resource_iri or not stable_id:
            continue
        if stable_id in indexed:
            errors.append(f"{owl_path}: duplicate trace:稳定标识 '{stable_id}'")
            continue
        indexed[stable_id] = item
    return indexed


def split_trace(value: str | None) -> set[str]:
    return {item for item in (value or "").split("|") if item and item != "无"}


def camunda_trace(element: ET.Element) -> dict[str, str]:
    by_chinese_name = {
        str(item.get("name", "")): str(item.get("value", ""))
        for item in element.findall(
            "bpmn:extensionElements/camunda:properties/camunda:property",
            BPMN_NS,
        )
    }
    return {
        key: by_chinese_name.get(chinese_name, "")
        for key, chinese_name in TRACE_PROPERTY_NAMES.items()
    }


def xml_signature(element: ET.Element) -> tuple:
    return (
        element.tag,
        tuple(sorted(element.attrib.items())),
        (element.text or "").strip(),
        tuple(xml_signature(child) for child in list(element)),
    )


def owl_cardinality_constraints(cardinality: str, required: bool) -> set[tuple[str, int]]:
    normalized = "".join(str(cardinality).split()).upper()
    if normalized == "1:1":
        return {("cardinality", 1)} if required else {("maxCardinality", 1)}
    if normalized in {"N:1", "M:1"}:
        result = {("maxCardinality", 1)}
        if required:
            result.add(("minCardinality", 1))
        return result
    if normalized in {"1:N", "1:M", "N:M", "M:N"}:
        return {("minCardinality", 1)} if required else set()
    if normalized in {"0..1", "0:1"}:
        return {("maxCardinality", 1)}
    if normalized == "1..1":
        return {("cardinality", 1)}
    if normalized == "1..*":
        return {("minCardinality", 1)}
    return set()


def validate_bpmn(
    spec: dict,
    bpmn_dir: Path,
    errors: list[str],
) -> None:
    meta = spec.get("meta", {})
    for process in spec.get("processes", []):
        process_id = str(process["process_id"])
        path = bpmn_dir / f"{process_id}.bpmn"
        if not path.exists():
            errors.append(f"{path}: missing BPMN projection")
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            errors.append(f"{path}: XML parse error: {exc}")
            continue
        expected_tree = build_bpmn(spec, process)
        if xml_signature(root) != xml_signature(expected_tree.getroot()):
            errors.append(f"{path}: BPMN projection is not an exact projection of model-spec.json")
        process_element = root.find(f".//bpmn:process[@id='{process_id}']", BPMN_NS)
        if process_element is None:
            errors.append(f"{path}: process_id '{process_id}' not found")
        for node in process.get("nodes", []):
            node_id = str(node["node_id"])
            element = root.find(f".//*[@id='{node_id}']")
            if element is None:
                errors.append(f"{path}: node_id '{node_id}' not found")
                continue
            trace = camunda_trace(element)
            if not trace.get("baselineId"):
                errors.append(f"{path}: node_id '{node_id}' has no Camunda trace properties")
                continue
            if trace["baselineId"] != str(meta.get("baseline_id", "")):
                errors.append(f"{path}: node_id '{node_id}' baselineId drift")
            if trace["modelVersion"] != str(meta.get("model_version", "")):
                errors.append(f"{path}: node_id '{node_id}' modelVersion drift")
            for attr, field in TRACE_ATTR_MAP.items():
                expected = set(text_list(node.get(field)))
                actual = split_trace(trace.get(attr))
                if actual != expected:
                    errors.append(
                        f"{path}: node_id '{node_id}' {attr} drift; "
                        f"expected={sorted(expected)} actual={sorted(actual)}"
                    )
        for flow in process.get("flows", []):
            flow_id = str(flow["flow_id"])
            element = root.find(f".//bpmn:sequenceFlow[@id='{flow_id}']", BPMN_NS)
            if element is None:
                errors.append(f"{path}: flow_id '{flow_id}' not found")
                continue
            if element.get("sourceRef") != str(flow["source"]) or element.get("targetRef") != str(flow["target"]):
                errors.append(f"{path}: flow_id '{flow_id}' source/target drift")
            trace = camunda_trace(element)
            if not trace.get("baselineId"):
                errors.append(f"{path}: flow_id '{flow_id}' has no Camunda trace properties")
                continue
            for attr, field in (
                ("ruleIds", "rule_ids"),
                ("exceptionIds", "exception_ids"),
                ("evidenceIds", "evidence_ids"),
                ("questionIds", "question_ids"),
            ):
                expected = set(text_list(flow.get(field)))
                actual = split_trace(trace.get(attr))
                if actual != expected:
                    errors.append(
                        f"{path}: flow_id '{flow_id}' {attr} drift; "
                        f"expected={sorted(expected)} actual={sorted(actual)}"
                    )
        represented_exceptions = {
            exception_id
            for flow in process.get("flows", [])
            for exception_id in text_list(flow.get("exception_ids"))
        }
        expected_exceptions = {
            str(item["exception_id"]) for item in process.get("exceptions", [])
        }
        for exception_id in sorted(expected_exceptions - represented_exceptions):
            errors.append(f"{path}: exception_id '{exception_id}' has no BPMN path")


def validate_owl(spec: dict, owl_path: Path, errors: list[str]) -> None:
    if not owl_path.exists():
        errors.append(f"{owl_path}: missing OWL projection")
        return
    try:
        root = ET.parse(owl_path).getroot()
    except ET.ParseError as exc:
        errors.append(f"{owl_path}: XML parse error: {exc}")
        return
    expected_tree = build_owl(spec)
    if xml_signature(root) != xml_signature(expected_tree.getroot()):
        errors.append(f"{owl_path}: OWL projection is not an exact projection of model-spec.json")
    class_elements = index_owl_resources(
        root, ".//owl:Class", owl_path, errors
    )
    object_properties = index_owl_resources(
        root, ".//owl:ObjectProperty", owl_path, errors
    )
    datatype_properties = index_owl_resources(
        root, ".//owl:DatatypeProperty", owl_path, errors
    )
    individuals = index_owl_resources(
        root, ".//owl:NamedIndividual", owl_path, errors
    )
    resource_stable_ids = {
        item.get(RDF_ABOUT, ""): owl_stable_id(item)
        for xpath in (
            ".//owl:Class",
            ".//owl:ObjectProperty",
            ".//owl:DatatypeProperty",
            ".//owl:NamedIndividual",
        )
        for item in root.findall(xpath, OWL_NS)
        if item.get(RDF_ABOUT) and owl_stable_id(item)
    }
    expected_entities = {str(item["entity_id"]) for item in spec.get("entities", [])}
    expected_relations = {str(item["relation_id"]) for item in spec.get("relations", [])}
    expected_fields = {
        str(attribute["field_id"])
        for entity in spec.get("entities", [])
        for attribute in entity.get("attributes", [])
        if attribute.get("field_id")
    }
    missing_entities = expected_entities - set(class_elements)
    missing_relations = expected_relations - set(object_properties)
    missing_fields = expected_fields - set(datatype_properties)
    for entity_id in sorted(missing_entities):
        errors.append(f"{owl_path}: entity_id '{entity_id}' not found as owl:Class")
    for relation_id in sorted(missing_relations):
        errors.append(f"{owl_path}: relation_id '{relation_id}' not found as owl:ObjectProperty")
    for field_id in sorted(missing_fields):
        errors.append(f"{owl_path}: field_id '{field_id}' not found as owl:DatatypeProperty")

    for entity in spec.get("entities", []):
        entity_id = str(entity["entity_id"])
        element = class_elements.get(entity_id)
        if element is None:
            continue
        parent = entity.get("parent_entity_id")
        parent_element = next(
            (
                child
                for child in element.findall("rdfs:subClassOf", OWL_NS)
                if child.get(RDF_ABOUT.replace("about", "resource"))
            ),
            None,
        )
        actual_parent = (
            resource_stable_ids.get(parent_element.get(RDF_RESOURCE, ""), "")
            if parent_element is not None
            else "Thing"
        )
        if str(parent or "Thing") != actual_parent:
            errors.append(f"{owl_path}: entity_id '{entity_id}' parent class drift")
        actual_synonyms = {
            child.text or "" for child in element.findall("skos:altLabel", OWL_NS)
        }
        if actual_synonyms != set(text_list(entity.get("synonyms"))):
            errors.append(f"{owl_path}: entity_id '{entity_id}' synonym drift")

    for relation in spec.get("relations", []):
        relation_id = str(relation["relation_id"])
        element = object_properties.get(relation_id)
        if element is None:
            continue
        domain = element.find("rdfs:domain", OWL_NS)
        range_element = element.find("rdfs:range", OWL_NS)
        actual_domain = (
            resource_stable_ids.get(domain.get(RDF_RESOURCE, ""), "")
            if domain is not None
            else ""
        )
        actual_range = (
            resource_stable_ids.get(range_element.get(RDF_RESOURCE, ""), "")
            if range_element is not None
            else ""
        )
        if actual_domain != str(relation.get("source_entity_id")):
            errors.append(f"{owl_path}: relation_id '{relation_id}' domain drift")
        if actual_range != str(relation.get("target_entity_id")):
            errors.append(f"{owl_path}: relation_id '{relation_id}' range drift")
        source_class = class_elements.get(str(relation.get("source_entity_id")))
        actual_constraints: set[tuple[str, int]] = set()
        if source_class is not None:
            for restriction in source_class.findall("rdfs:subClassOf/owl:Restriction", OWL_NS):
                on_property = restriction.find("owl:onProperty", OWL_NS)
                if on_property is None:
                    continue
                property_id = resource_stable_ids.get(
                    on_property.get(RDF_RESOURCE, ""), ""
                )
                if property_id != relation_id:
                    continue
                for predicate in ("cardinality", "minCardinality", "maxCardinality"):
                    value = restriction.find(f"owl:{predicate}", OWL_NS)
                    if value is not None and value.text:
                        actual_constraints.add((predicate, int(value.text)))
        expected_constraints = owl_cardinality_constraints(
            str(relation.get("cardinality", "")),
            bool(relation.get("required", False)),
        )
        if actual_constraints != expected_constraints:
            errors.append(
                f"{owl_path}: relation_id '{relation_id}' cardinality drift; "
                f"expected={sorted(expected_constraints)} actual={sorted(actual_constraints)}"
            )

    datatype_map = {
        "string": "string",
        "int": "integer",
        "integer": "integer",
        "decimal": "decimal",
        "boolean": "boolean",
        "date": "date",
        "datetime": "dateTime",
        "dateTime": "dateTime",
        "text": "string",
        "enum": "string",
        "json": "string",
    }
    for entity in spec.get("entities", []):
        for attribute in entity.get("attributes", []):
            field_id = str(attribute["field_id"])
            element = datatype_properties.get(field_id)
            if element is None:
                continue
            domain = element.find("rdfs:domain", OWL_NS)
            range_element = element.find("rdfs:range", OWL_NS)
            actual_domain = (
                resource_stable_ids.get(domain.get(RDF_RESOURCE, ""), "")
                if domain is not None
                else ""
            )
            actual_range = (
                fragment(range_element.get(RDF_RESOURCE, ""))
                if range_element is not None
                else ""
            )
            expected_range = datatype_map.get(str(attribute.get("datatype", "string")), "string")
            if actual_domain != str(entity["entity_id"]):
                errors.append(f"{owl_path}: field_id '{field_id}' domain drift")
            if actual_range != expected_range:
                errors.append(f"{owl_path}: field_id '{field_id}' datatype drift")

    for state in spec.get("states", []):
        state_id = str(state["state_id"])
        individual = individuals.get(state_id)
        if individual is None:
            errors.append(f"{owl_path}: state_id '{state_id}' not found as owl:NamedIndividual")
            continue
        checks = {
            "entityId": state.get("entity_id"),
            "fromState": state.get("from_state"),
            "toState": state.get("to_state"),
            "trigger": state.get("trigger"),
            "nodeIds": state.get("node_id"),
            "guardRuleIds": "|".join(text_list(state.get("guard_rule_ids"))),
        }
        for field, expected in checks.items():
            child = individual.find(f"trace:{TRACE_TERMS[field]}", OWL_NS)
            actual = child.text if child is not None else ""
            if actual != str(expected or ""):
                errors.append(f"{owl_path}: state_id '{state_id}' {field} drift")
    ontology = root.find(".//owl:Ontology", OWL_NS)
    if ontology is None:
        errors.append(f"{owl_path}: owl:Ontology not found")
        return
    baseline = ontology.find(f"trace:{TRACE_TERMS['baselineId']}", OWL_NS)
    version = ontology.find("owl:versionInfo", OWL_NS)
    if baseline is None or baseline.text != str(spec.get("meta", {}).get("baseline_id", "")):
        errors.append(f"{owl_path}: baselineId drift")
    if version is None or version.text != str(spec.get("meta", {}).get("model_version", "")):
        errors.append(f"{owl_path}: modelVersion drift")


def validate_docs(
    spec: dict,
    spec_path: Path,
    requirements_graph: Path,
    bpmn_dir: Path,
    owl_path: Path,
    docs_dir: Path,
    errors: list[str],
) -> None:
    ids = all_known_ids(spec)
    meta = spec.get("meta", {})
    header = generated_header(spec, spec_path, requirements_graph, bpmn_dir, owl_path)
    generators = {
        "00": generate_00,
        "01": generate_01,
        "02": generate_02,
        "03": generate_03,
        "04": generate_04,
        "05": generate_05,
        "06": generate_06,
        "07": generate_07,
    }
    filename_to_key = {filename: key for key, filename in FILES.items()}
    for filename, collections in DOC_COVERAGE.items():
        path = docs_dir / filename
        if not path.exists():
            errors.append(f"{path}: missing development input file")
            continue
        text = path.read_text(encoding="utf-8")
        key = filename_to_key[filename]
        expected_text = generators[key](spec, header)
        if text != expected_text:
            errors.append(
                f"{path}: Markdown projection is not an exact projection of model-spec.json"
            )
        if str(meta.get("baseline_id", "")) not in text:
            errors.append(f"{path}: baseline_id is missing or stale")
        if str(meta.get("model_version", "")) not in text:
            errors.append(f"{path}: model_version is missing or stale")
        for collection in collections:
            for stable_id in sorted(ids[collection]):
                # Rules are projected under the contract-mandated `RULE-`
                # prefix while the canonical spec keeps `R-`; compare against
                # the projected form, not the stored one.
                expected_id = rule_id(stable_id) if collection == "rules" else stable_id
                if expected_id not in text:
                    errors.append(f"{path}: missing required trace ID '{expected_id}'")

    overview = docs_dir / "00-项目概述.md"
    if overview.exists():
        text = overview.read_text(encoding="utf-8")
        for scope_key in ("in_scope", "out_of_scope"):
            for statement in text_list(spec.get("scope", {}).get(scope_key)):
                if statement not in text:
                    errors.append(f"{overview}: missing {scope_key} boundary '{statement}'")


def resolve_manifest_path(raw: str, project_root: Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else project_root / path


def validate_manifest(
    spec: dict,
    manifest_path: Path,
    project_root: Path,
    graph_dir: Path,
    errors: list[str],
) -> None:
    if not manifest_path.exists():
        errors.append(f"{manifest_path}: missing baseline manifest")
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        errors.append(f"{manifest_path}: {exc}")
        return
    meta = spec.get("meta", {})
    if manifest.get("baseline_id") != meta.get("baseline_id"):
        errors.append(f"{manifest_path}: baseline_id drift")
    if manifest.get("model_version") != meta.get("model_version"):
        errors.append(f"{manifest_path}: model_version drift")
    expected_review_paths = {
        resolve_manifest_path(str(path), project_root).resolve()
        for path in meta.get("review_files", [])
    }
    expected_review_paths.update(
        resolve_manifest_path(str(item["file_or_link"]), project_root).resolve()
        for item in spec.get("evidence", [])
        if item.get("file_or_link") and "://" not in str(item.get("file_or_link"))
    )
    actual_review_paths = {
        resolve_manifest_path(str(entry.get("path")), project_root).resolve()
        for entry in manifest.get("review_sources", [])
        if entry.get("path")
    }
    if actual_review_paths != expected_review_paths:
        errors.append(f"{manifest_path}: review/evidence source coverage drift")
    expected_graph_paths = {
        *(path.resolve() for path in (graph_dir / name for name in GRAPH_NAMES)),
        (graph_dir / "queries" / "query-manifest.json").resolve(),
        *(path.resolve() for path in sorted((graph_dir / "queries").glob("*.rq"))),
    }
    actual_graph_paths = {
        resolve_manifest_path(str(entry.get("path")), project_root).resolve()
        for entry in manifest.get("artifacts", [])
        if entry.get("kind") == "requirements-graph" and entry.get("path")
    }
    if actual_graph_paths != expected_graph_paths:
        errors.append(f"{manifest_path}: requirements graph artifact coverage drift")
    entries = [
        manifest.get("source_spec", {}),
        *manifest.get("review_sources", []),
        *manifest.get("artifacts", []),
    ]
    for entry in entries:
        raw_path = entry.get("path")
        expected_hash = entry.get("sha256")
        if not raw_path or not expected_hash:
            errors.append(f"{manifest_path}: malformed hash entry")
            continue
        path = resolve_manifest_path(str(raw_path), project_root)
        if not path.exists():
            errors.append(f"{manifest_path}: hashed file is missing: {path}")
            continue
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            errors.append(f"{path}: SHA-256 drift from baseline manifest")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate unified graph, BPMN/OWL projections, docs/input coverage, and baseline hashes."
    )
    parser.add_argument("--spec", required=True, help="Path to model-spec.json.")
    parser.add_argument("--bpmn-dir", default="models/bpmn", help="BPMN directory.")
    parser.add_argument("--owl", required=True, help="OWL file.")
    parser.add_argument("--graph-dir", required=True, help="Validated requirements graph directory.")
    parser.add_argument("--docs-dir", default="docs/input", help="Generated 00-07 directory.")
    parser.add_argument("--manifest", default="models/baseline-manifest.json", help="Baseline manifest.")
    parser.add_argument("--project-root", default=".", help="Root for manifest relative paths.")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    bpmn_dir = Path(args.bpmn_dir)
    owl_path = Path(args.owl)
    graph_dir = Path(args.graph_dir)
    docs_dir = Path(args.docs_dir)
    spec = load_spec(spec_path)
    errors = validate_spec(spec, require_approved=True)
    validate_bpmn(spec, bpmn_dir, errors)
    validate_owl(spec, owl_path, errors)
    graph_result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parent / "validate_graph_engineering.py"),
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
        ],
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if graph_result.returncode:
        errors.append(
            "requirements graph validation failed: "
            + (graph_result.stderr.strip() or graph_result.stdout.strip())
        )
    validate_docs(
        spec,
        spec_path,
        graph_dir / "requirements-graph.ttl",
        bpmn_dir,
        owl_path,
        docs_dir,
        errors,
    )
    validate_manifest(
        spec,
        Path(args.manifest),
        Path(args.project_root),
        graph_dir,
        errors,
    )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(
        "PASS traceability, canonical RDF graph, SHACL, OWL-RL, SPARQL, "
        "semantic links, scope boundaries, and baseline hashes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
