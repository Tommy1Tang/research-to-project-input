from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from model_spec_lib import joined, load_spec, validate_spec


NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "trace": "urn:research-to-project-input:trace#",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
XSD_TYPES = {
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
CHINESE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
INVALID_IRI_LOCAL = re.compile(r"[^\w.-]+", re.UNICODE)
TRACE_TERMS = {
    "stableId": "稳定标识",
    "baselineId": "基线标识",
    "modelVersion": "模型版本",
    "reviewStatus": "审核状态",
    "processIds": "流程标识",
    "nodeIds": "节点标识",
    "evidenceIds": "证据标识",
    "questionIds": "待确认问题标识",
    "businessName": "技术名称",
    "entityId": "实体标识",
    "fromState": "源状态",
    "toState": "目标状态",
    "trigger": "触发条件",
    "guardRuleIds": "守卫规则标识",
}


def qname(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def trace_tag(stable_name: str) -> str:
    return qname("trace", TRACE_TERMS[stable_name])


def chinese_local_name(value: Any, stable_id: str) -> str:
    local_name = unicodedata.normalize("NFKC", str(value or "")).strip()
    local_name = INVALID_IRI_LOCAL.sub("_", local_name).strip("_.-")
    if not local_name or not CHINESE_PATTERN.search(local_name):
        raise ValueError(
            f"OWL resource '{stable_id}' requires a Chinese business name for its IRI"
        )
    return local_name


def iri(base: str, business_name: Any, stable_id: str) -> str:
    return f"{base}{chinese_local_name(business_name, stable_id)}"


def register_iri(registry: dict[str, str], resource_iri: str, stable_id: str) -> None:
    existing = registry.get(resource_iri)
    if existing and existing != stable_id:
        raise ValueError(
            f"Duplicate Chinese OWL IRI '{resource_iri}' generated for "
            f"'{existing}' and '{stable_id}'"
        )
    registry[resource_iri] = stable_id


def add_literal(parent: ET.Element, tag: str, value: Any, lang: str | None = None) -> None:
    if value in (None, "", []):
        return
    item = ET.SubElement(parent, tag)
    if lang:
        item.set(XML_LANG, lang)
    item.text = joined(value, "|") if isinstance(value, list) else str(value)


def add_trace(parent: ET.Element, meta: dict[str, Any], item: dict[str, Any]) -> None:
    mapping = {
        "baselineId": meta.get("baseline_id"),
        "modelVersion": meta.get("model_version"),
        "processIds": item.get("process_ids"),
        "nodeIds": item.get("node_ids"),
        "evidenceIds": item.get("evidence_ids"),
        "questionIds": item.get("question_ids"),
    }
    for field, value in mapping.items():
        add_literal(parent, trace_tag(field), value)


def add_restriction(
    class_element: ET.Element,
    property_iri: str,
    predicate: str,
    value: int,
) -> None:
    subclass = ET.SubElement(class_element, qname("rdfs", "subClassOf"))
    restriction = ET.SubElement(subclass, qname("owl", "Restriction"))
    ET.SubElement(
        restriction,
        qname("owl", "onProperty"),
        {qname("rdf", "resource"): property_iri},
    )
    cardinality = ET.SubElement(
        restriction,
        qname("owl", predicate),
        {qname("rdf", "datatype"): f"{NS['xsd']}nonNegativeInteger"},
    )
    cardinality.text = str(value)


def relation_cardinality_constraints(cardinality: str, required: bool) -> list[tuple[str, int]]:
    normalized = re.sub(r"\s+", "", cardinality).upper()
    if normalized == "1:1":
        return [("cardinality", 1)] if required else [("maxCardinality", 1)]
    if normalized in {"N:1", "M:1"}:
        result = [("maxCardinality", 1)]
        if required:
            result.insert(0, ("minCardinality", 1))
        return result
    if normalized in {"1:N", "1:M", "N:M", "M:N"}:
        return [("minCardinality", 1)] if required else []
    if normalized in {"0..1", "0:1"}:
        return [("maxCardinality", 1)]
    if normalized in {"1..1"}:
        return [("cardinality", 1)]
    if normalized in {"1..*", "1:N"}:
        return [("minCardinality", 1)]
    return []


def build_owl(spec: dict[str, Any]) -> ET.ElementTree:
    meta = spec.get("meta", {})
    ontology_iri = str(meta.get("ontology_iri", "https://example.com/ontology/project#"))
    base = ontology_iri if ontology_iri.endswith(("#", "/")) else f"{ontology_iri}#"
    entity_names = {
        str(entity["entity_id"]): str(entity["name"])
        for entity in spec.get("entities", [])
    }
    iri_registry: dict[str, str] = {}
    entity_iris: dict[str, str] = {}
    for entity_id, entity_name in entity_names.items():
        entity_iri = iri(base, entity_name, entity_id)
        register_iri(iri_registry, entity_iri, entity_id)
        entity_iris[entity_id] = entity_iri

    relation_iris: dict[str, str] = {}
    for relation in spec.get("relations", []):
        relation_id = str(relation["relation_id"])
        source_name = entity_names[str(relation["source_entity_id"])]
        target_name = entity_names[str(relation["target_entity_id"])]
        relation_name = f"{source_name}_{relation['name_cn']}_{target_name}"
        relation_iri = iri(base, relation_name, relation_id)
        register_iri(iri_registry, relation_iri, relation_id)
        relation_iris[relation_id] = relation_iri

    field_iris: dict[str, str] = {}
    for entity in spec.get("entities", []):
        entity_id = str(entity["entity_id"])
        for attribute in entity.get("attributes", []):
            field_id = str(
                attribute.get("field_id")
                or f"{entity_id}__{attribute.get('name', 'field')}"
            )
            field_name = f"{entity_names[entity_id]}_{attribute.get('label', '')}"
            field_iri = iri(base, field_name, field_id)
            register_iri(iri_registry, field_iri, field_id)
            field_iris[field_id] = field_iri

    state_labels: dict[str, str] = {}
    state_iris: dict[str, str] = {}
    for state in spec.get("states", []):
        state_id = str(state["state_id"])
        state_label = (
            f"{entity_names[str(state['entity_id'])]}："
            f"{state.get('from_state')}转为{state.get('to_state')}："
            f"{state.get('trigger')}"
        )
        state_iri = iri(base, state_label, state_id)
        register_iri(iri_registry, state_iri, state_id)
        state_labels[state_id] = state_label
        state_iris[state_id] = state_iri

    root = ET.Element(qname("rdf", "RDF"))
    ontology = ET.SubElement(
        root,
        qname("owl", "Ontology"),
        {qname("rdf", "about"): ontology_iri.rstrip("#")},
    )
    ontology_label = f"{meta.get('project_name', '')}{meta.get('phase', '')}领域本体"
    add_literal(ontology, qname("rdfs", "label"), ontology_label, "zh-CN")
    add_literal(ontology, qname("owl", "versionInfo"), meta.get("model_version"))
    add_literal(ontology, trace_tag("baselineId"), meta.get("baseline_id"))
    add_literal(ontology, trace_tag("reviewStatus"), meta.get("review_status"))

    standard_term_labels = {
        f"{NS['rdf']}type": "类型",
        f"{NS['rdfs']}subClassOf": "子类关系",
        f"{NS['rdfs']}domain": "定义域",
        f"{NS['rdfs']}range": "值域",
        f"{NS['rdfs']}label": "显示名称",
    }
    for standard_iri, chinese_label in standard_term_labels.items():
        description = ET.SubElement(
            root,
            qname("rdf", "Description"),
            {qname("rdf", "about"): standard_iri},
        )
        add_literal(description, qname("rdfs", "label"), chinese_label, "zh-CN")

    for annotation_name, chinese_label in TRACE_TERMS.items():
        annotation = ET.SubElement(
            root,
            qname("owl", "AnnotationProperty"),
            {qname("rdf", "about"): f"{NS['trace']}{chinese_label}"},
        )
        add_literal(annotation, qname("rdfs", "label"), chinese_label, "zh-CN")
        add_literal(annotation, trace_tag("stableId"), annotation_name)

    state_transition_class = ET.SubElement(
        root,
        qname("owl", "Class"),
        {qname("rdf", "about"): f"{NS['trace']}状态迁移"},
    )
    add_literal(state_transition_class, qname("rdfs", "label"), "状态迁移", "zh-CN")
    add_literal(state_transition_class, trace_tag("stableId"), "StateTransition")

    class_elements: dict[str, ET.Element] = {}
    for entity in spec.get("entities", []):
        entity_id = str(entity["entity_id"])
        cls = ET.SubElement(
            root,
            qname("owl", "Class"),
            {qname("rdf", "about"): entity_iris[entity_id]},
        )
        class_elements[entity_id] = cls
        add_literal(cls, qname("rdfs", "label"), entity.get("name"), "zh-CN")
        add_literal(cls, trace_tag("stableId"), entity_id)
        add_literal(cls, trace_tag("businessName"), entity.get("class_name"))
        add_literal(cls, qname("rdfs", "comment"), entity.get("definition"), "zh-CN")
        for synonym in entity.get("synonyms", []):
            add_literal(cls, qname("skos", "altLabel"), synonym, "zh-CN")
        parent = entity.get("parent_entity_id")
        if parent and parent != "Thing":
            ET.SubElement(
                cls,
                qname("rdfs", "subClassOf"),
                {qname("rdf", "resource"): entity_iris[str(parent)]},
            )
        add_trace(cls, meta, entity)

    for relation in spec.get("relations", []):
        relation_id = str(relation["relation_id"])
        prop_iri = relation_iris[relation_id]
        prop = ET.SubElement(
            root,
            qname("owl", "ObjectProperty"),
            {qname("rdf", "about"): prop_iri},
        )
        add_literal(prop, qname("rdfs", "label"), relation.get("name_cn"), "zh-CN")
        add_literal(prop, trace_tag("stableId"), relation_id)
        add_literal(prop, trace_tag("businessName"), relation.get("name_en"))
        add_literal(prop, qname("rdfs", "comment"), relation.get("description"), "zh-CN")
        ET.SubElement(
            prop,
            qname("rdfs", "domain"),
            {qname("rdf", "resource"): entity_iris[str(relation["source_entity_id"])]},
        )
        ET.SubElement(
            prop,
            qname("rdfs", "range"),
            {qname("rdf", "resource"): entity_iris[str(relation["target_entity_id"])]},
        )
        add_trace(prop, meta, relation)
        source_class = class_elements[str(relation["source_entity_id"])]
        for predicate, value in relation_cardinality_constraints(
            str(relation.get("cardinality", "")),
            bool(relation.get("required", False)),
        ):
            add_restriction(source_class, prop_iri, predicate, value)

    property_ids: set[str] = set()
    for entity in spec.get("entities", []):
        entity_id = str(entity["entity_id"])
        for attribute in entity.get("attributes", []):
            field_id = str(attribute.get("field_id") or f"{entity_id}__{attribute.get('name', 'field')}")
            if field_id in property_ids:
                raise ValueError(f"Duplicate datatype property ID: {field_id}")
            property_ids.add(field_id)
            prop_iri = field_iris[field_id]
            prop = ET.SubElement(
                root,
                qname("owl", "DatatypeProperty"),
                {qname("rdf", "about"): prop_iri},
            )
            add_literal(prop, qname("rdfs", "label"), attribute.get("label"), "zh-CN")
            add_literal(prop, trace_tag("stableId"), field_id)
            add_literal(prop, qname("rdfs", "comment"), attribute.get("description"), "zh-CN")
            ET.SubElement(
                prop,
                qname("rdfs", "domain"),
                {qname("rdf", "resource"): entity_iris[entity_id]},
            )
            datatype = XSD_TYPES.get(str(attribute.get("datatype", "string")), "string")
            ET.SubElement(
                prop,
                qname("rdfs", "range"),
                {qname("rdf", "resource"): f"{NS['xsd']}{datatype}"},
            )
            add_trace(prop, meta, attribute)
            if attribute.get("required"):
                add_restriction(class_elements[entity_id], prop_iri, "minCardinality", 1)

    for state in spec.get("states", []):
        state_id = str(state["state_id"])
        individual = ET.SubElement(
            root,
            qname("owl", "NamedIndividual"),
            {qname("rdf", "about"): state_iris[state_id]},
        )
        ET.SubElement(
            individual,
            qname("rdf", "type"),
            {qname("rdf", "resource"): f"{NS['trace']}状态迁移"},
        )
        add_literal(individual, qname("rdfs", "label"), state_labels[state_id], "zh-CN")
        add_literal(individual, trace_tag("stableId"), state_id)
        add_literal(individual, trace_tag("entityId"), state.get("entity_id"))
        add_literal(individual, trace_tag("fromState"), state.get("from_state"))
        add_literal(individual, trace_tag("toState"), state.get("to_state"))
        add_literal(individual, trace_tag("trigger"), state.get("trigger"))
        add_literal(individual, trace_tag("nodeIds"), state.get("node_id"))
        add_literal(individual, trace_tag("guardRuleIds"), state.get("guard_rule_ids"))
        add_trace(individual, meta, state)

    return ET.ElementTree(root)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an OWL/RDF XML projection from canonical model-spec.json."
    )
    parser.add_argument("--spec", required=True, help="Path to model-spec.json.")
    parser.add_argument("--output", help="Output .owl path.")
    args = parser.parse_args()

    spec = load_spec(Path(args.spec))
    errors = validate_spec(spec, require_reviewed=True)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    meta = spec.get("meta", {})
    output = Path(args.output or f"models/ontology/{meta.get('ontology_id', 'ontology')}.owl")
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        tree = build_owl(spec)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    ET.indent(tree, space="  ")
    tree.write(output, encoding="utf-8", xml_declaration=True)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
