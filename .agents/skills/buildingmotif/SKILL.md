---
name: buildingmotif
description: Use BuildingMOTIF to validate, repair, and build building and water-system metadata models (Brick/223P/WaTr/SHACL), and to store, index, and retrieve source documents as repair evidence. Covers algebraic repair, templates, application shapes, SCADA and BACnet point lists, ontology exploration, and the Docling/Qdrant knowledge service. Use when the user mentions BuildingMOTIF, Brick, 223P, WaTr, SHACL, repair proposals or witnesses, point lists, equipment schedules, knowledge documents, evidence retrieval, or whether a model is sufficient for an application.
---

# BuildingMOTIF

Use BuildingMOTIF to answer whether a physical-system metadata model contains enough
information for an application, explain what is missing, and add only facts supported by
evidence.

## Start here

Before inspecting the package environment:

1. Identify the operation: **validate**, **repair**, **build**, **author requirements**, or
   **manage knowledge documents**.
2. Identify the target vocabulary: **Brick**, **223P**, or **WaTr-on-223P**.
3. Identify the evidence format: existing RDF, structured table, encoded labels, or
   documents.
4. Read only the references selected by the router.

## Workflow router

| Task | Read |
|---|---|
| Install/configure BuildingMOTIF; recover from import, environment, ontology, or library-loading failures | `references/setup.md` |
| Validate a model, report failures, list templates, or inspect a shape library | `references/validation.md` |
| Build a model with `Model.create`, templates, direct triples, and a durable exploration/build script | `references/building_models.md` |
| Verify Brick terms and class shapes | `references/brick_vocabulary.md` |
| Model 223P topology, properties, sensors, roles, domains, or media | `references/223p_vocabulary.md` |
| Model WaTr equipment, processes, water media, constituents, or WaTr-on-223P patterns | `references/watr_vocabulary.md` |
| Build from point lists, SCADA/BMS labels, BACnet objects, schedules, or source tables | `references/point_labels.md` + `references/building_models.md` + the target vocabulary reference |
| Propose or apply soundness-gated repairs | `references/repair.md` + `references/evidence.md` |
| Find evidence in local files or retrieved document chunks | `references/evidence.md` |
| Upload, index, retrieve, update, or delete documents through `bm.knowledge` | `references/knowledge_service.md` + `references/evidence.md` |
| Write SHACL shapes, application requirements, or manifests | `references/writing_shapes.md` |
| Write YAML or SHACL-derived templates | `references/writing_templates.md` |
| Find, choose, fill, or match templates | `references/templates.md` |
| Resolve `owl:imports`, configure OntoEnv, or inspect the graph store | `references/ontology_imports.md` |

For ontology term discovery, use `scripts/inspect_ontology.py` or keep equivalent
namespace-preserving queries in the task's durable build script. Never rebuild a discovered
IRI from only its local name.

## Guardrails

### Inspect the input before the checkout

A WaTr SCADA CSV routes to `point_labels.md`, `watr_vocabulary.md`, and
`223p_vocabulary.md`; it does not route to Brick merely because it is a point list. If code
execution is required, check package provenance once:

```bash
python -c "import buildingmotif; print(buildingmotif.__file__)"
```

If that succeeds, do not inspect the checkout's branch, `pyproject.toml`, or package files
unless the user is developing BuildingMOTIF or a required API is missing. If it fails, stop
ad hoc probing and follow `references/setup.md`.

### Use one durable script

Create one BuildingMOTIF Python script early and use it as the executable record of the
investigation. Keep configuration, source inventory, ontology loading, namespace-safe term
queries, verified mappings, representative construction, validation, audit counts, and
serialization in that script. Refine and rerun it as questions are answered. Do not leave
load-bearing discoveries in shell one-liners, temporary REPL fragments, or prose that the
final model cannot reproduce.

Keep exploration separate from assertion. Finding an ontology term, a retrieved chunk, or
a repair that passes a logical gate does not prove the corresponding equipment, point,
connection, or property exists in the real system.

### Never invent metadata

Use the loop **gap → evidence → user → apply**. Bind real identifiers from point lists,
submittals, schedules, BACnet exports, or retrieved documents. When evidence is absent or
ambiguous, ask the user. Never silently accept a repair because it validates, and never
present a synthesized node as if it were discovered.

## Build loop: prove a pattern before scaling it

For every build from repeated records:

1. Inventory distinct equipment IDs, source tokens, units, I/O types, and unresolved
   values.
2. Ask once about material facts the source does not establish, such as topology, process
   order, or command-versus-status meaning.
3. Verify only the required ontology terms, preserving their complete IRIs and namespaces.
4. Build one representative instance of every repeated pattern. For 223P/WaTr data, cover
   numeric and enumerated properties and observable and actuatable behavior when present.
5. Validate the representative graph and fix the reusable pattern.
6. Expand it across the input, report mapped/unmapped coverage, and validate the complete
   model.
7. Re-run the script from the original inputs in a fresh temporary database before handing
   off the serialized graph.

## Validation and repair loop

Validation is read-only; repair changes the model. For repair requests:

1. Validate and read `ctx.diffset` in domain terms.
2. Choose one failure/witness and inspect its useful proposals.
3. Preview the proposal with `ctx.preview(proposal)`; this does not change the model.
4. Find evidence and obtain user confirmation when needed.
5. Apply one confirmed repair and re-validate immediately.
6. Repeat until the model conforms or the evidence shows the requirement is inappropriate.

Do not batch unrelated repairs before validation. Fixing one failure can activate shapes on
new nodes and reveal additional requirements.

## Minimal setup

Use BuildingMOTIF as an installed package. See `references/setup.md` for installation,
deterministic environment recovery, persistence, OntoEnv, and library locations.

```python
from buildingmotif import BuildingMOTIF

with BuildingMOTIF("sqlite:///buildingmotif.db") as bm:
    # create/load models and libraries; the context commits on success
    ...
```

The default `pyshifty` engine (0.4.4 on this integration branch) provides algebraic
validation and repair witnesses. A proposal is a candidate graph change, not evidence
that equipment exists. Report results in domain language—“VAV-1 has no temperature
sensor” is more useful than only reporting a raw SHACL path—while retaining technical
diagnostics for inspection.

## Authoritative material

- Documentation: <https://buildingmotif.readthedocs.io/>
- Source, notebooks, and API documentation: <https://github.com/NatLabRockies/BuildingMOTIF>
- 223P ontology: <https://open223.info/223p.ttl>
- WaTr ontology: <https://watermetadata.org/water.ttl>
