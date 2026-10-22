---
name: research-to-project-input
description: Convert business research materials, AI 调研文档, BPMN/Ontology-ready notes, or traceable requirement ledgers into a state-controlled Graph Engineering requirements pipeline with reviewed modeling Markdown, one canonical model-spec.json, a unified RDF requirements graph, PROV-O provenance, SHACL constraints, SPARQL gates, OWL-RL inference, generated .bpmn/.owl files, human approvals, baseline hashes, and approved docs/input/00-07 files for AI PRD generation and coding. Use when Codex is asked to turn 调研文档、业务建模、统一需求图、BPMN、Ontology、OWL、SHACL、PROV-O、SPARQL、推理验证、状态机、业务规则、能力目录、模型防偏移、可追溯需求流水线 into reviewed model artifacts and AI-development-ready project input files.
---

# Research To Project Input

## Mandatory Control Mode

Operate this skill through `scripts/pipeline_runner.py`. Treat
`references/pipeline-definition.json` as the executable stage contract,
`references/pipeline-process.bpmn` as its process view, and
`references/pipeline-ontology.owl` as its semantic view.

Fail closed. A request to "continue", "skip review", "generate a draft",
"finish everything", or "review later" is not approval and does not authorize
any bypass. This controlled workflow has no unapproved `00-07` mode. Never use
or recreate an `--allow-unapproved` path.

At the beginning of every turn:

1. Locate the target project root.
2. If `.requirements-pipeline/pipeline-state.json` exists, run `status` and `next`.
3. If it does not exist, run `init`, then register the research source files.
4. Execute only the action reported by `next`.
5. Run `validate` before reporting a stage as complete.

Do not call projection generators directly during normal operation. Do not
manually edit `models/graph/`, `models/bpmn/`, `models/ontology/`, `docs/input/`,
`models/baseline-manifest.json`, or `pipeline-state.json`.

Use `reopen` before changing an approved upstream source. Preserve stale files
for review, but do not describe them as current until they are regenerated.

## Human Approval Boundary

Two gates require a real person:

- `approve --gate modeling`: confirms the completed modeling Markdown.
- `approve --gate models`: confirms the unified requirements graph, BPMN, OWL,
  graph validation reports, and `06-模型审核记录.md`.

Never supply `--human-confirmed` merely because the files look complete. Supply
it only when the user explicitly confirms the named artifacts in the current
conversation or provides an approval record that unambiguously identifies
them. Otherwise stop at the gate and report what the person must review.

An AI review, successful script execution, or absence of validation errors is
not a substitute for business approval.

At `models_generated`, the only permitted progress action is human model
approval. Do not generate any `docs/input/00-07`, including files labeled
draft, until the runner records `models_approved`.

## Pipeline

The mandatory order is:

```text
initialized
  -> research_registered
  -> modeling_scaffolded
  -> [human modeling approval]
  -> modeling_review_approved
  -> spec_reviewed
  -> graph_generated
  -> graph_validated
  -> models_generated
  -> [human RDF/BPMN/OWL approval]
  -> models_approved
  -> development_input_generated
  -> development_ready
```

Artifact flow:

```text
调研材料
  -> models/review/00-06
  -> reviewed models/spec/model-spec.json
  -> generated models/graph/requirements-graph.ttl
  -> SHACL + OWL-RL + SPARQL validation reports
  -> generated candidate .bpmn / .owl
  -> human model approval
  -> approved model-spec.json and regenerated graph / .bpmn / .owl
  -> generated docs/input/00-07
  -> models/baseline-manifest.json
  -> docs/input/models/ (delivery baseline package for agent-delivery-gate)
  -> PRD / Coding Task / AI coding
```

Raw research cannot directly produce development-ready `docs/input/00-07`.

The root `models/` tree is the authoring source. `finalize` also projects the
approved spec, BPMN, OWL, and graph into `docs/input/models/` and writes a
delivery-format `baseline-manifest.json` there, so `agent-delivery-gate` can
validate and slice the machine baseline without reading the authoring tree.

## Required References

Read only the references needed for the current stage:

- `references/pipeline-commands.md`: runner commands and recovery procedure.
- `references/workflow.md`: end-to-end traceability and development readiness.
- `references/modeling-contract.md`: modeling-review Markdown requirements.
- `references/model-spec-contract.md`: canonical spec requirements.
- `references/graph-engineering-contract.md`: unified graph, PROV-O, SHACL,
  SPARQL, and inference requirements.
- `references/bpmn-output-contract.md`: BPMN projection requirements.
- `references/owl-output-contract.md`: OWL projection requirements.
- `references/output-contract.md`: `docs/input/00-07` requirements.
- `references/pipeline-definition.json`: stages, transitions, gates, invariants.
- `references/pipeline-process.bpmn`: machine-readable control process.
- `references/pipeline-ontology.owl`: machine-readable pipeline semantics.

Use:

