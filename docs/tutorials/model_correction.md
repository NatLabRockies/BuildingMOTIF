---
jupytext:
  cell_metadata_filter: -all
  formats: md:myst
  text_representation:
    extension: .md
    format_name: myst
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

# Model Correction

Validation identifies gaps; it does not prove which real-world fact should be
added. Use repair proposals to understand the smallest possible change, check
that change against your source evidence, then apply it and validate again.

This tutorial continues from the model-validation tutorial. It uses the default
`pyshifty` engine, whose validation result contains structured failures and
soundness-gated repair proposals.

## Setup

```{code-cell}
from rdflib import Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model

bm = BuildingMOTIF("sqlite://")
BLDG = Namespace("urn:bldg/")
model = Model.create(BLDG, description="A simple building model")

# `constraints` and Brick ship with BuildingMOTIF. Guideline 36 is a
# repository library, so this tutorial expects a checkout for that directory.
Library.from_ontology("constraints/constraints.ttl")
Library.from_ontology("brick/Brick.ttl", run_shacl_inference=False)
Library.from_directory("../../libraries/ashrae/guideline36")

model.graph.parse("tutorial2_model.ttl", format="turtle")
manifest = Library.from_ontology("tutorial2_manifest.ttl")
model.manifest.add(manifest)
```

## Read the current failures

```{code-cell}
ctx = model.validate()
print("Conforms?", ctx.conforms)

for focus, failures in ctx.diffset.items():
    print(focus or "the whole model")
    for failure in failures:
        print(" -", failure.reason())
```

Each failure concerns one focus node and one requirement. Fix one at a time:
adding a missing part can activate requirements on that new part, while another
repair can make later failures disappear.

## Review proposals before changing data

The default engine exposes proposals on each failure. A proposal may reuse an
existing node, add a small graph, or (for constraints such as `sh:not`) delete
a graph. `is_sound` means it introduces no new SHACL violation; it is not
evidence that the proposed equipment or point exists in the building.

```{code-cell}
ahu = BLDG["Core_ZN-PSC_AC"]
failure = next(iter(ctx.get_diffs_for_entity(ahu)))

for proposal in failure.proposals():
    print(
        proposal.origin,
        "sound=", proposal.is_sound,
        "progress=", proposal.is_progress,
        "reuses=", sorted(map(str, proposal.reused_nodes)),
        "adds=", len(proposal.additions),
        "deletes=", len(proposal.deletions),
    )
```

Use the proposal as a question for the source documents: for example, “Does
this AHU really have this supply fan, and what is its identifier?” Do not use a
generated identifier merely to make validation pass.

## Preview, confirm, apply, re-validate

Previewing is read-only. It shows the validation run that would result from a
proposal without changing the model.

```{code-cell}
selected = failure.proposals()[0]
preview = ctx.preview(selected)
print("Would conform?", preview.conforms)
```

After confirming the assertion from project evidence, apply its delta to the
model and immediately validate again. The explicit loop makes the state change
visible, including deletions.

```{code-cell}
# Only run this after checking the proposal against source evidence.
for triple in selected.deletions:
    model.graph.remove(triple)
model.add_graph(selected.additions)

ctx = model.validate()
print("Conforms after the confirmed change?", ctx.conforms)
```

## Turn a chosen addition into a template

For a reusable correction pattern, lift a selected addition into a template.
Freshly minted repair nodes become template parameters; the original focus and
reused nodes stay concrete. A deletion-only proposal has no template body and
returns `None`.

```{code-cell}
repair_template = selected.as_template()
if repair_template is not None:
    print(repair_template.name)
    print(sorted(repair_template.parameters))
```

Templates make a repeated, evidence-backed pattern easier to fill. They do not
replace the need to confirm every building-specific identifier and relationship.
