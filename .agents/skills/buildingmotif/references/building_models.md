# Building a model with BuildingMOTIF

This is the script-first guide for **constructing** a building model — not validating an
existing one (`validation.md`) or fixing one (`repair.md`), but authoring one from scratch.
BuildingMOTIF has machinery for exactly this, and you should use it rather than handwriting
Turtle: a reusable **template library**, `Model.create` for the model shell, and
`TemplateBuilderContext` for wiring templates together and compiling them into one graph.
If the source is a point list, BMS naming convention, BACnet object list, or equipment
schedule, read `point_labels.md` first: the first job is mapping source tokens to verified
Brick classes (`brick_vocabulary.md`), not writing templates.

Source of truth on disk: `buildingmotif/model_builder.py` (`TemplateBuilderContext`,
`TemplateWrapper`), `buildingmotif/dataclasses/model.py` (`Model.create`/`from_graph`),
`buildingmotif/dataclasses/library.py`/`template.py`. The canonical walk-through is the
`notebooks/Model-Builder.ipynb` notebook on GitHub — mirror its structure.

## Why use the machinery (don't hand-write Turtle)

You *can* add triples to a model directly (`model.graph.add((s, p, o))`), and for a few
ad-hoc connections that's fine. But a model built by evaluating templates is:

- **Reusable** — the template library is written once and fills many models; the same
  `vav-cooling-only` template builds every VAV in every building.
- **Consistent** — the class structure, required points, and parts come from the template
  body, so you can't forget the `brick:hasPart` or mistype a class IRI the way you can in
  raw triples.
- **Validatable by construction** — templates decompiled from shapes
  (`writing_templates.md`) produce graphs that already conform to the shape they came
  from, so the model is closer to valid before you ever call `validate()`.
- **Evidence-anchored** — template parameters are the slots you bind to *real* identifiers
  from the user's documents (`evidence.md`), rather than minting names inline.

The `model_creation` tutorial puts it plainly: ontologies/schemas/rules belong in
**Libraries**, not Models. The model is the *filling* of templates from those libraries.

## The four-piece workflow

```python
from rdflib import Namespace
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.model_builder import TemplateBuilderContext
from buildingmotif.namespaces import BRICK

bm = BuildingMOTIF("sqlite://")   # tables are created automatically
BLDG = Namespace("urn:bldg/")

# 1. Create (or load) a reusable template LIBRARY.
#    Either write one (writing_templates.md), reuse a repo library (guideline36, 223p),
#    or just load Brick — its class templates (brick:AHU, brick:VAV, ...) are decompiled
#    from the ontology automatically.
brick = Library.load(ontology_graph="brick/Brick.ttl", run_shacl_inference=False)

# 2. Create the MODEL shell with Model.create (gives it a namespace + ontology decl).
model = Model.create(BLDG, description="My building model")

# 3. Build the graph with TemplateBuilderContext, binding parameters to REAL identifiers.
context = TemplateBuilderContext(BLDG)
context.add_templates_from_library(brick)
ahu = context[BRICK.AHU]
ahu["name"] = BLDG["AHU1"]

# 4. Compile the context into a graph, add it to the model, and validate.
model.add_graph(context.compile())
ctx = model.validate([brick.get_shape_collection()])
print(ctx.valid)
```

Each piece below.

## 1. The template library (reusable, written once)

A `Library` holds templates (YAML `.yml`) and shapes (Turtle `.ttl`); load it from a
directory, an ontology graph, or build it inline. **Load it once; reuse it across models.**
Brick's class templates are the universal base — `Library.load(ontology_graph="brick/Brick.ttl")`
gives you a template for every Brick class (`brick:AHU`, `brick:VAV`, `brick:Supply_Fan`, …),
decompiled from the ontology. Application libraries (guideline36, 223p templates) build on
top of those.

If the building needs structure the stock libraries don't have, **write your own template
library** (`writing_templates.md`) rather than hand-adding triples — the template is the
reusable unit. Small, focused templates compose better than one giant template.

Load order still matters: load Brick before any library that depends on Brick class
templates, or `inline_dependencies()` raises `TemplateNotFound` naming a Brick class
(`templates.md`).

