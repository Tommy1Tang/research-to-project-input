# BPMN Output Contract

Use this reference when creating `.bpmn` files.

## 1. Output Location

Default path:

```text
models/bpmn/{process_id}.bpmn
```

## 2. Source of Truth

Generate candidate BPMN only from a `reviewed` or `approved` `models/spec/model-spec.json` compiled from reviewed modeling Markdown. Do not maintain a separate BPMN-only source spec and do not generate BPMN directly from raw meeting notes.

## 3. Required BPMN Elements

Minimum supported BPMN 2.0 elements:

| Business item | BPMN element |
|---|---|
| Process start | `bpmn:startEvent` |
| Process completion | `bpmn:endEvent` |
| Manual/user step | `bpmn:userTask` or `bpmn:manualTask` |
| System step | `bpmn:serviceTask` or `bpmn:scriptTask` |
| Business decision | `bpmn:exclusiveGateway` |
| Parallel work | `bpmn:parallelGateway` |
| Flow order | `bpmn:sequenceFlow` |
| External interaction | `bpmn:participant` and `bpmn:messageFlow` |
| Trace relationship | `bpmn:extensionElements` with `trace:links` |

## 4. Chinese Modeling Language

- Every process, participant/pool, lane, event, task, gateway, sequence flow,
  and message flow must have a Chinese business `name`.
- External product names and abbreviations must include a Chinese qualifier,
  for example `SAP/OA系统`, not only `SAP/OA`.
- Conditions may retain formulas or technical expressions, but the associated
  gateway and flow names must be Chinese.
- Stable `process_id`, `node_id`, `flow_id`, XML `id`, and trace IDs remain
  ASCII and must not be translated.

## 5. Script Generation

Use the canonical example at `assets/model-spec.example.json`.

```bash
python scripts/generate_bpmn_from_spec.py \
  --spec models/spec/model-spec.json \
  --output-dir models/bpmn
```

Supported node `type` values:

`startEvent`, `endEvent`, `userTask`, `manualTask`, `serviceTask`, `scriptTask`, `businessRuleTask`, `receiveTask`, `sendTask`, `exclusiveGateway`, `inclusiveGateway`, `parallelGateway`, `intermediateCatchEvent`, `intermediateThrowEvent`, `boundaryErrorEvent`, `subProcess`.

## 6. Camunda Compatibility

- Declare `xmlns:camunda="http://camunda.org/schema/1.0/bpmn"`.
- Store baseline, model version, and stable trace IDs as Chinese-named
  `camunda:properties`; do not use an unknown custom extension namespace.
- Include one `bpmndi:BPMNShape` with `dc:Bounds` for every participant, lane,
  event, task, gateway, and subprocess.
- Include one `bpmndi:BPMNEdge` with `di:waypoint` values for every sequence
  flow and message flow.
- Set the BPMN plane to the collaboration when participants exist; otherwise
  set it to the process.
- A file that parses as XML but has missing BPMN DI is not accepted.

## 7. Validation Rules

- XML must parse.
- IDs must be unique.
- Each sequence flow source and target must exist.
- Each process must have at least one start event and one end event.
- Every node must preserve the spec `node_id`.
- Node trace links must exactly match capability, entity, rule, state, interface, exception, evidence, and question references in the spec.
- Every decision gateway has at least two outgoing paths.
- Every declared exception is represented by one or more sequence flows linked through `exceptionIds`.
- Baseline ID and model version must match the canonical spec.
- Draft files must be named or marked as draft if not reviewed.
- Every named BPMN business element passes the Chinese-label validation gate.
- Every node/participant/lane has exact BPMN DI shape coverage.
- Every sequence/message flow has exact BPMN DI edge coverage.
- Camunda extension properties exist and preserve trace metadata.
