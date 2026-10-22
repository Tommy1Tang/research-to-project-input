# Workflow Reference

## 1. Core Pipeline

The state machine in `pipeline-definition.json` controls execution.
`pipeline-process.bpmn` and `pipeline-ontology.owl` are process and semantic
views of the same contract; `pipeline_runner.py` is the only normal execution
entry. Every resumed AI turn must run `status` and `next` before changing
artifacts.

Use one traceable pipeline from research to coding:

```text
业务调研
  -> 调研台账
  -> AI 调研文档
  -> 建模用 Markdown 草案
  -> 人工确认
  -> reviewed model-spec.json
  -> 统一 RDF 需求图 + PROV-O
  -> SHACL + OWL-RL + SPARQL 门禁
  -> .bpmn / .owl
  -> 建模审核通过
  -> approved model-spec.json
  -> docs/input/00-07
  -> docs/input/models/ delivery baseline package
  -> 跨文件一致性校验
  -> 基线哈希锁定
  -> 能力目录
  -> PRD
  -> Coding Task
  -> 代码 / API / 页面 / 测试
```

The stable trace chain is:

```text
scenario_id
  -> process_id
  -> node_id
  -> capability_id
  -> prd_id
  -> task_id
  -> code_module / api / page / job / test_case
```

`docs/input/00-07` is a post-model development input set. Compile reviewed
Markdown into one canonical model spec, project it into one unified RDF graph,
validate that graph, generate `.bpmn`, `.owl`, and `00-07` from the same
approved source, then validate and hash the complete baseline.

Persist these execution stages:

```text
initialized
  -> research_registered
  -> modeling_scaffolded
  -> modeling_review_approved
  -> spec_reviewed
  -> graph_generated
  -> graph_validated
  -> models_generated
  -> models_approved
  -> development_input_generated
  -> development_ready
```

`modeling_scaffolded -> modeling_review_approved` and
`models_generated -> models_approved` are human gates. Automated execution
must stop at them.

## 2. Research Structuring

Do not treat research notes as a feature list. Structure them around the process chain.

Minimum research objects:

| Object | Purpose |
|---|---|
| `scenario_id` | Business scenario or end-to-end case |
| `process_id` | Process chain under the scenario |
| `node_id` | Business or system step in the process |
| `role_id` | Process participant or responsibility lane |
| `entity_id` | Business object touched by the node |
| `state_id` | Entity state before/after a trigger |
| `rule_id` | Business decision, validation, calculation, or assignment rule |
| `exception_id` | Exception branch, rollback, rejection, rework, revision |
| `interface_id` | External system or message/file/API interaction |
| `evidence_id` | SOP, screenshot, Excel, report template, interview source |
| `question_id` | Unresolved or disputed item |

Every role, entity, state, rule, exception, and interface should be linked to a `node_id` when possible. Cross-cutting items may be marked as global but still need evidence.

## 3. BPMN Extraction

To support BPMN, collect:

- Process start event and trigger source.
- End event and expected outcome.
- Pool and lane for each role/system.
- Ordered tasks and service/user/manual/script tasks.
- Gateway conditions and branch rules.
- Message flows between systems.
- Exceptions, return paths, timeout paths, cancellation, revision, rework.
- State changes caused by process nodes.

Mapping:

| Research item | BPMN element |
|---|---|
| Trigger | Start event |
| Node action | Task |
| Role/process participant | Lane |
| External system | Pool or participant |
| Business decision | Exclusive/inclusive gateway |
| Parallel work | Parallel gateway |
| Interface exchange | Message flow |
| Exception branch | Boundary event or exception path |
| Completion | End event |

## 4. Ontology Extraction

To support ontology, collect:

- Entity/class names and synonyms.
- Parent class or category.
- Key attributes and data types.
- Relationships and cardinality.
- Lifecycle states.
- Ownership, responsibility, and permissions.
- Evidence and source vocabulary.

Minimum relationship fields:

| Field | Meaning |
|---|---|
| `relation_id` | Stable relationship ID |
| `source_entity_id` | Source entity |
| `relation_name_en` | English predicate |
| `relation_name_cn` | Chinese business phrase |
| `target_entity_id` | Target entity |
| `cardinality` | `1:1`, `1:N`, `N:N`, optional/required |
| `source_process_id` | Where the relationship appears |
| `evidence_id` | Evidence |
| `question_id` | Open question if uncertain |

