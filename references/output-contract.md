# Post-Model Development Input Contract

This contract applies after unified graph, BPMN, and OWL model review has passed. `docs/input/00-07` is a generated projection of the same approved `model-spec.json`, names the validated unified graph, and is not an independent AI summary or first modeling draft.

## 1. Required Files

Generate the complete `docs/input/00-07` set:

| Order | File | Purpose |
|---|---|---|
| 1 | `00-项目概述.md` | Project boundary, scope, roles, constraints, success criteria |
| 2 | `05-流程模型.md` | Process list, nodes, BPMN mapping, exceptions, interfaces |
| 3 | `02-领域模型.md` | Entities, ontology classes, attributes, relationships |
| 4 | `03-状态机.md` | Stateful entities and state transitions |
| 5 | `04-业务规则.md` | Business rules, decision logic, inputs, outputs |
| 6 | `01-能力目录.md` | Reusable system capabilities for PRD generation |
| 7 | `06-调研台账摘要.md` | Research facts, evidence, assumptions, source summary |
| 8 | `07-待确认问题.md` | Open questions, blockers, assumptions, defer/mock strategy |

## 2. Prerequisites

Before generating development-ready `docs/input/00-07`, verify:

- BPMN business elements use Chinese names and OWL resources have Chinese
  `rdfs:label` values with `xml:lang="zh-CN"`.
- Reviewed `.bpmn` file exists for each in-scope process.
- Reviewed `.owl` file exists for the in-scope domain ontology.
- Validated `models/graph/requirements-graph.ttl` exists with conforming SHACL,
  clean OWL-RL reasoning, and passing mandatory SPARQL queries.
- Approved `models/spec/model-spec.json` exists and passes reference validation.
- The spec names the exact reviewed Markdown sources used to compile it.
- State machine and rule lists have been checked against the model artifacts.
- Open questions that affect development are listed in `07-待确认问题.md` with blocking level and defer/mock strategy.

If prerequisites are not met, stop and output a model-review gap list.
Unapproved `docs/input` generation is not supported, even when the user asks
for a draft.

Generate populated files with:

```bash
python scripts/generate_project_input_from_spec.py \
  --spec models/spec/model-spec.json \
  --output docs/input \
  --requirements-graph models/graph/requirements-graph.ttl \
  --bpmn-dir models/bpmn \
  --owl models/ontology/project.owl
```

## 3. Output Order Rationale

Create flow, domain, state, and rule outputs before capability catalog:

```text
项目概述
  -> 流程模型
  -> 领域模型
  -> 状态机
  -> 业务规则
  -> 能力目录
  -> 调研台账摘要
  -> 待确认问题
```

`01-能力目录.md` is downstream's main product-analysis entry, but it should be derived from the preceding model files, not guessed from a feature wishlist.

## 4. Template Mapping

Use these bundled templates:

| Output | Template |
|---|---|
| `00-项目概述.md` | `assets/templates/project-input/00-项目概述.template.md` |
| `01-能力目录.md` | `assets/templates/project-input/01-能力目录.template.md` |
| `02-领域模型.md` | `assets/templates/project-input/02-领域模型.template.md` |
| `03-状态机.md` | `assets/templates/project-input/03-状态机.template.md` |
| `04-业务规则.md` | `assets/templates/project-input/04-业务规则.template.md` |
| `05-流程模型.md` | `assets/templates/project-input/05-流程模型.template.md` |
| `06-调研台账摘要.md` | `assets/templates/project-input/06-调研台账摘要.template.md` |
| `07-待确认问题.md` | `assets/templates/project-input/07-待确认问题.template.md` |

## 5. File Requirements

### 5.1 `00-项目概述.md`

Include:

- Project name and phase.
- Background and goals.
- In-scope and out-of-scope boundaries.
- Users, roles, external systems.
- Compliance/security/audit constraints.
- Non-functional requirements.
- Success and acceptance signals.
- Known assumptions and open boundary questions.

### 5.2 `05-流程模型.md`

Include:

- Approved source `.bpmn` file path and model version.
- Process overview table.
- Node-level table with `process_id`, `node_id`, BPMN element type, pool, lane, actor, trigger, input, output, previous/next nodes.
- Gateway conditions.
- Exception branches.
- Interface/message objects.
- Evidence and questions.

Minimum BPMN fields:

`process_id`, `node_id`, `bpmn_element_type`, `pool`, `lane`, `node_name`, `actor`, `trigger`, `input`, `output`, `prev_node_id`, `next_node_id`, `gateway_condition`, `exception_id`, `interface_id`, `evidence_id`, `question_id`.

### 5.3 `02-领域模型.md`

Include:

