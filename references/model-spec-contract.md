# Unified Model Spec Contract

Use one approved UTF-8 JSON file as the machine-readable source for `.bpmn`, `.owl`, and `docs/input/00-07`.

Default path:

```text
models/spec/model-spec.json
```

The approved modeling Markdown remains the human review source. Compile it into `model-spec.json` only after review. Do not edit generated BPMN, OWL, or generated sections of `00-07` independently.

Use `assets/model-spec.schema.json` for structural editor validation and `scripts/validate_model_spec.py` for cross-reference and semantic gates.

## Required Top-Level Objects

| Key | Purpose |
|---|---|
| `meta` | Project identity, model version, baseline ID, review status |
| `scope` | Goals, in-scope, out-of-scope, constraints |
| `roles` | Stable process roles |
| `scenarios` | End-to-end business scenarios |
| `processes` | BPMN processes, participants, lanes, nodes, flows, exceptions |
| `entities` | Ontology classes and attributes |
| `relations` | Ontology object properties and cardinalities |
| `states` | Entity state transitions |
| `rules` | Business and decision rules |
| `interfaces` | External exchanges and failure behavior |
| `capabilities` | Reusable system abilities derived from process needs |
| `evidence` | Traceable research evidence |
| `questions` | Unresolved points and defer/mock strategies |

## Meta Gate

Development-ready generation requires:

```json
{
  "meta": {
    "project_id": "PROJECT-001",
    "project_name": "工单处理系统（示例）",
    "phase": "一期",
    "model_version": "1.0.0",
    "baseline_id": "BASELINE-001",
    "review_status": "approved",
    "reviewer": "Business owner / model reviewer",
    "review_date": "2026-07-30",
    "review_files": [
      "models/review/00-建模范围.md",
      "models/review/01-流程建模台账.md",
      "models/review/02-领域建模台账.md",
      "models/review/03-状态与规则台账.md",
      "models/review/04-接口与消息台账.md",
      "models/review/05-证据与待确认问题.md",
      "models/review/06-模型审核记录.md"
    ],
    "ontology_iri": "https://example.com/ontology/project#",
    "ontology_id": "project-ontology"
  }
}
```

Allowed `review_status` values:

- `draft`: modeling work is incomplete.
- `reviewed`: modeling Markdown and canonical spec may generate and validate the
  unified graph, then generate candidate BPMN/OWL.
- `approved`: the unified graph, validation reports, BPMN, and OWL have passed
  model review and may generate development-ready `00-07`.

An approved spec requires reviewer, non-future review date, review source files, and no open High blocker.

A closed question requires `resolution`, `closed_date`, and `closed_by`.

## Chinese Business Labels

The reviewed spec must provide Chinese business labels for BPMN and OWL:

- Chinese project, process, participant, lane, node, flow, and message-flow names.
- Chinese entity names, relationship `name_cn`, attribute labels, and lifecycle
  source state, target state, and trigger names.
- External abbreviations need a Chinese business qualifier, such as `SAP/OA系统`.
- Stable IDs, class aliases, and technical field names remain ASCII.
- Business OWL IRI local names are generated in Chinese; stable IDs are stored
  separately as `trace:稳定标识`.

## Stable ID Rules

Use globally stable IDs. Never regenerate an ID because a display name changes.

| Object | Recommended prefix |
|---|---|
| Scenario | `SC-` |
| Process | `PROC-` |
| Node | `ND-` |
| Flow | `FLOW-` |
| Role | `ROLE-` |
| Entity | `ENT-` |
| Relation | `REL-` |
| State transition | `ST-` |
| Rule | `R-` |
| Exception | `EX-` |
| Interface | `IF-` |
| Capability | `CAP-` |
| Evidence | `EV-` |
| Question | `Q-` |

All references must resolve to an object in the same spec. Cross-cutting items may use an empty process/node link but must include evidence or a question.

When both directions are stored, they must be exact inverses. For example, a node that references `CAP-001` must appear in `CAP-001.node_ids`; the same rule applies to entities, states, rules, interfaces, evidence, and questions.

## Process Shape

Each process requires:

- `process_id`, `name`, `trigger`, and `end_result`.
- At least one start event and one end event.
- `participants` and optional lanes.
- Ordered `nodes` and `flows`.
- Gateway conditions and related `rule_ids`.
- `message_flows` for external exchanges.
- `exceptions` for reject, return, cancel, timeout, or manual intervention paths.

Each node may link:

```text
capability_ids
entity_ids
rule_ids
state_ids
interface_ids
exception_ids
evidence_ids
question_ids
```

These links are embedded into BPMN `extensionElements`.

Every decision gateway needs at least two outgoing paths. Every exception needs `path_flow_ids` that point to real BPMN sequence flows.

Every node must be reachable from a start event and able to reach an end event.

In an approved baseline, roles, scenarios, processes, nodes, flows, entities, relations, states, rules, interfaces, capabilities, and attributes require `evidence_ids` or `question_ids`.

## Ontology Shape

Each entity requires:

- `entity_id`, `name`, `class_name`, `definition`.
- Parent entity or `Thing`.
- Synonyms.
- Key attributes with datatype and required flag.
- Stateful/core flags.
- Evidence or questions.

Each relation requires:

- `relation_id`, `name_en`, `name_cn`.
- `source_entity_id`, `target_entity_id`.
- Cardinality and required flag.
- Process/node/evidence/question links.

Entity and relation Chinese names generate readable OWL IRIs. Entity and
relation IDs remain the authoritative identity through `trace:稳定标识`;
English predicates remain annotations.

## Capability Shape

One reusable capability has one `capability_id`, even when many BPMN nodes use it.

Must-level capabilities require:

- Goal, trigger role, inputs, outputs.
- Normal flow and exception flow or an explicit statement that no exception is known.
- Acceptance criteria.
- Process/node/entity/rule/state/interface trace links.
- Evidence or a question.

## Generated Artifact Policy

Treat these as generated projections:

```text
models/bpmn/*.bpmn
models/ontology/*.owl
docs/input/00-07
models/baseline-manifest.json
```

Change the approved modeling Markdown or `model-spec.json`, regenerate all affected projections, review the diff, and create a new baseline. Never patch one projection to hide a mismatch.