## 5. State and Rule Extraction

For each stateful entity, capture:

- Entity.
- Current state.
- Trigger event.
- Source state.
- Target state.
- Actor/system.
- Guard condition.
- Related rule.
- Audit requirement.
- Rollback/rework path.

For each business rule, capture:

- Rule type: validation, calculation, assignment, judgment, permission, audit, notification, report selection, interface mapping.
- Trigger process/node.
- Inputs.
- Outputs.
- Decision logic.
- Exception behavior.
- Evidence.
- Open question if not confirmed.

## 6. Model Baseline Before Development Input

Before generating `docs/input/00-07`, ensure:

- The unified requirements graph is the exact projection of the reviewed spec.
- SHACL conforms, OWL-RL consistency checks pass, and mandatory SPARQL queries pass.
- Each process has a reviewed `.bpmn` file or an approved BPMN-equivalent model table.
- Each ontology/domain scope has a reviewed `.owl` file or an approved OWL-equivalent model table.
- Gateway conditions, state transitions, and business rules have owner confirmation or are explicitly deferred.
- Open issues that affect development are listed as blockers, not silently converted into assumptions.
- The canonical model spec passes reference validation.
- Candidate graph/BPMN/OWL models were generated from a `reviewed` spec, then
  the same spec was marked `approved` only after complete model-package review.
- Generated graph, BPMN, and OWL trace annotations match the spec.
- Every declared exception has a modeled BPMN path.
- No approved baseline contains an open High blocker.
- Every node is reachable from a start and can reach an end.
- Final graph, BPMN, OWL, and `00-07` match deterministic projections regenerated from the approved spec.

If the user asks to generate `docs/input/00-07` before model approval, stop at
the human gate and provide the model-review checklist. A request for draft
output is not model approval and must not bypass the runner.

After generation:

- Create `models/baseline-manifest.json`.
- Include reviewed Markdown and local evidence sources in the manifest.
- Export `docs/input/models/` and its delivery-format manifest for
  `agent-delivery-gate`; the root `models/` tree remains the authoring source.
- Validate complete ID coverage, semantic links, scope boundaries, and hashes.
- If any generated artifact is edited independently, mark the baseline stale and regenerate from the source.
- Use `pipeline_runner.py reopen` before changing an approved upstream source.
- Keep `.requirements-pipeline/pipeline-state.json` as the execution record;
  do not edit it manually.
- Treat project-local hooks as guardrails that block direct generated-file
  writes and stop a turn when recorded artifacts have drifted.

## 7. Capability Abstraction

Generate capabilities after process, entities, states, and rules are known.

Capability extraction principles:

- One reusable system ability should have one `capability_id`.
- If several BPMN processes use the same ability, reference the same `capability_id`.
- Do not make every process node a separate feature.
- Separate reusable capability from process orchestration.
- A capability must state trigger, actor, input, output, normal flow, exception flow, data objects, rules, permissions, audit, and acceptance criteria.

Common capability types:

| Type | Examples |
|---|---|
| Master data | organization, user, product, project, unit, document template |
| Workflow | task acceptance, task assignment, review, approval |
| Data processing | result parsing, calculation, rounding, judgment |
| Reporting | report data preparation, report dataset review |
| Compliance | audit trail, electronic signature, permission control |
| Integration | external task import, status sync, message notification |

## 8. Semi-Automatic Boundary

When the research source describes a semi-automatic boundary (system prepares
data, human applies it):

- System may collect, normalize, calculate, aggregate, and present data.
- Human users still confirm, apply, compose, or finalize output content unless
  full automation is explicitly in scope.
- Record which data fields are system-generated and which are manually confirmed.
- Capture output template, data source, calculation rule, judgment rule,
  review rule, revision rule, and comparison method with the manual baseline.

Do not silently upgrade a semi-automatic boundary into full automation.

## 9. Development Readiness

Only generate PRD-ready output when:

- Project boundary is clear.
- `.bpmn` and `.owl` model artifacts are approved or explicitly accepted as development baseline.
- Main process chain has ordered nodes.
- Core entities and relationships are explicit.
- Stateful entities have state transitions.
- Key rules have inputs and outputs.
- Interfaces have direction, trigger, payload, frequency, owner, and failure handling or open questions.
- Acceptance criteria can be written in Given/When/Then style.
