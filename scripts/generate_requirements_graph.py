from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from graph_runtime import (
    Graph,
    Literal,
    OWL,
    PROV,
    RDF,
    REQ,
    RDFS,
    URIRef,
    XSD,
    deterministic_turtle,
)
from model_spec_lib import load_spec, text_list, validate_spec


CLASS_BY_COLLECTION = {
    "roles": REQ.Role,
    "scenarios": REQ.Scenario,
    "entities": REQ.Entity,
    "relations": REQ.EntityRelation,
    "states": REQ.StateTransition,
    "rules": REQ.BusinessRule,
    "interfaces": REQ.Interface,
    "capabilities": REQ.Capability,
    "evidence": REQ.Evidence,
    "questions": REQ.Question,
    "inferences": REQ.Inference,
    "decisions": REQ.Decision,
}
ID_BY_COLLECTION = {
    "roles": "role_id",
    "scenarios": "scenario_id",
    "entities": "entity_id",
    "relations": "relation_id",
    "states": "state_id",
    "rules": "rule_id",
    "interfaces": "interface_id",
    "capabilities": "capability_id",
    "evidence": "evidence_id",
    "questions": "question_id",
    "inferences": "inference_id",
    "decisions": "decision_id",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def base_iri(spec: dict[str, Any]) -> str:
    configured = str(spec.get("meta", {}).get("ontology_iri") or "").strip()
    if configured:
        return configured if configured.endswith(("#", "/")) else configured + "#"
    project = quote(str(spec.get("meta", {}).get("project_id") or "project"), safe="-._~")
    return f"https://openai.example/requirements/{project}#"


def resource(base: str, stable_id: str) -> URIRef:
    return URIRef(base + quote(str(stable_id), safe="-._~"))


def add_literal(graph: Graph, subject: URIRef, predicate: URIRef, value: Any) -> None:
    if value is None or value == "":
        return
    if isinstance(value, bool):
        graph.add((subject, predicate, Literal(value, datatype=XSD.boolean)))
    elif isinstance(value, (dict, list)):
        graph.add((subject, predicate, Literal(canonical_json(value))))
    else:
        graph.add((subject, predicate, Literal(str(value))))


def add_ref_list(
    graph: Graph,
    subject: URIRef,
    predicate: URIRef,
    values: Iterable[Any],
    base: str,
) -> None:
    for value in values:
        if value:
            graph.add((subject, predicate, resource(base, str(value))))


def add_trace(graph: Graph, subject: URIRef, item: dict[str, Any], base: str) -> None:
    add_ref_list(graph, subject, REQ.supportedBy, text_list(item.get("evidence_ids")), base)
    add_ref_list(graph, subject, REQ.hasQuestion, text_list(item.get("question_ids")), base)
    for evidence_id in text_list(item.get("evidence_ids")):
        graph.add((subject, PROV.wasDerivedFrom, resource(base, evidence_id)))


def add_named_item(
    graph: Graph,
    base: str,
    item: dict[str, Any],
    stable_id: str,
    class_uri: URIRef,
) -> URIRef:
    subject = resource(base, stable_id)
    graph.add((subject, RDF.type, class_uri))
    graph.add((subject, REQ.stableId, Literal(stable_id)))
    add_literal(graph, subject, REQ.name, item.get("name") or item.get("question"))
    add_literal(graph, subject, REQ.description, item.get("description") or item.get("definition"))
    add_trace(graph, subject, item, base)
    return subject


def build_requirements_graph(spec: dict[str, Any], spec_path: Path) -> Graph:
    skill = Path(__file__).resolve().parent.parent
    graph = Graph()
    graph.parse(skill / "assets" / "requirements-graph-ontology.ttl", format="turtle")
    graph.bind("req", REQ)
    graph.bind("prov", PROV)
    graph.bind("owl", OWL)
    graph.bind("rdfs", RDFS)

    base = base_iri(spec)
    meta = spec.get("meta", {})
    project_id = str(meta["project_id"])
    project = add_named_item(graph, base, meta, project_id, REQ.Project)
    add_literal(graph, project, REQ.name, meta.get("project_name"))
    add_literal(graph, project, REQ.modelVersion, meta.get("model_version"))
    add_literal(graph, project, REQ.baselineId, meta.get("baseline_id"))
    add_literal(graph, project, REQ.reviewStatus, meta.get("review_status"))
    for value in text_list(spec.get("scope", {}).get("in_scope")):
        add_literal(graph, project, REQ.scopeIn, value)
    for value in text_list(spec.get("scope", {}).get("out_of_scope")):
        add_literal(graph, project, REQ.scopeOut, value)
    for value in spec.get("scope", {}).get("constraints", []):
        add_literal(graph, project, REQ.constraintText, value)

    spec_artifact = resource(base, "ARTIFACT-MODEL-SPEC")
    graph.add((spec_artifact, RDF.type, REQ.ModelArtifact))
    graph.add((spec_artifact, RDF.type, PROV.Entity))
    graph.add((spec_artifact, REQ.name, Literal("model-spec.json")))
    graph.add((spec_artifact, REQ.sourceText, Literal(spec_path.as_posix())))
    graph.add(
        (
            spec_artifact,
            REQ.constraintText,
            Literal(hashlib.sha256(spec_path.read_bytes()).hexdigest()),
        )
    )

    reviewer = str(meta.get("reviewer") or "").strip()
    if reviewer:
        reviewer_ref = resource(base, "AGENT-" + reviewer)
        graph.add((reviewer_ref, RDF.type, PROV.Agent))
        graph.add((reviewer_ref, RDFS.label, Literal(reviewer)))
        graph.add((spec_artifact, PROV.wasAttributedTo, reviewer_ref))
        review = resource(base, f"REVIEW-{meta.get('model_version', 'unknown')}")
        graph.add((review, RDF.type, REQ.ReviewActivity))
        graph.add((review, RDF.type, PROV.Activity))
        graph.add((review, PROV.used, spec_artifact))
        graph.add((review, PROV.wasAssociatedWith, reviewer_ref))
        add_literal(graph, review, REQ.reviewStatus, meta.get("review_status"))
        add_literal(graph, review, REQ.sourceText, meta.get("review_date"))

    refs: dict[str, dict[str, URIRef]] = {}
    for collection, class_uri in CLASS_BY_COLLECTION.items():
        refs[collection] = {}
        id_field = ID_BY_COLLECTION[collection]
        for index, item in enumerate(spec.get(collection, [])):
            stable_id = str(item.get(id_field) or f"{collection.upper()}-{index + 1}")
            refs[collection][stable_id] = add_named_item(
                graph, base, item, stable_id, class_uri
            )

    for role in spec.get("roles", []):
        subject = refs["roles"][role["role_id"]]
        for responsibility in text_list(role.get("responsibilities")):
            add_literal(graph, subject, REQ.description, responsibility)

    for scenario in spec.get("scenarios", []):
        subject = refs["scenarios"][scenario["scenario_id"]]
        graph.add((project, REQ.hasScenario, subject))
        add_literal(graph, subject, REQ.priority, scenario.get("priority"))
        add_ref_list(graph, subject, REQ.hasProcess, text_list(scenario.get("process_ids")), base)
        add_ref_list(graph, subject, REQ.performedByRole, text_list(scenario.get("role_ids")), base)

    for process in spec.get("processes", []):
        process_id = str(process["process_id"])
        subject = add_named_item(graph, base, process, process_id, REQ.Process)
        graph.add((project, REQ.hasProcess, subject))
        add_literal(graph, subject, REQ.trigger, process.get("trigger"))
        add_ref_list(graph, subject, REQ.performedByRole, text_list(process.get("role_ids")), base)
        add_ref_list(graph, subject, REQ.touchesEntity, text_list(process.get("entity_ids")), base)
        add_ref_list(graph, subject, REQ.usesInterface, text_list(process.get("interface_ids")), base)

        participant_refs: dict[str, URIRef] = {}
        for participant in process.get("participants", []):
            participant_id = str(participant["participant_id"])
            participant_ref = add_named_item(
                graph, base, participant, participant_id, REQ.Participant
            )
            participant_refs[participant_id] = participant_ref
            graph.add((subject, REQ.hasParticipant, participant_ref))
            for lane in participant.get("lanes", []):
                lane_ref = add_named_item(graph, base, lane, str(lane["lane_id"]), REQ.Lane)
                graph.add((participant_ref, REQ.hasLane, lane_ref))
                if lane.get("role_id"):
                    graph.add((lane_ref, REQ.performedByRole, resource(base, lane["role_id"])))

        node_refs: dict[str, URIRef] = {}
        for node in process.get("nodes", []):
            node_id = str(node["node_id"])
            node_ref = add_named_item(graph, base, node, node_id, REQ.ProcessNode)
            node_refs[node_id] = node_ref
            graph.add((subject, REQ.hasNode, node_ref))
            graph.add((node_ref, REQ.belongsToProcess, subject))
            add_literal(graph, node_ref, REQ.nodeType, node.get("type"))
            add_literal(graph, node_ref, REQ.trigger, node.get("trigger"))
            add_ref_list(graph, node_ref, REQ.usesCapability, text_list(node.get("capability_ids")), base)
            for capability_id in text_list(node.get("capability_ids")):
                graph.add((resource(base, capability_id), REQ.usedByNode, node_ref))
            add_ref_list(graph, node_ref, REQ.touchesEntity, text_list(node.get("entity_ids")), base)
            add_ref_list(graph, node_ref, REQ.governedByRule, text_list(node.get("rule_ids")), base)
            add_ref_list(graph, node_ref, REQ.usesInterface, text_list(node.get("interface_ids")), base)
            if node.get("actor_role_id"):
                graph.add((node_ref, REQ.performedByRole, resource(base, node["actor_role_id"])))
            if str(node.get("type", "")).lower() == "startevent":
                graph.add((subject, REQ.hasStartNode, node_ref))
            if str(node.get("type", "")).lower() == "endevent":
                graph.add((subject, REQ.hasEndNode, node_ref))

        for flow in process.get("flows", []):
            flow_ref = add_named_item(
                graph, base, flow, str(flow["flow_id"]), REQ.SequenceFlow
            )
            graph.add((subject, REQ.hasFlow, flow_ref))
            graph.add((flow_ref, REQ.sourceNode, resource(base, flow["source"])))
            graph.add((flow_ref, REQ.targetNode, resource(base, flow["target"])))
            add_literal(graph, flow_ref, REQ.condition, flow.get("condition"))
            add_ref_list(graph, flow_ref, REQ.governedByRule, text_list(flow.get("rule_ids")), base)

        for exception in process.get("exceptions", []):
            exception_ref = add_named_item(
                graph, base, exception, str(exception["exception_id"]), REQ.Exception
            )
            graph.add((subject, REQ.hasException, exception_ref))
            graph.add(
                (
                    exception_ref,
                    REQ.triggerNode,
                    resource(base, exception["trigger_node_id"]),
                )
            )
            add_literal(graph, exception_ref, REQ.condition, exception.get("condition"))

        for message in process.get("message_flows", []):
            message_ref = add_named_item(
                graph,
                base,
                message,
                str(message["message_flow_id"]),
                REQ.MessageFlow,
            )
            graph.add((subject, REQ.hasMessageFlow, message_ref))
            graph.add((message_ref, REQ.sourceParticipant, resource(base, message["source"])))
            graph.add((message_ref, REQ.targetParticipant, resource(base, message["target"])))
            if message.get("interface_id"):
                graph.add((message_ref, REQ.usesInterface, resource(base, message["interface_id"])))

    for entity in spec.get("entities", []):
        subject = refs["entities"][entity["entity_id"]]
        add_literal(graph, subject, REQ.stateful, bool(entity.get("stateful")))
        add_ref_list(graph, subject, REQ.hasProcess, text_list(entity.get("process_ids")), base)
        if entity.get("parent_entity_id") and entity["parent_entity_id"] != "Thing":
            graph.add((subject, RDFS.subClassOf, resource(base, entity["parent_entity_id"])))
        for attribute in entity.get("attributes", []):
            field_id = str(attribute.get("field_id") or f"{entity['entity_id']}-FIELD")
            field_ref = add_named_item(graph, base, attribute, field_id, REQ.EntityAttribute)
            graph.add((subject, REQ.hasAttribute, field_ref))
            add_literal(graph, field_ref, REQ.required, bool(attribute.get("required")))

    for relation in spec.get("relations", []):
        subject = refs["relations"][relation["relation_id"]]
        graph.add((subject, REQ.sourceEntity, resource(base, relation["source_entity_id"])))
        graph.add((subject, REQ.targetEntity, resource(base, relation["target_entity_id"])))
        add_literal(graph, subject, REQ.cardinality, relation.get("cardinality"))
        add_literal(graph, subject, REQ.required, bool(relation.get("required")))
        add_ref_list(graph, subject, REQ.hasProcess, text_list(relation.get("process_ids")), base)

    for transition in spec.get("states", []):
        subject = refs["states"][transition["state_id"]]
        entity_ref = resource(base, transition["entity_id"])
        graph.add((subject, REQ.transitionOfEntity, entity_ref))
        graph.add((entity_ref, REQ.hasStateTransition, subject))
        source_state = resource(
            base, f"STATE-{transition['entity_id']}-{transition['from_state']}"
        )
        target_state = resource(
            base, f"STATE-{transition['entity_id']}-{transition['to_state']}"
        )
        for state_ref, label in (
            (source_state, transition["from_state"]),
            (target_state, transition["to_state"]),
        ):
            graph.add((state_ref, RDF.type, REQ.State))
            graph.add((state_ref, REQ.name, Literal(str(label))))
        graph.add((subject, REQ.sourceState, source_state))
        graph.add((subject, REQ.targetState, target_state))
        graph.add((subject, REQ.triggerNode, resource(base, transition["node_id"])))
        add_literal(graph, subject, REQ.trigger, transition.get("trigger"))
        add_ref_list(graph, subject, REQ.governedByRule, text_list(transition.get("guard_rule_ids")), base)

    for rule in spec.get("rules", []):
        subject = refs["rules"][rule["rule_id"]]
        add_literal(graph, subject, REQ.trigger, rule.get("trigger"))
        add_literal(graph, subject, REQ.logic, rule.get("logic"))
        for value in rule.get("inputs", []):
            add_literal(graph, subject, REQ.inputValue, value)
        for value in rule.get("outputs", []):
            add_literal(graph, subject, REQ.outputValue, value)
        add_ref_list(graph, subject, REQ.hasProcess, text_list(rule.get("process_ids")), base)
        add_ref_list(graph, subject, REQ.touchesEntity, text_list(rule.get("entity_ids")), base)
        add_ref_list(graph, subject, REQ.usesCapability, text_list(rule.get("capability_ids")), base)

    for interface in spec.get("interfaces", []):
        subject = refs["interfaces"][interface["interface_id"]]
        add_literal(graph, subject, REQ.trigger, interface.get("trigger"))
        add_ref_list(graph, subject, REQ.hasProcess, text_list(interface.get("process_ids")), base)

    for capability in spec.get("capabilities", []):
        subject = refs["capabilities"][capability["capability_id"]]
        add_literal(graph, subject, REQ.priority, capability.get("priority"))
        add_ref_list(graph, subject, REQ.hasProcess, text_list(capability.get("process_ids")), base)
        add_ref_list(graph, subject, REQ.touchesEntity, text_list(capability.get("entity_ids")), base)
        add_ref_list(graph, subject, REQ.governedByRule, text_list(capability.get("rule_ids")), base)
        add_ref_list(graph, subject, REQ.usesInterface, text_list(capability.get("interface_ids")), base)
        add_ref_list(graph, subject, REQ.performedByRole, text_list(capability.get("role_ids")), base)
        for node_id in text_list(capability.get("node_ids")):
            graph.add((subject, REQ.usedByNode, resource(base, node_id)))
        for criterion in text_list(capability.get("acceptance_criteria")):
            add_literal(graph, subject, REQ.acceptanceCriterion, criterion)

    for evidence in spec.get("evidence", []):
        subject = refs["evidence"][evidence["evidence_id"]]
        graph.add((subject, RDF.type, PROV.Entity))
        add_literal(graph, subject, REQ.sourceText, evidence.get("source"))
        provider = str(evidence.get("provider") or "").strip()
        if provider:
            provider_ref = resource(base, "AGENT-" + provider)
            graph.add((provider_ref, RDF.type, PROV.Agent))
            graph.add((provider_ref, RDFS.label, Literal(provider)))
            graph.add((subject, PROV.wasAttributedTo, provider_ref))

    for question in spec.get("questions", []):
        subject = refs["questions"][question["question_id"]]
        add_literal(graph, subject, REQ.blockingLevel, question.get("blocking_level"))
        add_literal(graph, subject, REQ.questionStatus, question.get("status"))

    graph_artifact = resource(base, "ARTIFACT-REQUIREMENTS-GRAPH")
    generation = resource(
        base, f"ACTIVITY-GRAPH-GENERATION-{meta.get('model_version', 'unknown')}"
    )
    runner = resource(base, "AGENT-PIPELINE-RUNNER")
    graph.add((graph_artifact, RDF.type, REQ.ModelArtifact))
    graph.add((graph_artifact, RDF.type, PROV.Entity))
    graph.add((generation, RDF.type, REQ.GenerationActivity))
    graph.add((generation, RDF.type, PROV.Activity))
    graph.add((runner, RDF.type, PROV.SoftwareAgent))
    graph.add((generation, PROV.used, spec_artifact))
    graph.add((generation, PROV.generated, graph_artifact))
    graph.add((generation, PROV.wasAssociatedWith, runner))
    graph.add((graph_artifact, PROV.wasGeneratedBy, generation))
    graph.add((graph_artifact, PROV.wasDerivedFrom, spec_artifact))
    return graph


def copy_contracts(shapes_output: Path, queries_output: Path) -> list[Path]:
    skill = Path(__file__).resolve().parent.parent
    shapes_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill / "assets" / "requirements-shapes.ttl", shapes_output)
    ontology_output = shapes_output.parent / "requirements-graph-ontology.ttl"
    shutil.copy2(skill / "assets" / "requirements-graph-ontology.ttl", ontology_output)
    queries_output.mkdir(parents=True, exist_ok=True)
    copied = [shapes_output, ontology_output]
    for source in sorted((skill / "assets" / "sparql").iterdir()):
        if source.is_file():
            target = queries_output / source.name
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile canonical model-spec.json into one traceable RDF requirements graph."
    )
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", default="models/graph/requirements-graph.ttl")
    parser.add_argument("--shapes-output", default="models/graph/requirements-shapes.ttl")
    parser.add_argument("--queries-output", default="models/graph/queries")
    args = parser.parse_args()

    spec_path = Path(args.spec)
    spec = load_spec(spec_path)
    errors = validate_spec(spec, require_reviewed=True)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    graph = build_requirements_graph(spec, spec_path)
    output = Path(args.output)
    deterministic_turtle(graph, output)
    contracts = copy_contracts(Path(args.shapes_output), Path(args.queries_output))
    print(output)
    for path in contracts:
        print(path)
    print(f"triples={len(graph)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