## 2. `Model.create` — the model shell

```python
model = Model.create(BLDG, description="Small office building")
```

`Model.create(name, description="")` takes a namespace (a `rdflib.Namespace` or URI string)
and creates a model with an `a owl:Ontology` declaration at that URI — that declaration is
required (it's how BuildingMOTIF keys the model and how OntoEnv resolves its imports). The
model's graph starts essentially empty; you fill it by adding evaluated templates.

Don't `Model.create` from raw triples you already have — use `Model.from_file(path)` or
`Model.from_graph(g)` for an existing graph (the graph must contain an `owl:Ontology`
declaration; `from_graph` reads the name from it). `create` is for *starting* a model you'll
build up with templates.

## 3. `TemplateBuilderContext` — wire templates and bind parameters

`TemplateBuilderContext` (`buildingmotif.model_builder`) is the fluent builder for
multi-template models. It holds a set of templates (inlined so their dependencies are
visible), lets you instantiate one by name, bind its parameters, and — the key feature —
**shares parameters across templates** by referring to a wrapper's bound slot, so two
templates that should reference the same equipment actually do. From the `Model-Builder`
notebook:

```python
context = TemplateBuilderContext(BLDG)
context.add_templates_from_library(nrel_lib)   # or .add_template(t) one at a time

# instantiate a template by indexing into the context
mau = context["makeup-air-unit"]
mau["name"] = BLDG["MAU"]
mau["air-supply"] = BLDG["MAU_AIR_SUPPLY"]

junction = context["junction"](name="MAU_SUPPLY_JUNCTION")

# a duct connecting the MAU's air-supply to the junction's in1 — note how mau["air-supply"]
# and junction["in1"] hand the *same* node to both ends of the duct
duct = context["duct"](name="mau_air_supply_duct", a=mau["air-supply"], b=junction["in1"])
```

Two things make this the workhorse:

- **`context[name]` returns a `TemplateWrapper`** — a fresh copy of the (inlined) template
  you bind parameters on by `wrapper["param"] = value` or `wrapper(name=..., param=...)`.
  Reading an unbound parameter (`wrapper["param"]`) **invents a name** in the namespace and
  returns it — which is how `mau["air-supply"]` can be passed to the duct before you've
  explicitly named it. Use this to connect components: read the slot on one wrapper, pass
  the resulting node as the binding on another.
- **`add_templates_from_library(lib)`** pulls in every template in a library at once. Use
  `add_template(t)` to add just one (it inlines dependencies).

### Binding to real identifiers (the evidence step)

`wrapper["name"] = BLDG["VAV1_ZN_T"]` binds a parameter to a real building identifier.
**This is where evidence enters** (`evidence.md`): the parameter names are the slots, and
the values are the real point/equipment names from the user's point list, BACnet dump, or
submittal. The `model_creation` tutorial is explicit that you "would likely pull the
equipment or point names from an external source" — do that, via `evidence.md`, rather than
inventing names.

`t.fill(BLDG)` (autogenerate bindings) exists for smoke tests and demos — **never use it to
build a real model**, it names real equipment with random hex. `TemplateBuilderContext`
uses `fill` internally only for the *remaining unbound required* parameters at compile time
(below); your job is to bind the meaningful ones to evidence first.

## 4. Compile, add to the model, validate

```python
model.add_graph(context.compile())
ctx = model.validate([brick.get_shape_collection()], error_on_missing_imports=False)
```

`context.compile()` evaluates every wrapper, **drops optional parameters** that weren't
bound, and **invents names** (in the context's namespace) for any *required* parameters
you didn't bind — then concatenates everything into one `Graph`, adding an `rdfs:label` to
each typed instance if it lacks one. Add that graph to the model with `model.add_graph(...)`.

**Then validate immediately** (`validation.md`). Building from templates gets you close to
conforming, but "close" is not "valid" — a missed connection or a missing point still fails,
and the iterative validate→fix→re-validate loop (`SKILL.md`) is how you close the rest. The
advantage of having built from templates is that the *fix* is often "bind one more
parameter on a template wrapper and re-compile," not "hand-write a triple and hope."

If you persist to a file/database, `bm.session.commit()` after `add_graph` for a
disk-backed instance; serialize with `model.graph.serialize(destination="model.ttl")`.

## Connecting components the model_builder can't express

`TemplateBuilderContext` wires templates by shared parameters. Some connections are just
edges between already-instantiated nodes — `ahu brick:hasPart fan` — and are clearer as a
direct triple than as another template. For those, add to the model's graph directly:

```python
model.graph.add((BLDG["AHU1"], BRICK.hasPart, BLDG["AHU1-Fan"]))
```

This is the legitimate use of `model.graph.add` — a handful of *connections* between things
you already built with templates. Don't use it to *define* equipment (that's what templates
are for); use it to link them.

## Bulk point-list builds

Point-list models are a special but common build case. A row may only tell you:

- the real point identifier/label;
- the owning equipment identifier;
- a suffix or description that maps to a Brick point class;
- optional units, I/O type, or BACnet reference.

For those rows, direct triples for **point leaves** are the scalable representation:
`point a verified Brick class`, `point rdfs:label "real label"`, and
`equipment brick:hasPoint point`. Use templates for repeated equipment/part structures
when you actually have enough evidence to bind their parameters. Do not create a custom
template just to add hundreds of typed leaves from a CSV.

The hybrid pattern is:

1. Use `brick_vocabulary.md` to verify every point/equipment class in the mapping table.
2. Use `point_labels.md` to parse labels or structured rows into equipment IDs and point
   classes.
3. Instantiate equipment templates when the source identifies a real equipment class.
4. Add point leaves directly with `model.graph.add(...)` or a small `add_point` helper.
5. Validate and refine the mapping from the failures.

## Building incrementally and validating as you go

A real model isn't built in one shot. The iterative workflow applies to *building* too, not
just repair: add a few templates, compile, validate, read what's missing, add the next
piece, re-validate. Early validation catches a missing point when it's one template away
from the fix, rather than after you've built the whole model on top of a gap.

```python
# build a little, then check
model.add_graph(context.compile())
ctx = model.validate([brick.get_shape_collection()], error_on_missing_imports=False)
for focus, failures in ctx.diffset.items():
    for f in failures:
        print(focus, f.reason())
# ...bind the missing parameters / add the missing templates, re-compile, re-validate
```

Each `context.compile()` produces a fresh graph — re-compiling after adding more wrappers is
fine, and `model.add_graph` merges (idempotently for duplicate triples). To *replace* a
model's contents wholesale, use `model.graph` carefully (the graph is the model; there's no
"clear and rebuild" shortcut through the context — re-run your build script from
`Model.create` for a clean rebuild).

