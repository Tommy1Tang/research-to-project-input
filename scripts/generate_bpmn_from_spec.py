from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from model_spec_lib import joined, load_spec, text_list, validate_spec


NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
}

for prefix, uri in NS.items():
    ET.register_namespace(prefix, uri)


TYPE_MAP = {
    "startEvent": "startEvent",
    "endEvent": "endEvent",
    "userTask": "userTask",
    "manualTask": "manualTask",
    "serviceTask": "serviceTask",
    "scriptTask": "scriptTask",
    "businessRuleTask": "businessRuleTask",
    "receiveTask": "receiveTask",
    "sendTask": "sendTask",
    "exclusiveGateway": "exclusiveGateway",
    "inclusiveGateway": "inclusiveGateway",
    "parallelGateway": "parallelGateway",
    "intermediateCatchEvent": "intermediateCatchEvent",
    "intermediateThrowEvent": "intermediateThrowEvent",
    "boundaryErrorEvent": "boundaryEvent",
    "subProcess": "subProcess",
}

ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
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


def qname(prefix: str, tag: str) -> str:
    return f"{{{NS[prefix]}}}{tag}"


def xml_id(value: Any, label: str) -> str:
    result = str(value or "")
    if not ID_PATTERN.fullmatch(result):
        raise ValueError(
            f"{label} '{result}' is not a valid stable XML ID. "
            "Use ASCII letters, digits, underscore, dot, or hyphen and do not start with a digit."
        )
    return result


def add_bounds(parent: ET.Element, x: int, y: int, width: int, height: int) -> None:
    ET.SubElement(
        parent,
        qname("dc", "Bounds"),
        {"x": str(x), "y": str(y), "width": str(width), "height": str(height)},
    )


def add_trace(parent: ET.Element, meta: dict[str, Any], **values: Any) -> None:
    extension = ET.SubElement(parent, qname("bpmn", "extensionElements"))
    properties = ET.SubElement(extension, qname("camunda", "properties"))
    trace_values = {
        "baselineId": str(meta.get("baseline_id", "")),
        "modelVersion": str(meta.get("model_version", "")),
    }
    for key, value in values.items():
        if value in (None, "", []):
            continue
        trace_values[key] = joined(value, "|")
    for key, value in trace_values.items():
        ET.SubElement(
            properties,
            qname("camunda", "property"),
            {
                "name": TRACE_PROPERTY_NAMES[key],
                "value": str(value),
            },
        )


