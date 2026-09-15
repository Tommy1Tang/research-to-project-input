from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


BPMN_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}
OWL_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "pipe": "https://openai.example/requirements-pipeline#",
}
RDF_ABOUT = f"{{{OWL_NS['rdf']}}}about"
RDF_RESOURCE = f"{{{OWL_NS['rdf']}}}resource"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
CHINESE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fragment(value: str | None) -> str:
    return (value or "").rsplit("#", 1)[-1]


def validate_chinese_label(
    element: ET.Element,
    label: str,
    errors: list[str],
) -> None:
    labels = element.findall("rdfs:label", OWL_NS)
    if not any(
        item.get(XML_LANG) == "zh-CN"
        and CHINESE_PATTERN.search((item.text or "").strip())
        for item in labels
    ):
        errors.append(f"pipeline OWL {label} requires a Chinese rdfs:label with xml:lang='zh-CN'")


def camunda_property_values(tree: ET.ElementTree, name: str) -> list[str]:
    return [
        str(element.get("value", "")).strip()
        for element in tree.findall(f".//camunda:property[@name='{name}']", BPMN_NS)
    ]


def control_stable_id(element: ET.Element) -> str:
    node = element.find("pipe:稳定标识", OWL_NS)
    return (node.text or "").strip() if node is not None else ""