- Approved source `.owl` file path and model version.
- Entity/class list.
- Ontology class name.
- Parent class.
- Synonyms.
- Key attributes and data types.
- Relationships and cardinality.
- Lifecycle notes.
- Evidence and open questions.

Minimum ontology fields:

`entity_id`, `entity_name`, `ontology_class`, `parent_class`, `synonym`, `key_attributes`, `relationship`, `cardinality`, `source_process_id`, `source_node_id`, `evidence_id`, `question_id`.

### 5.4 `03-状态机.md`

Include one table per stateful entity or one consolidated table with:

`state_id`, `entity_id`, `from_state`, `trigger`, `to_state`, `actor`, `source_node_id`, `guard_rule_id`, `rollback_state`, `audit_required`, `evidence_id`, `question_id`.

If an entity is stateful but transition data is missing, create a `question_id`.

### 5.5 `04-业务规则.md`

Include:

`rule_id`, `rule_name`, `rule_type`, `process_id`, `node_id`, `entity_id`, `capability_id`, `trigger`, `inputs`, `outputs`, `logic`, `exception_behavior`, `evidence_id`, `question_id`.

Rules that are not confirmed must be marked as assumptions or open questions.

### 5.6 `01-能力目录.md`

Include:

`capability_id`, `capability_name`, `capability_type`, `business_goal`, `trigger_role`, `related_process_id`, `source_node_id`, `related_entity_id`, `related_rule_id`, `related_state_id`, `related_interface_id`, `input`, `output`, `normal_flow`, `exception_flow`, `permission_audit`, `acceptance_criteria`, `phase`, `evidence_id`, `question_id`.

Must-level capabilities require:

- Goal.
- Trigger role.
- Input/output.
- Normal flow.
- At least one exception flow or explicit statement that none is known.
- Given/When/Then acceptance criteria.
- Out-of-scope notes.
- Linked process/node or explicit global classification.

### 5.7 `06-调研台账摘要.md`

Include:

- Research source summary.
- Confirmed facts.
- AI inferences.
- Evidence list.
- Current manual/system process summary.
- Data gaps.
- Decision log.

Every fact should link to `evidence_id` where possible.

### 5.8 `07-待确认问题.md`

Include:

`question_id`, `question`, `category`, `scenario_id`, `process_id`, `node_id`, `capability_id`, `prd_id`, `current_assumption`, `blocking_level`, `mock_or_defer_strategy`, `owner`, `due_date`, `status`, `resolution`.

Blocking levels:

- `High`: blocks PRD or development; requires assumption plus mock/defer strategy.
- `Medium`: may remain open in the question ledger but must be confirmed before implementation or acceptance when it affects that scope.
- `Low`: can proceed with explicit assumption.

## 6. Development Input Completeness Gate

Return one of:

- `通过`: model baseline is approved and enough to generate all eight files.
- `部分通过`: do not generate `00-07`; split and approve an explicit baseline scope first.
- `不通过`: model baseline is absent or unresolved blockers affect development; output gap list first.

Gate checks:

- `.bpmn` and `.owl` source model artifacts exist or are explicitly waived with rationale.
- All artifacts carry the same `baseline_id` and `model_version`.
- Bidirectional node links are exact inverses for entities, states, rules, interfaces, capabilities, evidence, and questions.
- Every declared exception has a real BPMN path.
- Every process node is reachable from a start event and can reach an end event.
- Each Must capability is traceable to process nodes or marked global.
- Each core entity has key fields and relationships.
- Each stateful entity has state transitions or open questions.
- Each rule has trigger, inputs, outputs, and source.
- Each interface has direction, trigger, payload, frequency, owner, and failure handling or open questions.
- Each unresolved high blocker appears in `07-待确认问题.md`.
- No High blocker remains open in an approved development baseline.
- No full-automation behavior is assumed when input only says semi-automatic.
- The baseline manifest hashes match the current spec, complete graph package, BPMN, OWL, and all eight Markdown files.
- The baseline manifest also hashes all declared modeling-review Markdown and local evidence files.
- The unified graph, BPMN, OWL, and `00-07` exactly match deterministic projections regenerated from the current spec.
- SHACL conforms; OWL-RL consistency checks and mandatory SPARQL gates pass.
- Every approved critical object has evidence or a traceable open question.
- Closed questions contain resolution, close date, and confirmer.

## 7. Final Validation Checklist

Before final response:

- Confirm source unified graph, `.bpmn`, and `.owl` baselines are named in the output or gap list.
- Confirm all eight output files exist.
- Confirm filenames match exactly.
- Confirm IDs are stable and reused consistently.
- Confirm capability reuse is visible.
- Confirm facts, assumptions, and open questions are separated.
- Confirm generated output is PRD-ready but does not pretend unresolved questions are solved.
- Confirm `validate_traceability.py` returns PASS.