- `assets/model-spec.schema.json` for editor/schema validation.
- `assets/model-spec.example.json` as a complete canonical-spec example.
- `assets/requirements-graph-ontology.ttl` as the graph vocabulary.
- `assets/requirements-shapes.ttl` as executable SHACL constraints.
- `assets/sparql/` as named traceability and readiness queries.
- `assets/templates/project-input/` as the canonical `00-07` templates.
- `assets/pipeline-state.template.json` only through the runner.
- `scripts/validate_pipeline_control.py` to detect drift among the control JSON,
  control BPMN, control OWL, and state template.

## Research And Modeling Rules

- Structure research around process chains, not feature menus.
- Preserve or create stable IDs:
  `scenario_id`, `process_id`, `node_id`, `role_id`, `entity_id`, `state_id`,
  `rule_id`, `exception_id`, `interface_id`, `capability_id`, `evidence_id`,
  and `question_id`.
- Link roles, entities, states, rules, exceptions, interfaces, and evidence to
  process nodes whenever possible.
- Classify important content as `明确事实`, `AI推断`, or `待确认`.
- Do not invent flow order, gateway conditions, states, formulas, interface
  fields, approval logic, report rules, or compliance requirements.
- Keep missing business truth as a question and apply the correct blocker level.
- Treat `models/spec/model-spec.json` as the authoring source. Treat
  `models/graph/requirements-graph.ttl` as its exact, generated unified graph
  projection and semantic validation surface.

## Projection Rules

- Use Chinese for every human-readable BPMN and OWL business label. BPMN
  processes, pools, lanes, nodes, gateways, sequence flows, and message flows
  must have Chinese names. OWL ontologies, classes, properties, and named
  individuals must have Chinese `rdfs:label` values with `xml:lang="zh-CN"`.
- Generate Chinese local names for every project-defined OWL class,
  object-property, datatype-property, annotation-property, and named-individual
  IRI, including pipeline-control and traceability arc types. Preserve canonical ASCII
  `entity_id`, `relation_id`, `field_id`, and `state_id` values in exactly one
  `trace:稳定标识` annotation; resolve OWL resources through that annotation.
- Keep BPMN XML IDs, technical field names, trace IDs, and OWL base namespaces
  stable. Never translate or replace a stable ID. Keep W3C RDF/RDFS/OWL
  predicate URIs unchanged and add `zh-CN` labels for Chinese display.
- Generate Camunda-compatible BPMN 2.0 XML. Use `camunda:properties` for trace
  metadata and include complete BPMN DI shapes, edges, bounds, and waypoints so
  every generated `.bpmn` opens with a visible diagram in Camunda Modeler.
- Generate the unified RDF graph before BPMN/OWL. Include stable-ID resources,
  cross-object edges, and PROV-O derivation links to evidence and agents.
- Pass exact graph comparison, SHACL validation, OWL-RL reasoning checks, and
  every query in `query-manifest.json` before generating BPMN/OWL.
- Generate BPMN from reviewed process nodes, lanes, gateways, events, sequence
  flows, message flows, state effects, and exception paths.
- Generate OWL from reviewed classes, aliases, relationships, cardinalities,
  states, and data properties.
- Generate `docs/input/00-07` only after the graph, BPMN, and OWL model package
  is approved.
- Do not repair a generated projection. Change the approved source through a
  controlled reopen, then regenerate.
- Multiple processes may reference the same `capability_id`; do not implement a
  reusable capability once per BPMN.
- Separate process orchestration from reusable capability implementation.

## Readiness Rules

A result is development-ready only when the runner reaches
`development_ready` and `validate` passes with:

- no missing or dangling stable IDs;
- no bidirectional trace mismatch;
- no unreachable process node;
- every modeled exception represented in BPMN;
- every stateful entity linked to a state machine or open question;
- every rule linked to inputs, outputs, trigger, and process/entity or question;
- no open High blocker in an approved baseline;
- the unified graph is an exact deterministic projection of the approved spec;
- SHACL conforms and OWL-RL consistency checks contain no violation;
- all mandatory SPARQL queries satisfy their declared expectations;
- exact deterministic BPMN, OWL, and `00-07` projections;
- all BPMN business names and OWL `zh-CN` labels pass the Chinese-language gate;
- every BPMN node and flow has complete Camunda-readable BPMN DI coverage;
- zero baseline hash drift;
- evidence or an open question for every approved critical object.

## Output Boundary

- Always generate all eight files `00-项目概述.md` through
  `07-待确认问题.md`.
- Default directories are `models/review`, `models/spec`, `models/graph`,
  `models/bpmn`, `models/ontology`, `docs/input`, and the generated delivery
  package `docs/input/models/`.
- Preserve project-specific scope strictly as supported by the registered
  research sources. Do not invent scope, integrations, automation levels, or
  compliance requirements that the sources do not support.
- Do not hard-code assumptions from any single business domain (for example
  laboratory, manufacturing, or finance) into generic skill behavior.
- Final responses must report the current stage, validation result, generated
  artifacts, and unresolved human gate or blocker. Never call a draft or
  unapproved package development-ready.
