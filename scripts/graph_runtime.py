from __future__ import annotations

import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parent.parent
VENDOR = SKILL_ROOT / "vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

try:
    from owlrl import DeductiveClosure, OWLRL_Semantics
    from pyshacl import validate as shacl_validate
    from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
    from rdflib.compare import to_canonical_graph
    from rdflib.namespace import OWL, PROV, XSD
except ImportError as exc:
    raise RuntimeError(
        f"RDF toolchain is incomplete under {VENDOR}. "
        "Restore the skill vendor directory before graph generation."
    ) from exc


REQ = Namespace("https://openai.example/requirements-schema#")
SH = Namespace("http://www.w3.org/ns/shacl#")


def deterministic_turtle(graph: Graph, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = to_canonical_graph(graph).serialize(format="nt")
    lines = sorted(line for line in serialized.splitlines() if line.strip())
    output.write_text(
        "# Deterministic N-Triples serialization; valid Turtle syntax.\n"
        + "\n".join(lines)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def load_rdf(path: Path) -> Graph:
    graph = Graph()
    graph.parse(path, format="turtle")
    return graph
