# OWL Output Contract

Use this reference when creating `.owl` files.

## 1. Output Location

Default path:

```text
models/ontology/{ontology_name}.owl
```

## 2. Source of Truth

Generate candidate OWL only from a `reviewed` or `approved` `models/spec/model-spec.json` compiled from reviewed domain modeling Markdown. Do not maintain a separate ontology-only source spec and do not generate OWL directly from raw meeting notes.

## 3. Required OWL Content

Minimum supported ontology elements:

| Business item | OWL/RDF element |
|---|---|
| Entity/class | `owl:Class` |
| Parent class | `rdfs:subClassOf` |
| Entity relationship | `owl:ObjectProperty` |
| Entity attribute | `owl:DatatypeProperty` |
| Relationship source | `rdfs:domain` |
| Relationship target | `rdfs:range` |
| Business label | `rdfs:label` |
| Synonym | `skos:altLabel` |
| Comment | `rdfs:comment` |
| Cardinality | `owl:Restriction` |
| Trace relationship | custom `trace:*` annotations |

## 4. Chinese Modeling Language

- The ontology, every business class, object property, datatype property, trace
  annotation property, and named individual must have a Chinese
  `rdfs:label`.
- Chinese labels must use `xml:lang="zh-CN"`.
- Entity names, relationship Chinese names, attribute labels, and lifecycle
  state labels come from reviewed Chinese modeling Markdown.
- Every project-defined class, object-property, datatype-property,
  annotation-property, and named-individual IRI local name must be Chinese and
  derived deterministically from reviewed names.
- Preserve canonical ASCII entity, relation, field, and state IDs in exactly one
  non-empty `trace:稳定标识` annotation on each business OWL resource.
- OWL base namespaces, English class aliases, technical field names, and trace
  ID values remain stable technical identifiers.
- Keep W3C RDF/RDFS/OWL predicate URIs unchanged. Add Chinese `zh-CN` labels for
  display instead of redefining standard semantics.

## 5. Script Generation

Use the canonical example at `assets/model-spec.example.json`.

```bash
python scripts/generate_owl_from_spec.py \
  --spec models/spec/model-spec.json \
  --output models/ontology/project.owl
```

XSD datatype aliases:

`string`, `integer`, `decimal`, `boolean`, `date`, `dateTime`.

## 6. Validation Rules

- RDF/XML must parse as XML.
- Class/property IDs must be unique.
- Property domain and range classes should exist or be explicitly external.
- Chinese business IRIs must be unique. Fail generation when two stable IDs
  would produce the same Chinese IRI instead of merging the resources.
- Entity IDs, relation IDs, field IDs, and state IDs must be globally unique
  `trace:稳定标识` values and are the authoritative cross-artifact identity.
- Synonyms, process/node sources, evidence, questions, baseline ID, and model version must be annotations.
- Business-critical cardinality must produce OWL restrictions.
- State transitions must be represented as traceable OWL named individuals.
- Draft files must be named or marked as draft if not reviewed.
- Every OWL ontology/class/property/individual passes the `zh-CN` label gate.
