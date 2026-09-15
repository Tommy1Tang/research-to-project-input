# Graph Engineering Contract

## 1. Purpose

The graph package is the semantic integration layer between reviewed research
and downstream projections. It connects process, domain, state, rule,
capability, interface, evidence, question, and provenance resources in one
queryable graph.

The source and projection roles are fixed:

```text
reviewed modeling Markdown
  -> models/spec/model-spec.json       authoring source
  -> models/graph/requirements-graph.ttl
                                      exact unified RDF projection
  -> SHACL + OWL-RL + SPARQL gates     semantic validation
  -> BPMN / domain OWL                 specialized model projections
  -> docs/input/00-07                  development-input projections
```

Do not edit the generated graph to fix a validation failure. Reopen the
pipeline, correct the reviewed Markdown or `model-spec.json`, and regenerate.

## 2. Graph Package

`models/graph/` must contain:

| Artifact | Role |
|---|---|
| `requirements-graph.ttl` | Unified requirements graph |
| `requirements-graph-ontology.ttl` | Requirements vocabulary and OWL axioms |
| `requirements-shapes.ttl` | SHACL data-quality constraints |
| `queries/query-manifest.json` | Executable query expectations |
| `queries/*.rq` | Named SPARQL validation and analysis queries |
| `inferred-graph.ttl` | Materialized OWL-RL closure |
| `shacl-report.ttl` | Machine-readable SHACL report |
| `reasoning-report.json` | Inference and consistency result |
| `sparql-results.json` | Query result sets and expectation results |
| `graph-validation-report.json` | Consolidated gate result |

All files are baseline-hashed. RDF output is canonicalized before deterministic
serialization so blank-node identifiers cannot create false drift.

## 3. Identity And Trace Rules

- Every modeled resource uses its stable business ID as the graph identity.
- IDs must match `model-spec.json`; graph-local replacement IDs are forbidden.
- Process nodes link to roles, entities, states, rules, exceptions, interfaces,
  capabilities, evidence, and questions with explicit RDF properties.
- Reverse trace is validated by the canonical spec and graph constraints.
- BPMN, domain OWL, and `00-07` remain independent projections of the same
  approved spec; the validated graph proves their integrated semantic context.
- `baseline_id` and `model_version` identify the complete graph/model package.

## 4. PROV-O Provenance

Use W3C PROV-O terms for origin and generation:

- `prov:Entity`: research evidence, `model-spec.json`, and generated graph.
- `prov:Activity`: unified graph generation.
- `prov:SoftwareAgent`: pipeline runner/generator.
- `prov:Person` or `prov:Agent`: evidence provider and reviewer.
- `prov:wasDerivedFrom`: modeled facts to evidence and graph to source spec.
- `prov:wasGeneratedBy`: graph to generation activity.
- `prov:wasAssociatedWith`: activity to software agent.
- `prov:wasAttributedTo`: approved source/model to reviewer when known.

An approved critical object without evidence or an explicit open question is a
model defect, not a provenance omission to be ignored.

## 5. SHACL Gate

`requirements-shapes.ttl` is executable policy, not documentation. The gate
must at least check:

- stable ID and name presence;
- process-node membership and trace links;
- stateful entity to transition coverage;
- rule trigger/input/output completeness;
- Must capability acceptance and trace coverage;
- evidence/question support;
- open High blocker prohibition for approved baselines.

`pyshacl` runs with OWL-RL inference enabled. A non-conforming report blocks
the `graph_validated` stage.

## 6. SPARQL Gate

Every query is registered in `queries/query-manifest.json` with:

- stable `query_id`;
- file;
- purpose;
- gate mode;
- expected result condition.

The bundled queries detect:

| Query | Intent |
|---|---|
| `QRY-GRAPH-001` | Find modeled resources without evidence/question trace |
| `QRY-GRAPH-002` | Find stateful entities without transitions |
| `QRY-GRAPH-003` | Find incomplete Must capabilities |
| `QRY-GRAPH-004` | Find open High blockers |
| `QRY-GRAPH-005` | Show capability reuse across process nodes |
| `QRY-GRAPH-006` | Produce cross-model impact paths |

Validation queries fail closed according to the manifest. Analysis queries may
return rows but must still execute successfully and persist their results.
Adding a query without a manifest entry, or a manifest entry without a query
file, is contract drift.

## 7. Inference Gate

Materialize an OWL-RL closure over the unified graph and graph ontology. Block
the pipeline when reasoning detects:

- any resource inferred as `owl:Nothing`;
- one resource typed as disjoint classes;
- a functional property with multiple distinct values.

The inference report records source, ontology, inferred, and output triple
counts. `inferred-graph.ttl` is an analysis artifact; it is not an authoring
source and must not be edited.

## 8. Human Model Review

At the model gate, the reviewer checks the complete package:

1. Unified graph resources and cross-object links match business meaning.
2. PROV-O links identify evidence, generation, and reviewer provenance.
3. SHACL report conforms.
4. Reasoning report has no consistency violation.
5. Mandatory SPARQL gates pass; analysis query results are plausible.
6. BPMN behavior matches process semantics.
7. Domain OWL matches classes, relations, states, and cardinalities.
8. Shared `capability_id` values represent genuine reuse.

The record in `models/review/06-模型审核记录.md` must name
`models/graph`, `models/bpmn`, and `models/ontology`, and include
`RDF` or `需求图` together with BPMN/OWL.

## 9. Development Readiness

`docs/input/00-07` may be generated only after the graph/model review gate.
Each generated file names the exact `requirements-graph.ttl`, BPMN directory,
and domain OWL path in its header.

Final validation reruns:

- exact graph reconstruction;
- SHACL;
- OWL-RL inference and consistency checks;
- all SPARQL queries;
- exact BPMN, OWL, and Markdown projection checks;
- complete baseline hash checks.

Only `development_ready` with `valid: true` is a development baseline.
