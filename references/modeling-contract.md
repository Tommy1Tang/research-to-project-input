# Modeling Review Contract

Use this contract before generating `.bpmn`, `.owl`, or `docs/input/00-07`.

All business-facing modeling names must be Chinese. Preserve stable ASCII IDs
beside Chinese names so reviewed Markdown can generate interoperable BPMN XML
IDs and Chinese business OWL IRIs. Store each OWL resource's canonical ID in
`trace:稳定标识` so readable IRIs do not weaken cross-artifact identity.

## 1. Modeling Output Stages

| Stage | Output | Purpose |
|---|---|---|
| A | `models/review/*.md` | Human-readable modeling review package |
| B | `models/spec/model-spec.json` | Approved canonical machine-readable model |
| C | `models/bpmn/*.bpmn` | Generated BPMN 2.0 process projection |
| D | `models/ontology/*.owl` | Generated OWL/RDF ontology projection |
| E | `docs/input/00-07` | Generated post-model AI development input |
| F | `models/baseline-manifest.json` | Approved hashes for source and projections |

## 2. Modeling Markdown Files

Default files:

| File | Purpose |
|---|---|
| `00-建模范围.md` | Scope, project boundary, model purpose, exclusions |
| `01-流程建模台账.md` | BPMN-ready process, lane, node, gateway, sequence, exception, message-flow data |
| `02-领域建模台账.md` | OWL-ready class, attribute, relationship, cardinality, synonym data |
| `03-状态与规则台账.md` | Entity lifecycle, state transitions, rules, guards, calculations |
| `04-接口与消息台账.md` | External systems, message objects, trigger, payload, sync/failure behavior |
| `05-证据与待确认问题.md` | Evidence, assumptions, open questions, blockers |
| `06-模型审核记录.md` | Review conclusion, approved scope, rejected scope, change log |

## 3. Modeling Readiness Gate

Return one of:

- `可生成模型`: enough to generate `.bpmn` and `.owl`.
- `可生成草案`: enough for draft model files; unresolved issues must be visible.
- `不可生成`: missing flow order, gateway rules, entity relationships, or core states.

Minimum BPMN readiness:

- Start/end event.
- Ordered process nodes.
- Actor/lane for each node.
- Node type.
- Inputs and outputs.
- Gateway branch conditions.
- Exception/return path.
- Message flow for external systems.
- Evidence or question for every uncertain item.

Minimum OWL readiness:

- Core classes.
- Parent class or category.
- Object properties.
- Data properties.
- Domain/range.
- Cardinality when business-critical.
- Synonyms or business terms.
- State-bearing classes identified.
- Evidence or question for every uncertain relationship.

## 4. Review Rules

Do not treat AI inference as approved fact.

Before generating development input:

- Business owner must confirm or explicitly defer high-impact process branches.
- Domain owner must confirm or explicitly defer core entity relationships.
- Model reviewer must confirm `.bpmn` and `.owl` are accepted as baseline.
- The canonical spec must be `reviewed` before unified graph and candidate
  model generation, and `approved` only after graph/BPMN/OWL package review.
- Any deferred point that affects development must be carried into `07-待确认问题.md`.
- The reviewed Markdown must be compiled into one valid `model-spec.json`.
- BPMN, OWL, and `00-07` must use the same `baseline_id` and `model_version`.
- Run cross-artifact validation before declaring the baseline development-ready.
- Approved baselines cannot contain open High blockers.