## When to use what

| You have... | Use |
|---|---|
| A template library (yours or Brick's) + real identifiers from evidence | `TemplateBuilderContext` + `Model.create` (this file) |
| A point list / BMS labels / BACnet object names | `point_labels.md` + verified class mapping + hybrid templates/direct point triples |
| An existing Turtle file to validate | `Model.from_file` (`validation.md`) |
| An in-memory `rdflib.Graph` (e.g. from an ingress) | `Model.from_graph` (`validation.md`) |
| A shape requirement and want the builder for it | Write the shape (`writing_shapes.md`) → it decompiles to a template (`writing_templates.md`) → build with it |
| One-off connections between already-built nodes | `model.graph.add(...)` (sparingly) |

## Checklist

- [ ] Model created with `Model.create(BLDG, description=...)` (has the `owl:Ontology`
      declaration BuildingMOTIF requires).
- [ ] Template library loaded (Brick first, then dependents); reused, not reinvented.
- [ ] Parameters bound to **real identifiers** from evidence, not `fill`/random hex.
- [ ] Components connected via shared parameters (`wrapper["slot"]`) or, for simple edges,
      `model.graph.add`.
- [ ] `context.compile()` → `model.add_graph(...)` → `model.validate(...)` — validate early
      and iterate (`SKILL.md`).
- [ ] Serialized (`model.graph.serialize(destination=...)`) or committed
      (`bm.session.commit()`) when done.