def main() -> int:
    skill = Path(__file__).resolve().parent.parent
    definition_path = skill / "references" / "pipeline-definition.json"
    bpmn_path = skill / "references" / "pipeline-process.bpmn"
    owl_path = skill / "references" / "pipeline-ontology.owl"
    state_template_path = skill / "assets" / "pipeline-state.template.json"
    errors: list[str] = []

    try:
        definition = load_json(definition_path)
        state_template = load_json(state_template_path)
        bpmn = ET.parse(bpmn_path)
        owl = ET.parse(owl_path)
    except (OSError, json.JSONDecodeError, ET.ParseError) as exc:
        print(f"Control contract parse failure: {exc}", file=sys.stderr)
        return 1

    stages = sorted(definition.get("stages", []), key=lambda item: item.get("index", -1))
    stage_ids = [str(item.get("id", "")) for item in stages]
    if not stages or stage_ids[0] != "initialized" or stage_ids[-1] != "development_ready":
        errors.append("pipeline definition must start at initialized and end at development_ready")
    indexes = [item.get("index") for item in stages]
    if indexes != list(range(len(stages))):
        errors.append("pipeline stage indexes must be contiguous from zero")
    if len(stage_ids) != len(set(stage_ids)):
        errors.append("pipeline definition contains duplicate stage IDs")

    transitions = definition.get("transitions", [])
    transition_actions = {str(item.get("action", "")) for item in transitions}
    expected_pairs = set(zip(stage_ids, stage_ids[1:]))
    actual_pairs = {
        (str(item.get("from", "")), str(item.get("to", ""))) for item in transitions
    }
    if actual_pairs != expected_pairs:
        errors.append("pipeline transitions do not exactly connect adjacent stage definitions")

    ontology = owl.find(".//owl:Ontology", OWL_NS)
    if ontology is None:
        errors.append("pipeline OWL must define owl:Ontology")
    else:
        validate_chinese_label(ontology, "ontology", errors)
        version = ontology.find("owl:versionInfo", OWL_NS)
        if version is None or (version.text or "").strip() != str(definition.get("version", "")):
            errors.append("pipeline OWL versionInfo drift")

    for element_type in ("Class", "ObjectProperty", "DatatypeProperty"):
        for element in owl.findall(f".//owl:{element_type}", OWL_NS):
            validate_chinese_label(
                element,
                f"{element_type} {fragment(element.get(RDF_ABOUT))}",
                errors,
            )
    expected_class_ids = {
        "流水线阶段",
        "流水线动作",
        "流水线产物",
        "人工审批门禁",
        "人工审批",
        "校验结果",
    }
    actual_class_ids = {
        fragment(element.get(RDF_ABOUT))
        for element in owl.findall(".//owl:Class", OWL_NS)
    }
    if actual_class_ids != expected_class_ids:
        errors.append(
            "pipeline OWL Chinese class IRI drift: "
            f"missing={sorted(expected_class_ids - actual_class_ids)}, "
            f"extra={sorted(actual_class_ids - expected_class_ids)}"
        )
    expected_property_iris = {
        "nextStage": "下一阶段",
        "enteredBy": "由动作进入",
        "requiresArtifact": "需要产物",
        "producesArtifact": "产生产物",
        "requiresApproval": "需要人工审批",
        "stageIndex": "阶段序号",
        "stableId": "稳定标识",
    }
    actual_property_iris: dict[str, str] = {}
    for element_type in ("ObjectProperty", "DatatypeProperty"):
        for element in owl.findall(f".//owl:{element_type}", OWL_NS):
            property_iri = fragment(element.get(RDF_ABOUT))
            stable_id = control_stable_id(element)
            if not CHINESE_PATTERN.search(property_iri):
                errors.append(
                    f"pipeline OWL {element_type} IRI must be Chinese: {property_iri!r}"
                )
            if not stable_id:
                errors.append(
                    f"pipeline OWL {element_type} {property_iri!r} "
                    "requires pipe:稳定标识"
                )
                continue
            if stable_id in actual_property_iris:
                errors.append(f"pipeline OWL duplicate property stableId {stable_id!r}")
            actual_property_iris[stable_id] = property_iri
    if actual_property_iris != expected_property_iris:
        errors.append(
            "pipeline OWL Chinese property IRI drift: "
            f"expected={expected_property_iris}, actual={actual_property_iris}"
        )
    allowed_pipe_terms = {
        *expected_class_ids,
        *expected_property_iris.values(),
    }
    for element in owl.getroot().iter():
        if not element.tag.startswith(f"{{{OWL_NS['pipe']}}}"):
            continue
        local_name = element.tag.rsplit("}", 1)[-1]
        if local_name not in allowed_pipe_terms:
            errors.append(
                f"pipeline OWL contains undeclared or non-Chinese custom arc/type "
                f"{local_name!r}"
            )
    resource_stable_ids: dict[str, str] = {}
    for element_type in (
        "流水线产物",
        "流水线动作",
        "流水线阶段",
        "人工审批门禁",
        "人工审批",
    ):
        for element in owl.findall(f".//pipe:{element_type}", OWL_NS):
            resource_iri = str(element.get(RDF_ABOUT, ""))
            resource_fragment = fragment(resource_iri)
            stable_id = control_stable_id(element)
            validate_chinese_label(
                element,
                f"{element_type} {resource_fragment}",
                errors,
            )
            if not CHINESE_PATTERN.search(resource_fragment):
                errors.append(
                    f"pipeline OWL {element_type} instance IRI must be Chinese: "
                    f"{resource_fragment!r}"
                )
            if not stable_id:
                errors.append(
                    f"pipeline OWL {element_type} {resource_fragment} "
                    "requires pipe:稳定标识"
                )
            elif stable_id in resource_stable_ids.values():
                errors.append(f"pipeline OWL duplicate stableId {stable_id!r}")
            resource_stable_ids[resource_iri] = stable_id

    bpmn_actions = set(camunda_property_values(bpmn, "执行动作"))
    if bpmn_actions != transition_actions:
        errors.append(
            "pipeline BPMN runner actions drift: "
            f"missing={sorted(transition_actions - bpmn_actions)}, "
            f"extra={sorted(bpmn_actions - transition_actions)}"
        )
    for stage_id in [
        *camunda_property_values(bpmn, "来源阶段"),
        *camunda_property_values(bpmn, "目标阶段"),
    ]:
        if stage_id not in set(stage_ids):
            errors.append(f"pipeline BPMN references unknown stage {stage_id!r}")

    named_bpmn_paths = (
        ".//bpmn:process",
        ".//bpmn:startEvent",
        ".//bpmn:endEvent",
        ".//bpmn:task",
        ".//bpmn:userTask",
        ".//bpmn:serviceTask",
        ".//bpmn:exclusiveGateway",
        ".//bpmn:sequenceFlow",
    )
    for path in named_bpmn_paths:
        for element in bpmn.findall(path, BPMN_NS):
            business_name = str(element.get("name", "")).strip()
            if not CHINESE_PATTERN.search(business_name):
                errors.append(
                    f"pipeline BPMN element {element.get('id', '<?>')} "
                    "requires a Chinese business name"
                )

    flow_nodes = {
        str(element.get("id"))
        for path in named_bpmn_paths[1:-1]
        for element in bpmn.findall(path, BPMN_NS)
        if element.get("id")
    }
    sequence_flows = {
        str(element.get("id"))
        for element in bpmn.findall(".//bpmn:sequenceFlow", BPMN_NS)
        if element.get("id")
    }
    diagram_shapes = {
        str(element.get("bpmnElement"))
        for element in bpmn.findall(".//bpmndi:BPMNShape", BPMN_NS)
        if element.get("bpmnElement")
    }
    diagram_edges = {
        str(element.get("bpmnElement"))
        for element in bpmn.findall(".//bpmndi:BPMNEdge", BPMN_NS)
        if element.get("bpmnElement")
    }
    if diagram_shapes != flow_nodes:
        errors.append(
            "pipeline BPMN diagram shape coverage drift: "
            f"missing={sorted(flow_nodes - diagram_shapes)}, "
            f"extra={sorted(diagram_shapes - flow_nodes)}"
        )
    if diagram_edges != sequence_flows:
        errors.append(
            "pipeline BPMN diagram edge coverage drift: "
            f"missing={sorted(sequence_flows - diagram_edges)}, "
            f"extra={sorted(diagram_edges - sequence_flows)}"
        )

    ontology_stages: dict[str, ET.Element] = {}
    for element in owl.findall(".//pipe:流水线阶段", OWL_NS):
        ontology_stages[control_stable_id(element)] = element
    if set(ontology_stages) != set(stage_ids):
        errors.append(
            "pipeline OWL stage drift: "
            f"missing={sorted(set(stage_ids) - set(ontology_stages))}, "
            f"extra={sorted(set(ontology_stages) - set(stage_ids))}"
        )
    for stage in stages:
        stage_id = str(stage["id"])
        element = ontology_stages.get(stage_id)
        if element is None:
            continue
        index_node = element.find("pipe:阶段序号", OWL_NS)
        if index_node is None or (index_node.text or "").strip() != str(stage["index"]):
            errors.append(f"pipeline OWL stageIndex drift for {stage_id}")
        next_node = element.find("pipe:下一阶段", OWL_NS)
        expected_next = str(stage.get("next_action")) != "validate"
        if expected_next:
            expected_stage = stage_ids[int(stage["index"]) + 1]
            actual_stage = (
                resource_stable_ids.get(str(next_node.get(RDF_RESOURCE)), "")
                if next_node is not None
                else ""
            )
            if actual_stage != expected_stage:
                errors.append(f"pipeline OWL nextStage drift for {stage_id}")
        elif next_node is not None:
            errors.append("terminal pipeline OWL stage must not have nextStage")
        if int(stage["index"]) > 0:
            transition = next(
                item for item in transitions if str(item.get("to")) == stage_id
            )
            entered_by = element.find("pipe:由动作进入", OWL_NS)
            actual_action = (
                resource_stable_ids.get(str(entered_by.get(RDF_RESOURCE)), "")
                if entered_by is not None
                else ""
            )
            if actual_action != str(transition.get("action", "")):
                errors.append(f"pipeline OWL enteredBy drift for {stage_id}")

    ontology_actions = {
        control_stable_id(element)
        for element in [
            *owl.findall(".//pipe:流水线动作", OWL_NS),
            *owl.findall(".//pipe:人工审批门禁", OWL_NS),
        ]
    }
    if ontology_actions != transition_actions:
        errors.append(
            "pipeline OWL action drift: "
            f"missing={sorted(transition_actions - ontology_actions)}, "
            f"extra={sorted(ontology_actions - transition_actions)}"
        )

    if state_template.get("current_stage") != "initialized":
        errors.append("pipeline state template must begin at initialized")
    if state_template.get("pipeline_id") != definition.get("pipeline_id"):
        errors.append("pipeline state template pipeline_id drift")
    required_groups = {
        "modeling_review",
        "model_spec",
        "requirements_graph",
        "graph_contracts",
        "graph_validation",
        "bpmn",
        "owl",
        "development_input",
        "baseline_manifest",
    }
    actual_groups = set(state_template.get("artifacts", {}))
    if actual_groups != required_groups:
        errors.append("pipeline state template artifact groups drift")

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("PASS pipeline definition, BPMN process, OWL semantics, and state template are aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
