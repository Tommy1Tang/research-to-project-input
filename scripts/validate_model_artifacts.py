from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


CHINESE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
BPMN_NAMED_TAGS = {
    "process",
    "participant",
    "lane",
    "startEvent",
    "endEvent",
    "userTask",
    "manualTask",
    "serviceTask",
    "scriptTask",
    "businessRuleTask",
    "receiveTask",
    "sendTask",
    "exclusiveGateway",
    "inclusiveGateway",
    "parallelGateway",
    "intermediateCatchEvent",
    "intermediateThrowEvent",
    "boundaryEvent",
    "subProcess",
    "sequenceFlow",
    "messageFlow",
}


def has_chinese(value: str | None) -> bool:
    return bool(value and CHINESE_PATTERN.search(value))


def validate_xml(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        return [f"{path}: XML parse error: {exc}"]

    ids: set[str] = set()
    duplicates: set[str] = set()
    for elem in tree.iter():
        elem_id = elem.attrib.get("id")
        if not elem_id:
            continue
        if elem_id in ids:
            duplicates.add(elem_id)
        ids.add(elem_id)
    for elem_id in sorted(duplicates):
        errors.append(f"{path}: duplicate id: {elem_id}")

    if path.suffix.lower() == ".bpmn":
        namespace = {
            "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
            "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
            "camunda": "http://camunda.org/schema/1.0/bpmn",
        }
        root = tree.getroot()
        for element in root.iter():
            if not element.tag.startswith(f"{{{namespace['bpmn']}}}"):
                continue
            local_name = element.tag.rsplit("}", 1)[-1]
            if local_name not in BPMN_NAMED_TAGS:
                continue
            business_name = element.attrib.get("name")
            if not has_chinese(business_name):
                errors.append(
                    f"{path}: BPMN {local_name} '{element.attrib.get('id', '<?>')}' "
                    "must have a Chinese business name"
                )
        expected_shapes = {
            str(element.attrib["id"])
            for element in root.iter()
            if element.attrib.get("id")
            and element.tag.startswith(f"{{{namespace['bpmn']}}}")
            and element.tag.rsplit("}", 1)[-1]
            in BPMN_NAMED_TAGS - {"process", "sequenceFlow", "messageFlow"}
        }
        actual_shapes = {
            str(element.attrib["bpmnElement"])
            for element in root.findall(".//bpmndi:BPMNShape", namespace)
            if element.attrib.get("bpmnElement")
        }
        if actual_shapes != expected_shapes:
            errors.append(
                f"{path}: BPMN DI shape coverage drift; "
                f"missing={sorted(expected_shapes - actual_shapes)} "
                f"extra={sorted(actual_shapes - expected_shapes)}"
            )
        expected_edges = {
            str(element.attrib["id"])
            for element in root.iter()
            if element.attrib.get("id")
            and element.tag.rsplit("}", 1)[-1] in {"sequenceFlow", "messageFlow"}
            and element.tag.startswith(f"{{{namespace['bpmn']}}}")
        }
        actual_edges = {
            str(element.attrib["bpmnElement"])
            for element in root.findall(".//bpmndi:BPMNEdge", namespace)
            if element.attrib.get("bpmnElement")
        }
        if actual_edges != expected_edges:
            errors.append(
                f"{path}: BPMN DI edge coverage drift; "
                f"missing={sorted(expected_edges - actual_edges)} "
                f"extra={sorted(actual_edges - expected_edges)}"
            )
        if not root.findall(".//camunda:properties/camunda:property", namespace):
            errors.append(f"{path}: Camunda extension properties are missing")
        for process in root.findall(".//bpmn:process", namespace):
            process_id = process.attrib.get("id", "process<?>")
            if not process.findall(".//bpmn:startEvent", namespace):
                errors.append(f"{path}: {process_id} has no startEvent")
            if not process.findall(".//bpmn:endEvent", namespace):
                errors.append(f"{path}: {process_id} has no endEvent")
        for flow in root.findall(".//bpmn:sequenceFlow", namespace):
            source = flow.attrib.get("sourceRef")
            target = flow.attrib.get("targetRef")
            if source not in ids or target not in ids:
                errors.append(
                    f"{path}: sequenceFlow {flow.attrib.get('id')} has a missing sourceRef/targetRef"
                )
    if path.suffix.lower() == ".owl":
        namespace = {
            "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
            "owl": "http://www.w3.org/2002/07/owl#",
            "trace": "urn:research-to-project-input:trace#",
        }
        root = tree.getroot()
        rdf_about = f"{{{namespace['rdf']}}}about"
        is_generated_business_owl = any(
            element.attrib.get(rdf_about, "").startswith(namespace["trace"])
            for element in root.findall(".//owl:AnnotationProperty", namespace)
        )
        stable_ids: dict[str, str] = {}
        for element_type in (
            "Ontology",
            "Class",
            "ObjectProperty",
            "DatatypeProperty",
            "AnnotationProperty",
            "NamedIndividual",
        ):
            for element in root.findall(f".//owl:{element_type}", namespace):
                resource_id = element.attrib.get(f"{{{namespace['rdf']}}}about", "<?>")
                labels = element.findall("rdfs:label", namespace)
                valid_label = any(
                    label.attrib.get(XML_LANG) == "zh-CN" and has_chinese(label.text)
                    for label in labels
                )
                if not valid_label:
                    errors.append(
                        f"{path}: OWL {element_type} '{resource_id}' "
                        "must have an rdfs:label with xml:lang='zh-CN'"
                    )
                if not is_generated_business_owl or element_type not in {
                    "Class",
                    "ObjectProperty",
                    "DatatypeProperty",
                    "AnnotationProperty",
                    "NamedIndividual",
                }:
                    continue
                iri_local_name = resource_id.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
                if not has_chinese(iri_local_name):
                    errors.append(
                        f"{path}: OWL {element_type} '{resource_id}' "
                        "must use a Chinese IRI local name"
                    )
                stable_id_elements = element.findall("trace:稳定标识", namespace)
                stable_id = (
                    (stable_id_elements[0].text or "").strip()
                    if len(stable_id_elements) == 1
                    else ""
                )
                if len(stable_id_elements) != 1 or not stable_id:
                    errors.append(
                        f"{path}: OWL {element_type} '{resource_id}' "
                        "must have exactly one non-empty trace:稳定标识"
                    )
                    continue
                existing_resource = stable_ids.get(stable_id)
                if existing_resource and existing_resource != resource_id:
                    errors.append(
                        f"{path}: duplicate trace:稳定标识 '{stable_id}' on "
                        f"'{existing_resource}' and '{resource_id}'"
                    )
                stable_ids[stable_id] = resource_id
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BPMN/OWL XML syntax and duplicate IDs.")
    parser.add_argument("paths", nargs="+", help="Model files or directories to validate.")
    args = parser.parse_args()

    files: list[Path] = []
    for item in args.paths:
        path = Path(item)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.bpmn")))
            files.extend(sorted(path.rglob("*.owl")))
        else:
            files.append(path)

    errors: list[str] = []
    for path in files:
        if not path.exists():
            errors.append(f"{path}: file not found")
            continue
        errors.extend(validate_xml(path))

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    for path in files:
        print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
