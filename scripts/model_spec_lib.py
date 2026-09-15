from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable


CHINESE_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


TOP_LEVEL_LISTS = (
    "roles",
    "scenarios",
    "processes",
    "entities",
    "relations",
    "states",
    "rules",
    "interfaces",
    "capabilities",
    "evidence",
    "questions",
)

ID_FIELDS = {
    "roles": "role_id",
    "scenarios": "scenario_id",
    "processes": "process_id",
    "entities": "entity_id",
    "relations": "relation_id",
    "states": "state_id",
    "rules": "rule_id",
    "interfaces": "interface_id",
    "capabilities": "capability_id",
    "evidence": "evidence_id",
    "questions": "question_id",
}


def load_spec(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Model spec root must be a JSON object.")
    return data


def list_value(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def text_list(value: Any) -> list[str]:
    return [str(item) for item in list_value(value) if str(item).strip()]


def joined(value: Any, separator: str = "、") -> str:
    values = text_list(value)
    return separator.join(values) if values else "无"


def md(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, list):
        value = "、".join(str(item) for item in value)
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_index(spec: dict[str, Any], collection: str) -> dict[str, dict[str, Any]]:
    id_field = ID_FIELDS[collection]
    return {
        str(item[id_field]): item
        for item in spec.get(collection, [])
        if isinstance(item, dict) and item.get(id_field)
    }


def process_nodes(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(node["node_id"]): node
        for process in spec.get("processes", [])
        for node in process.get("nodes", [])
        if isinstance(node, dict) and node.get("node_id")
    }


def nested_ids(spec: dict[str, Any], key: str, id_field: str) -> set[str]:
    return {
        str(item[id_field])
        for process in spec.get("processes", [])
        for item in process.get(key, [])
        if isinstance(item, dict) and item.get(id_field)
    }


def all_known_ids(spec: dict[str, Any]) -> dict[str, set[str]]:
    ids = {
        collection: set(object_index(spec, collection))
        for collection in ID_FIELDS
    }
    ids.update(
        {
            "nodes": set(process_nodes(spec)),
            "flows": nested_ids(spec, "flows", "flow_id"),
            "exceptions": nested_ids(spec, "exceptions", "exception_id"),
            "message_flows": nested_ids(spec, "message_flows", "message_flow_id"),
            "fields": {
                str(attribute["field_id"])
                for entity in spec.get("entities", [])
                for attribute in entity.get("attributes", [])
                if isinstance(attribute, dict) and attribute.get("field_id")
            },
            "participants": {
                str(item["participant_id"])
                for process in spec.get("processes", [])
                for item in process.get("participants", [])
                if isinstance(item, dict) and item.get("participant_id")
            },
            "lanes": {
                str(lane["lane_id"])
                for process in spec.get("processes", [])
                for participant in process.get("participants", [])
                for lane in participant.get("lanes", [])
                if isinstance(lane, dict) and lane.get("lane_id")
            },
        }
    )
    return ids


def _require(item: dict[str, Any], fields: Iterable[str], label: str, errors: list[str]) -> None:
    for field in fields:
        if item.get(field) in (None, "", []):
            errors.append(f"{label}: missing required field '{field}'")


def _check_refs(
    item: dict[str, Any],
    field: str,
    allowed: set[str],
    label: str,
    errors: list[str],
) -> None:
    for ref in text_list(item.get(field)):
        if ref not in allowed:
            errors.append(f"{label}: {field} references missing ID '{ref}'")


def _require_chinese(
    item: dict[str, Any],
    field: str,
    label: str,
    errors: list[str],
) -> None:
    value = str(item.get(field, "") or "")
    if value and not CHINESE_PATTERN.search(value):
        errors.append(f"{label}: field '{field}' must contain a Chinese business label")


def validate_spec(
    spec: dict[str, Any],
    require_approved: bool = False,
    require_reviewed: bool = False,
) -> list[str]:
    errors: list[str] = []
    meta = spec.get("meta")
    scope = spec.get("scope")
    if not isinstance(meta, dict):
        errors.append("root: missing object 'meta'")
        meta = {}
    if not isinstance(scope, dict):
        errors.append("root: missing object 'scope'")
    for key in TOP_LEVEL_LISTS:
        if not isinstance(spec.get(key), list):
            errors.append(f"root: '{key}' must be a list")

    _require(
        meta,
        ("project_id", "project_name", "phase", "model_version", "baseline_id", "review_status"),
        "meta",
        errors,
    )
    _require_chinese(meta, "project_name", "meta", errors)
    status = meta.get("review_status")
    if status not in {"draft", "reviewed", "approved"}:
        errors.append("meta: review_status must be draft, reviewed, or approved")
    if require_approved and status != "approved":
        errors.append("meta: development-ready generation requires review_status='approved'")
    if require_reviewed and status not in {"reviewed", "approved"}:
        errors.append("meta: model generation requires review_status='reviewed' or 'approved'")
    if status == "approved":
        _require(meta, ("reviewer", "review_date", "review_files"), "meta", errors)
        review_date = meta.get("review_date")
        try:
            parsed_review_date = date.fromisoformat(str(review_date))
            if parsed_review_date > date.today():
                errors.append("meta: review_date cannot be in the future")
        except ValueError:
            errors.append("meta: review_date must use YYYY-MM-DD")

    for collection, id_field in ID_FIELDS.items():
        seen: set[str] = set()
        for item in spec.get(collection, []):
            item_id = str(item.get(id_field, ""))
            if not item_id:
                continue
            if item_id in seen:
                errors.append(f"{collection}: duplicate {id_field} '{item_id}'")
            seen.add(item_id)

    for nested_key, id_field in (
        ("nodes", "node_id"),
        ("flows", "flow_id"),
        ("message_flows", "message_flow_id"),
        ("exceptions", "exception_id"),
    ):
        seen = set()
        for process in spec.get("processes", []):
            for item in process.get(nested_key, []):
                item_id = str(item.get(id_field, ""))
                if not item_id:
                    continue
                if item_id in seen:
                    errors.append(f"{nested_key}: duplicate {id_field} '{item_id}'")
                seen.add(item_id)

    ids = all_known_ids(spec)
    global_seen: dict[str, str] = {}
    for collection, values in ids.items():
        for value in values:
            if value in global_seen:
                errors.append(
                    f"global ID '{value}' is reused by {global_seen[value]} and {collection}"
                )
            global_seen[value] = collection

    roles = ids["roles"]
    processes = ids["processes"]
    nodes = ids["nodes"]
    entities = ids["entities"]
    states = ids["states"]
    rules = ids["rules"]
    interfaces = ids["interfaces"]
    capabilities = ids["capabilities"]
    evidence = ids["evidence"]
    questions = ids["questions"]
    exceptions = ids["exceptions"]
    fields = ids["fields"]

    for scenario in spec.get("scenarios", []):
        label = scenario.get("scenario_id", "scenario<?>")
        _require(scenario, ("scenario_id", "name"), label, errors)
        _check_refs(scenario, "role_ids", roles, label, errors)
        _check_refs(scenario, "process_ids", processes, label, errors)
        _check_refs(scenario, "evidence_ids", evidence, label, errors)
        _check_refs(scenario, "question_ids", questions, label, errors)

    node_owner: dict[str, str] = {}
    for process in spec.get("processes", []):
        process_id = str(process.get("process_id", "process<?>"))
        _require(process, ("process_id", "name", "trigger", "end_result"), process_id, errors)
        _require_chinese(process, "name", process_id, errors)
        process_node_ids = {
            str(node.get("node_id"))
            for node in process.get("nodes", [])
            if node.get("node_id")
        }
        start_count = sum(node.get("type") == "startEvent" for node in process.get("nodes", []))
        end_count = sum(node.get("type") == "endEvent" for node in process.get("nodes", []))
        if start_count < 1:
            errors.append(f"{process_id}: requires at least one startEvent")
        if end_count < 1:
            errors.append(f"{process_id}: requires at least one endEvent")

        participants = process.get("participants", [])
        participant_ids = {
            str(item.get("participant_id"))
            for item in participants
            if item.get("participant_id")
        }
        lane_ids = {
            str(lane.get("lane_id"))
            for participant in participants
            for lane in participant.get("lanes", [])
            if lane.get("lane_id")
        }
        lane_roles = {
            str(lane.get("role_id"))
            for participant in participants
            for lane in participant.get("lanes", [])
            if lane.get("role_id")
        }
        for role_id in lane_roles:
            if role_id not in roles:
                errors.append(f"{process_id}: lane references missing role_id '{role_id}'")
        if not participants:
            errors.append(f"{process_id}: participants must define the primary process pool")
        for participant in participants:
            participant_id = str(participant.get("participant_id", "participant<?>"))
            _require(participant, ("participant_id", "name"), f"{process_id}/{participant_id}", errors)
            _require_chinese(participant, "name", f"{process_id}/{participant_id}", errors)
            for lane in participant.get("lanes", []):
                lane_id = str(lane.get("lane_id", "lane<?>"))
                _require(lane, ("lane_id", "name"), f"{process_id}/{lane_id}", errors)
                _require_chinese(lane, "name", f"{process_id}/{lane_id}", errors)

        for node in process.get("nodes", []):
            node_id = str(node.get("node_id", "node<?>"))
            _require(node, ("node_id", "name", "type"), f"{process_id}/{node_id}", errors)
            _require_chinese(node, "name", f"{process_id}/{node_id}", errors)
            if node_id in node_owner:
                errors.append(
                    f"node_id '{node_id}' is reused by {node_owner[node_id]} and {process_id}"
                )
            node_owner[node_id] = process_id
            if node.get("participant_id") and node["participant_id"] not in participant_ids:
                errors.append(
                    f"{process_id}/{node_id}: participant_id references missing ID '{node['participant_id']}'"
                )
            if node.get("lane_id") and node["lane_id"] not in lane_ids:
                errors.append(
                    f"{process_id}/{node_id}: lane_id references missing ID '{node['lane_id']}'"
                )
            if node.get("actor_role_id") and node["actor_role_id"] not in roles:
                errors.append(
                    f"{process_id}/{node_id}: actor_role_id references missing ID '{node['actor_role_id']}'"
                )
            if node.get("type") == "boundaryErrorEvent":
                attached_to = node.get("attached_to")
                if attached_to not in process_node_ids:
                    errors.append(
                        f"{process_id}/{node_id}: boundaryErrorEvent requires a valid attached_to node"
                    )
            for field, allowed in (
                ("capability_ids", capabilities),
                ("entity_ids", entities),
                ("rule_ids", rules),
                ("state_ids", states),
                ("interface_ids", interfaces),
                ("exception_ids", exceptions),
                ("evidence_ids", evidence),
                ("question_ids", questions),
            ):
                _check_refs(node, field, allowed, f"{process_id}/{node_id}", errors)

        flow_ids: set[str] = set()
        outgoing_counts: dict[str, int] = {node_id: 0 for node_id in process_node_ids}
        adjacency: dict[str, set[str]] = {node_id: set() for node_id in process_node_ids}
        reverse_adjacency: dict[str, set[str]] = {node_id: set() for node_id in process_node_ids}
        for flow in process.get("flows", []):
            flow_id = str(flow.get("flow_id", "flow<?>"))
            _require(flow, ("flow_id", "name", "source", "target"), f"{process_id}/{flow_id}", errors)
            _require_chinese(flow, "name", f"{process_id}/{flow_id}", errors)
            if flow_id in flow_ids:
                errors.append(f"{process_id}: duplicate flow_id '{flow_id}'")
            flow_ids.add(flow_id)
            if flow.get("source") not in process_node_ids:
                errors.append(f"{process_id}/{flow_id}: missing source node '{flow.get('source')}'")
            if flow.get("target") not in process_node_ids:
                errors.append(f"{process_id}/{flow_id}: missing target node '{flow.get('target')}'")
            if flow.get("source") in outgoing_counts:
                outgoing_counts[str(flow.get("source"))] += 1
            if flow.get("source") in adjacency and flow.get("target") in reverse_adjacency:
                adjacency[str(flow.get("source"))].add(str(flow.get("target")))
                reverse_adjacency[str(flow.get("target"))].add(str(flow.get("source")))
            _check_refs(flow, "rule_ids", rules, f"{process_id}/{flow_id}", errors)
            _check_refs(flow, "exception_ids", exceptions, f"{process_id}/{flow_id}", errors)
            _check_refs(flow, "evidence_ids", evidence, f"{process_id}/{flow_id}", errors)
            _check_refs(flow, "question_ids", questions, f"{process_id}/{flow_id}", errors)

        message_endpoints = process_node_ids | participant_ids
        for message in process.get("message_flows", []):
            message_id = str(message.get("message_flow_id", "message<?>"))
            _require(
                message,
                ("message_flow_id", "name", "source", "target", "interface_id"),
                f"{process_id}/{message_id}",
                errors,
            )
            _require_chinese(message, "name", f"{process_id}/{message_id}", errors)
            if message.get("source") not in message_endpoints:
                errors.append(f"{process_id}/{message_id}: missing message source")
            if message.get("target") not in message_endpoints:
                errors.append(f"{process_id}/{message_id}: missing message target")
            _check_refs(message, "interface_id", interfaces, f"{process_id}/{message_id}", errors)

        for exception in process.get("exceptions", []):
            exception_id = str(exception.get("exception_id", "exception<?>"))
            _require(
                exception,
                ("exception_id", "trigger_node_id", "condition", "handling"),
                f"{process_id}/{exception_id}",
                errors,
            )
            if exception.get("trigger_node_id") not in process_node_ids:
                errors.append(f"{process_id}/{exception_id}: missing trigger_node_id")
            path_flow_ids = text_list(exception.get("path_flow_ids"))
            if not path_flow_ids:
                errors.append(f"{process_id}/{exception_id}: requires path_flow_ids")
            for path_flow_id in path_flow_ids:
                if path_flow_id not in flow_ids:
                    errors.append(
                        f"{process_id}/{exception_id}: path_flow_ids references missing flow '{path_flow_id}'"
                    )
            _check_refs(exception, "evidence_ids", evidence, f"{process_id}/{exception_id}", errors)
            _check_refs(exception, "question_ids", questions, f"{process_id}/{exception_id}", errors)

        for node in process.get("nodes", []):
            if node.get("type") in {"exclusiveGateway", "inclusiveGateway"}:
                node_id = str(node.get("node_id"))
                if outgoing_counts.get(node_id, 0) < 2:
                    errors.append(
                        f"{process_id}/{node_id}: decision gateway requires at least two outgoing flows"
                    )

        node_types = {
            str(node.get("node_id")): str(node.get("type"))
            for node in process.get("nodes", [])
            if node.get("node_id")
        }
        for node in process.get("nodes", []):
            if node.get("type") == "boundaryErrorEvent" and node.get("attached_to") in adjacency:
                adjacency[str(node["attached_to"])].add(str(node["node_id"]))
                reverse_adjacency[str(node["node_id"])].add(str(node["attached_to"]))
        starts = {node_id for node_id, node_type in node_types.items() if node_type == "startEvent"}
        ends = {node_id for node_id, node_type in node_types.items() if node_type == "endEvent"}

        def traverse(seeds: set[str], graph: dict[str, set[str]]) -> set[str]:
            visited: set[str] = set()
            pending = list(seeds)
            while pending:
                current = pending.pop()
                if current in visited:
                    continue
                visited.add(current)
                pending.extend(graph.get(current, set()) - visited)
            return visited

        reachable = traverse(starts, adjacency)
        can_reach_end = traverse(ends, reverse_adjacency)
        for node_id in sorted(process_node_ids - reachable):
            errors.append(f"{process_id}/{node_id}: node is unreachable from every startEvent")
        for node_id in sorted(process_node_ids - can_reach_end):
            errors.append(f"{process_id}/{node_id}: node cannot reach any endEvent")

        _check_refs(process, "evidence_ids", evidence, process_id, errors)
        _check_refs(process, "question_ids", questions, process_id, errors)

    for entity in spec.get("entities", []):
        label = entity.get("entity_id", "entity<?>")
        _require(entity, ("entity_id", "name", "class_name", "definition"), label, errors)
        _require_chinese(entity, "name", str(label), errors)
        parent = entity.get("parent_entity_id")
        if parent and parent != "Thing" and parent not in entities:
            errors.append(f"{label}: parent_entity_id references missing entity '{parent}'")
        _check_refs(entity, "evidence_ids", evidence, label, errors)
        _check_refs(entity, "question_ids", questions, label, errors)
        _check_refs(entity, "process_ids", processes, label, errors)
        _check_refs(entity, "node_ids", nodes, label, errors)
        for attribute in entity.get("attributes", []):
            attribute_label = attribute.get("field_id") or f"{label}/attribute<?>"
            _require(
                attribute,
                ("field_id", "name", "label", "datatype", "required"),
                attribute_label,
                errors,
            )
            _require_chinese(attribute, "label", str(attribute_label), errors)
            _check_refs(attribute, "evidence_ids", evidence, attribute_label, errors)
            _check_refs(attribute, "question_ids", questions, attribute_label, errors)

    for relation in spec.get("relations", []):
        label = relation.get("relation_id", "relation<?>")
        _require(
            relation,
            ("relation_id", "name_en", "name_cn", "source_entity_id", "target_entity_id", "cardinality"),
            label,
            errors,
        )
        _require_chinese(relation, "name_cn", str(label), errors)
        _check_refs(relation, "source_entity_id", entities, label, errors)
        _check_refs(relation, "target_entity_id", entities, label, errors)
        _check_refs(relation, "process_ids", processes, label, errors)
        _check_refs(relation, "node_ids", nodes, label, errors)
        _check_refs(relation, "evidence_ids", evidence, label, errors)
        _check_refs(relation, "question_ids", questions, label, errors)

    for state in spec.get("states", []):
        label = state.get("state_id", "state<?>")
        _require(
            state,
            ("state_id", "entity_id", "from_state", "to_state", "trigger", "node_id"),
            label,
            errors,
        )
        for field in ("from_state", "to_state", "trigger"):
            _require_chinese(state, field, str(label), errors)
        _check_refs(state, "entity_id", entities, label, errors)
        _check_refs(state, "node_id", nodes, label, errors)
        _check_refs(state, "guard_rule_ids", rules, label, errors)
        _check_refs(state, "exception_ids", exceptions, label, errors)
        _check_refs(state, "evidence_ids", evidence, label, errors)
        _check_refs(state, "question_ids", questions, label, errors)

    for rule in spec.get("rules", []):
        label = rule.get("rule_id", "rule<?>")
        _require(rule, ("rule_id", "name", "type", "trigger", "inputs", "outputs", "logic"), label, errors)
        _check_refs(rule, "capability_ids", capabilities, label, errors)
        _check_refs(rule, "process_ids", processes, label, errors)
        _check_refs(rule, "node_ids", nodes, label, errors)
        _check_refs(rule, "entity_ids", entities, label, errors)
        _check_refs(rule, "evidence_ids", evidence, label, errors)
        _check_refs(rule, "question_ids", questions, label, errors)

    for interface in spec.get("interfaces", []):
        label = interface.get("interface_id", "interface<?>")
        _require(
            interface,
            ("interface_id", "name", "external_system", "direction", "trigger", "message_object", "owner", "failure_handling"),
            label,
            errors,
        )
        _check_refs(interface, "process_ids", processes, label, errors)
        _check_refs(interface, "node_ids", nodes, label, errors)
        _check_refs(interface, "evidence_ids", evidence, label, errors)
        _check_refs(interface, "question_ids", questions, label, errors)

    for capability in spec.get("capabilities", []):
        label = capability.get("capability_id", "capability<?>")
        _require(capability, ("capability_id", "name", "type", "priority", "goal"), label, errors)
        for field, allowed in (
            ("role_ids", roles),
            ("process_ids", processes),
            ("node_ids", nodes),
            ("entity_ids", entities),
            ("rule_ids", rules),
            ("state_ids", states),
            ("interface_ids", interfaces),
            ("evidence_ids", evidence),
            ("question_ids", questions),
        ):
            _check_refs(capability, field, allowed, label, errors)
        if capability.get("priority") == "Must":
            _require(
                capability,
                ("inputs", "outputs", "normal_flow", "exception_flow", "acceptance_criteria"),
                label,
                errors,
            )

    for evidence_item in spec.get("evidence", []):
        label = evidence_item.get("evidence_id", "evidence<?>")
        _require(evidence_item, ("evidence_id", "type", "source", "summary", "confidence"), label, errors)
        _check_refs(evidence_item, "scenario_ids", ids["scenarios"], label, errors)
        _check_refs(evidence_item, "process_ids", processes, label, errors)
        _check_refs(evidence_item, "node_ids", nodes, label, errors)
        _check_refs(evidence_item, "capability_ids", capabilities, label, errors)
        _check_refs(evidence_item, "rule_ids", rules, label, errors)

    for question in spec.get("questions", []):
        label = question.get("question_id", "question<?>")
        _require(question, ("question_id", "question", "category", "blocking_level", "status"), label, errors)
        _check_refs(question, "scenario_ids", ids["scenarios"], label, errors)
        _check_refs(question, "process_ids", processes, label, errors)
        _check_refs(question, "node_ids", nodes, label, errors)
        _check_refs(question, "capability_ids", capabilities, label, errors)
        for related_id in text_list(question.get("related_ids")):
            if related_id not in global_seen and related_id not in fields:
                errors.append(f"{label}: related_ids references missing ID '{related_id}'")
        if question.get("blocking_level") == "High" and not question.get("mock_or_defer_strategy"):
            errors.append(f"{label}: High blocker requires mock_or_defer_strategy")
        if (
            status == "approved"
            and question.get("blocking_level") == "High"
            and question.get("status") != "Closed"
        ):
            errors.append(f"{label}: approved development baseline cannot contain an open High blocker")
        if question.get("status") == "Closed":
            _require(
                question,
                ("resolution", "closed_date", "closed_by"),
                label,
                errors,
            )
            closed_date = question.get("closed_date")
            try:
                parsed_closed_date = date.fromisoformat(str(closed_date))
                if parsed_closed_date > date.today():
                    errors.append(f"{label}: closed_date cannot be in the future")
            except ValueError:
                errors.append(f"{label}: closed_date must use YYYY-MM-DD")

    node_items = process_nodes(spec)

    def reverse_node_refs(field: str, stable_id: str) -> set[str]:
        return {
            node_id
            for node_id, node in node_items.items()
            if stable_id in text_list(node.get(field))
        }

    for collection, id_field, node_field in (
        ("entities", "entity_id", "entity_ids"),
        ("rules", "rule_id", "rule_ids"),
        ("interfaces", "interface_id", "interface_ids"),
        ("capabilities", "capability_id", "capability_ids"),
        ("evidence", "evidence_id", "evidence_ids"),
        ("questions", "question_id", "question_ids"),
    ):
        for item in spec.get(collection, []):
            stable_id = str(item.get(id_field))
            expected = reverse_node_refs(node_field, stable_id)
            actual = set(text_list(item.get("node_ids")))
            if expected != actual:
                errors.append(
                    f"{stable_id}: bidirectional node trace drift; "
                    f"expected={sorted(expected)} actual={sorted(actual)}"
                )
            expected_processes = {
                node_owner[node_id] for node_id in expected if node_id in node_owner
            }
            actual_processes = set(text_list(item.get("process_ids")))
            if expected_processes != actual_processes:
                errors.append(
                    f"{stable_id}: bidirectional process trace drift; "
                    f"expected={sorted(expected_processes)} actual={sorted(actual_processes)}"
                )

    for state in spec.get("states", []):
        state_id = str(state.get("state_id"))
        expected = reverse_node_refs("state_ids", state_id)
        actual = {str(state.get("node_id"))} if state.get("node_id") else set()
        if expected != actual:
            errors.append(
                f"{state_id}: bidirectional state/node trace drift; "
                f"expected={sorted(expected)} actual={sorted(actual)}"
            )

    must_interface_ids = {
        interface_id
        for capability in spec.get("capabilities", [])
        if capability.get("priority") == "Must"
        for interface_id in text_list(capability.get("interface_ids"))
    }
    for interface in spec.get("interfaces", []):
        interface_id = str(interface.get("interface_id"))
        if interface_id not in must_interface_ids:
            continue
        unresolved_contract = any(
            not interface.get(field) or "待确认" in str(interface.get(field))
            for field in ("payload_fields", "frequency", "protocol_format", "failure_handling")
        )
        if unresolved_contract and not text_list(interface.get("question_ids")):
            errors.append(
                f"{interface_id}: Must capability interface has unresolved contract fields "
                "but no question_ids"
            )

    if status == "approved":
        if not spec.get("evidence"):
            errors.append("approved baseline requires at least one evidence item")

        def require_support(item: dict[str, Any], label: str) -> None:
            if not text_list(item.get("evidence_ids")) and not text_list(item.get("question_ids")):
                errors.append(
                    f"{label}: approved baseline requires evidence_ids or question_ids"
                )

        for collection, id_field in (
            ("roles", "role_id"),
            ("scenarios", "scenario_id"),
            ("processes", "process_id"),
            ("entities", "entity_id"),
            ("relations", "relation_id"),
            ("states", "state_id"),
            ("rules", "rule_id"),
            ("interfaces", "interface_id"),
            ("capabilities", "capability_id"),
        ):
            for item in spec.get(collection, []):
                require_support(item, str(item.get(id_field, f"{collection}<?>")))
        for process in spec.get("processes", []):
            process_id = str(process.get("process_id"))
            for key, id_field in (
                ("nodes", "node_id"),
                ("flows", "flow_id"),
                ("message_flows", "message_flow_id"),
                ("exceptions", "exception_id"),
            ):
                for item in process.get(key, []):
                    require_support(
                        item,
                        f"{process_id}/{item.get(id_field, f'{key}<?>')}",
                    )
        for entity in spec.get("entities", []):
            for attribute in entity.get("attributes", []):
                require_support(
                    attribute,
                    str(attribute.get("field_id", "field<?>")),
                )

    return errors