def node_dimensions(node_type: str) -> tuple[int, int]:
    if node_type in {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent"}:
        return (36, 36)
    if node_type == "boundaryErrorEvent":
        return (30, 30)
    if "Gateway" in node_type:
        return (50, 50)
    if node_type == "subProcess":
        return (150, 100)
    return (120, 80)


def build_bpmn(spec: dict[str, Any], process_spec: dict[str, Any]) -> ET.ElementTree:
    meta = spec.get("meta", {})
    process_id = xml_id(process_spec.get("process_id"), "process_id")
    process_name = str(process_spec.get("name", process_id))
    nodes = process_spec.get("nodes", [])
    flows = process_spec.get("flows", [])
    participants = process_spec.get("participants", [])

    definitions = ET.Element(
        qname("bpmn", "definitions"),
        {
            "id": f"Definitions_{process_id}",
            "targetNamespace": str(meta.get("ontology_iri", "urn:research-to-project-input:bpmn")),
            "exporter": "research-to-project-input",
            "exporterVersion": "2.0.0",
        },
    )
    process = ET.SubElement(
        definitions,
        qname("bpmn", "process"),
        {"id": process_id, "name": process_name, "isExecutable": "false"},
    )
    add_trace(
        process,
        meta,
        processId=process_id,
        scenarioIds=process_spec.get("scenario_ids"),
        evidenceIds=process_spec.get("evidence_ids"),
        questionIds=process_spec.get("question_ids"),
    )

    primary_participant = next(
        (item for item in participants if item.get("process_ref") is True),
        participants[0] if participants else None,
    )
    primary_participant_id = (
        xml_id(primary_participant.get("participant_id"), "participant_id")
        if primary_participant
        else f"PARTICIPANT_{process_id}"
    )

    collaboration = ET.SubElement(
        definitions,
        qname("bpmn", "collaboration"),
        {"id": f"COLLAB_{process_id}"},
    )
    participant_elements: dict[str, ET.Element] = {}
    participant_specs = participants or [
        {
            "participant_id": primary_participant_id,
            "name": process_name,
            "process_ref": True,
            "lanes": [],
        }
    ]
    for participant_spec in participant_specs:
        participant_id = xml_id(participant_spec.get("participant_id"), "participant_id")
        attrs = {
            "id": participant_id,
            "name": str(participant_spec.get("name", participant_id)),
        }
        if participant_id == primary_participant_id or participant_spec.get("process_ref") is True:
            attrs["processRef"] = process_id
        participant = ET.SubElement(collaboration, qname("bpmn", "participant"), attrs)
        participant_elements[participant_id] = participant
        add_trace(
            participant,
            meta,
            processId=process_id,
            roleIds=participant_spec.get("role_ids"),
            evidenceIds=participant_spec.get("evidence_ids"),
        )

    lanes = primary_participant.get("lanes", []) if primary_participant else []
    lane_elements: dict[str, ET.Element] = {}
    lane_node_ids: dict[str, list[str]] = {}
    if lanes:
        lane_set = ET.SubElement(process, qname("bpmn", "laneSet"), {"id": f"LANESET_{process_id}"})
        for lane_spec in lanes:
            lane_id = xml_id(lane_spec.get("lane_id"), "lane_id")
            lane = ET.SubElement(
                lane_set,
                qname("bpmn", "lane"),
                {"id": lane_id, "name": str(lane_spec.get("name", lane_id))},
            )
            lane_elements[lane_id] = lane
            lane_node_ids[lane_id] = []
            add_trace(
                lane,
                meta,
                processId=process_id,
                roleIds=lane_spec.get("role_id"),
                evidenceIds=lane_spec.get("evidence_ids"),
            )

    node_elements: dict[str, ET.Element] = {}
    node_specs: dict[str, dict[str, Any]] = {}
    for node_spec in nodes:
        node_id = xml_id(node_spec.get("node_id"), "node_id")
        node_type = str(node_spec.get("type", "userTask"))
        bpmn_tag = TYPE_MAP.get(node_type)
        if not bpmn_tag:
            raise ValueError(f"Unsupported BPMN node type: {node_type}")
        attrs = {"id": node_id, "name": str(node_spec.get("name", node_id))}
        if node_type == "boundaryErrorEvent":
            attrs["attachedToRef"] = xml_id(node_spec.get("attached_to"), "attached_to")
            attrs["cancelActivity"] = "true" if node_spec.get("cancel_activity", True) else "false"
        node = ET.SubElement(process, qname("bpmn", bpmn_tag), attrs)
        if node_type == "boundaryErrorEvent":
            ET.SubElement(node, qname("bpmn", "errorEventDefinition"))
        elif node_type in {"intermediateCatchEvent", "intermediateThrowEvent"} and node_spec.get("event") == "message":
            ET.SubElement(node, qname("bpmn", "messageEventDefinition"))
        add_trace(
            node,
            meta,
            processId=process_id,
            nodeId=node_id,
            roleIds=node_spec.get("actor_role_id"),
            capabilityIds=node_spec.get("capability_ids"),
            entityIds=node_spec.get("entity_ids"),
            ruleIds=node_spec.get("rule_ids"),
            stateIds=node_spec.get("state_ids"),
            interfaceIds=node_spec.get("interface_ids"),
            exceptionIds=node_spec.get("exception_ids"),
            evidenceIds=node_spec.get("evidence_ids"),
            questionIds=node_spec.get("question_ids"),
        )
        node_elements[node_id] = node
        node_specs[node_id] = node_spec
        lane_id = node_spec.get("lane_id")
        if lane_id in lane_node_ids:
            lane_node_ids[lane_id].append(node_id)

    for lane_id, node_ids in lane_node_ids.items():
        for node_id in node_ids:
            ref = ET.SubElement(lane_elements[lane_id], qname("bpmn", "flowNodeRef"))
            ref.text = node_id

    for flow_spec in flows:
        flow_id = xml_id(flow_spec.get("flow_id"), "flow_id")
        source = xml_id(flow_spec.get("source"), "flow source")
        target = xml_id(flow_spec.get("target"), "flow target")
        if source not in node_elements or target not in node_elements:
            raise ValueError(f"Flow {flow_id} references missing source or target: {source} -> {target}")
        attrs = {"id": flow_id, "sourceRef": source, "targetRef": target}
        if flow_spec.get("name"):
            attrs["name"] = str(flow_spec["name"])
        flow = ET.SubElement(process, qname("bpmn", "sequenceFlow"), attrs)
        add_trace(
            flow,
            meta,
            processId=process_id,
            ruleIds=flow_spec.get("rule_ids"),
            exceptionIds=flow_spec.get("exception_ids"),
            evidenceIds=flow_spec.get("evidence_ids"),
            questionIds=flow_spec.get("question_ids"),
        )
        condition = flow_spec.get("condition")
        if condition:
            expression = ET.SubElement(
                flow,
                qname("bpmn", "conditionExpression"),
                {qname("xsi", "type"): "bpmn:tFormalExpression"},
            )
            expression.text = str(condition)
        outgoing = ET.SubElement(node_elements[source], qname("bpmn", "outgoing"))
        outgoing.text = flow_id
        incoming = ET.SubElement(node_elements[target], qname("bpmn", "incoming"))
        incoming.text = flow_id

    message_specs = process_spec.get("message_flows", [])
    for message_spec in message_specs:
        message_id = xml_id(message_spec.get("message_flow_id"), "message_flow_id")
        attrs = {
            "id": message_id,
            "name": str(message_spec.get("name", message_id)),
            "sourceRef": xml_id(message_spec.get("source"), "message source"),
            "targetRef": xml_id(message_spec.get("target"), "message target"),
        }
        message = ET.SubElement(collaboration, qname("bpmn", "messageFlow"), attrs)
        add_trace(
            message,
            meta,
            processId=process_id,
            interfaceIds=message_spec.get("interface_id"),
            evidenceIds=message_spec.get("evidence_ids"),
            questionIds=message_spec.get("question_ids"),
        )

    diagram = ET.SubElement(
        definitions,
        qname("bpmndi", "BPMNDiagram"),
        {"id": f"BPMNDiagram_{process_id}"},
    )
    plane = ET.SubElement(
        diagram,
        qname("bpmndi", "BPMNPlane"),
        {"id": f"BPMNPlane_{process_id}", "bpmnElement": f"COLLAB_{process_id}"},
    )

    lane_order = [str(item.get("lane_id")) for item in lanes]
    lane_y = {lane_id: 100 + index * 160 for index, lane_id in enumerate(lane_order)}
    primary_height = max(180, 160 * max(1, len(lane_order)))
    primary_shape = ET.SubElement(
        plane,
        qname("bpmndi", "BPMNShape"),
        {
            "id": f"{primary_participant_id}_di",
            "bpmnElement": primary_participant_id,
            "isHorizontal": "true",
        },
    )
    add_bounds(primary_shape, 40, 60, max(900, 190 * len(nodes) + 100), primary_height)

    for index, lane_id in enumerate(lane_order):
        shape = ET.SubElement(
            plane,
            qname("bpmndi", "BPMNShape"),
            {
                "id": f"{lane_id}_di",
                "bpmnElement": lane_id,
                "isHorizontal": "true",
            },
        )
        add_bounds(shape, 70, 60 + index * 160, max(870, 190 * len(nodes) + 70), 160)

    external_ids = [item for item in participant_elements if item != primary_participant_id]
    for index, participant_id in enumerate(external_ids):
        shape = ET.SubElement(
            plane,
            qname("bpmndi", "BPMNShape"),
            {
                "id": f"{participant_id}_di",
                "bpmnElement": participant_id,
                "isHorizontal": "true",
            },
        )
        add_bounds(shape, 40, 100 + primary_height + index * 120, max(900, 190 * len(nodes) + 100), 90)

    positions: dict[str, tuple[int, int, int, int]] = {}
    lane_counts: dict[str, int] = {}
    for index, node_spec in enumerate(nodes):
        node_id = str(node_spec["node_id"])
        node_type = str(node_spec.get("type", "userTask"))
        width, height = node_dimensions(node_type)
        lane_id = str(node_spec.get("lane_id", ""))
        lane_counts[lane_id] = lane_counts.get(lane_id, 0) + 1
        x = 130 + index * 180
        y = lane_y.get(lane_id, 110) + (40 if height <= 80 else 20)
        if node_type == "boundaryErrorEvent":
            attached = str(node_spec.get("attached_to"))
            if attached in positions:
                ax, ay, aw, ah = positions[attached]
                x, y = ax + aw - 15, ay + ah - 15
        positions[node_id] = (x, y, width, height)
        shape = ET.SubElement(
            plane,
            qname("bpmndi", "BPMNShape"),
            {"id": f"{node_id}_di", "bpmnElement": node_id},
        )
        add_bounds(shape, x, y, width, height)

    for flow_spec in flows:
        flow_id = str(flow_spec["flow_id"])
        source = str(flow_spec["source"])
        target = str(flow_spec["target"])
        sx, sy, sw, sh = positions[source]
        tx, ty, _tw, th = positions[target]
        edge = ET.SubElement(
            plane,
            qname("bpmndi", "BPMNEdge"),
            {"id": f"{flow_id}_di", "bpmnElement": flow_id},
        )
        ET.SubElement(
            edge,
            qname("di", "waypoint"),
            {"x": str(sx + sw), "y": str(sy + sh // 2)},
        )
        ET.SubElement(
            edge,
            qname("di", "waypoint"),
            {"x": str(tx), "y": str(ty + th // 2)},
        )

    for index, message_spec in enumerate(message_specs):
        message_id = str(message_spec["message_flow_id"])
        source = str(message_spec["source"])
        target = str(message_spec["target"])
        edge = ET.SubElement(
            plane,
            qname("bpmndi", "BPMNEdge"),
            {"id": f"{message_id}_di", "bpmnElement": message_id},
        )
        source_pos = positions.get(source, (100, 100, 100, 50))
        target_pos = positions.get(
            target,
            (200 + index * 120, 100 + primary_height, 100, 50),
        )
        ET.SubElement(
            edge,
            qname("di", "waypoint"),
            {
                "x": str(source_pos[0] + source_pos[2] // 2),
                "y": str(source_pos[1] + source_pos[3]),
            },
        )
        ET.SubElement(
            edge,
            qname("di", "waypoint"),
            {
                "x": str(target_pos[0] + target_pos[2] // 2),
                "y": str(target_pos[1]),
            },
        )

    return ET.ElementTree(definitions)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate BPMN 2.0 XML projections from canonical model-spec.json."
    )
    parser.add_argument("--spec", required=True, help="Path to model-spec.json.")
    parser.add_argument("--output-dir", default="models/bpmn", help="Directory for generated BPMN files.")
    parser.add_argument("--process-id", help="Generate only one process.")
    parser.add_argument("--output", help="Explicit output path; requires --process-id or a single process.")
    args = parser.parse_args()

    spec = load_spec(Path(args.spec))
    errors = validate_spec(spec, require_reviewed=True)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    processes = spec.get("processes", [])
    if args.process_id:
        processes = [item for item in processes if item.get("process_id") == args.process_id]
        if not processes:
            print(f"Unknown process_id: {args.process_id}", file=sys.stderr)
            return 1
    if args.output and len(processes) != 1:
        print("--output requires exactly one selected process", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for process_spec in processes:
        process_id = str(process_spec["process_id"])
        output = Path(args.output) if args.output else output_dir / f"{process_id}.bpmn"
        tree = build_bpmn(spec, process_spec)
        ET.indent(tree, space="  ")
        tree.write(output, encoding="utf-8", xml_declaration=True)
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
