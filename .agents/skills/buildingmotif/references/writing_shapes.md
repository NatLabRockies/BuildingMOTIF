# Writing shapes

A **Shape** (SHACL) states what an application needs: the conditions and constraints an
RDF graph must satisfy. Writing a good shape *is* the act of making "will this app work
here?" answerable — most of the value in BuildingMOTIF comes from getting shapes right,
because a wrong shape produces confident, sound, wrong repairs (`repair.md`).

This file is the **authoring** guide: how to write shapes for pointlists, application
requirements, and manifests; the SHACL subset BuildingMOTIF understands; the `bmotif:`
vocabulary libraries use to organize shapes; and the bugs that produce shapes which pass
vacuously or demand nonsense. Folded in from `docs/tutorials/model_validation.md`,
`docs/explanations/shapes-and-templates.md`, and `docs/explanations/templates.md`
(readthedocs), and the real shapes in the repo's `libraries/ashrae/guideline36/*.ttl`.
Assumes BuildingMOTIF is an **installed package**.

Source of truth for what's recognized: `buildingmotif.utils.get_template_parts_from_shape`
(decompilation) and `buildingmotif/dataclasses/validation.py` (legacy report parsing); the
`pyshifty` engine evaluates the full SHACL spec it implements.

## Three kinds of shape you'll write

BuildingMOTIF validates against three things (`docs/tutorials/model_validation.md` names
these), and the shape you write depends on which:

1. **Ontology shapes** — come from the ontology itself (Brick's shape collection). You
   don't write these; you load them and validate against them to check the model *uses*
   the ontology correctly. `model.validate([brick.get_shape_collection()])`.
2. **Manifest shapes** — your model's *standing* requirements: "this site has exactly 1
   AHU, 1 supply fan, …". A manifest is a shape collection you associate with the model
   via `model.add_to_manifest(...)`. Written with the `constraint:` vocabulary (below).
3. **Application / use-case shapes** — "to run G36 §4.8, an AHU must have these points."
   These are the pointlist/equipment shapes that answer "is my model sufficient for X?"
   and are what most of this file is about. Libraries tag them as
   `bmotif:System_Specification` (below).

All three are just SHACL `sh:NodeShape`s; the distinction is *what they express* and how
you point validation at them.

## The pointlist idiom (the shape you'll write most)

A "pointlist shape" says: *this equipment must have these points.* The canonical form uses
a qualified value shape per required point. This is the pattern to copy:

```turtle
@prefix sh:    <http://www.w3.org/ns/shacl#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix bmotif: <https://nrel.gov/BuildingMOTIF#> .
@prefix : <urn:my-app/> .

: a owl:Ontology .

:vav-with-reheat a sh:NodeShape, owl:Class, bmotif:System_Specification ;
    sh:class brick:RVAV ;
    rdfs:subClassOf <urn:ashrae/g36/4.1/vav-cooling-only/vav-cooling-only> ;  # shapes compose
    bmotif:domain bmotif:HVAC ;
    sh:or ( :heating-signal1 :heating-signal2 ) .  # alternative valid designs

:heating-signal1 a sh:NodeShape ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Heating_Command ] ;
        sh:qualifiedMinCount 1 ;
    ] .
```

Five things in this example, each a deliberate choice:

### 1. `sh:NodeShape, owl:Class` — make it instantiable

Type your application shapes as **both** `sh:NodeShape` **and** `owl:Class`. Only the pair
gets decompiled into a template (`writing_templates.md`) — so you get the builder for the
equipment for free. A `sh:NodeShape` that is not also an `owl:Class` validates fine but
generates no template. Library system-specification shapes (`vav-cooling-only`, `sz-vav-ahu`,
…) all use both.

### 2. `sh:qualifiedValueShape` + `sh:qualifiedMinCount`, not `sh:minCount` + `sh:class`

This is **the most common shape bug.** Plain `sh:minCount 1` + `sh:class X` on one
property shape means "≥1 `hasPoint`, and **all** of them are X" — which fails the moment
the VAV has a second, different point. The qualified form means "≥1 of the `hasPoint`s is
an X", which is what a pointlist actually requires:

```turtle
# WRONG — fails when the equipment has any other point too
sh:property [
    sh:path brick:hasPoint ;
    sh:class brick:Temperature_Sensor ;
    sh:minCount 1 ;
] .

# RIGHT — "at least one hasPoint is a Temperature_Sensor"
sh:property [
    sh:path brick:hasPoint ;
    sh:qualifiedValueShape [ sh:class brick:Temperature_Sensor ] ;
    sh:qualifiedMinCount 1 ;
] .
```

### 3. `sh:or` for alternative designs

When the application accepts several valid designs (a heating command *or* a heating coil
with a position command), use `sh:or` rather than forcing one. The guideline36 shapes lean
on this heavily — `box-damper-position` is `sh:or` of "the VAV has the point directly" and
"the VAV has a part that has the point":

```turtle
:box-damper-position a sh:NodeShape, owl:Class ;
    sh:or ( :box-damper-position1 :box-damper-position2 ) .

:box-damper-position1 a sh:NodeShape ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Damper_Position_Command ] ;
        sh:qualifiedMinCount 1 ;
    ] .

:box-damper-position2 a sh:NodeShape ;
    sh:property [
        sh:path brick:hasPart ;
        sh:qualifiedValueShape [ sh:node :damper-with-position ] ;
        sh:qualifiedMinCount 1 ;
    ] .
```

### 4. `sh:class` vs `sh:targetClass` — does it actively select?

- **`sh:targetClass`** *actively* selects every instance of the class for validation.
  An app shape usually wants this (or a manifest that targets it) so it runs at all.
- **`sh:class`** constrains a node reached in a path; it doesn't select anything by
  itself.

A shape that never fires validates everything vacuously — see the debugging table below.
Note the guideline36 idiom uses **`sh:class`** at the top of a system-spec shape
(`:vav-cooling-only sh:class brick:VAV`) to mean "the focus node must be a VAV"; the
*selection* of which nodes to validate comes from a manifest targeting the shape
(`sh:node :vav-cooling-only`) or from the shape being used as a `sh:node` of another
shape. If you want a shape to run on every VAV unprompted, use `sh:targetClass brick:VAV`.

Class matching respects the **class hierarchy**: a shape requiring
`brick:Temperature_Sensor` is satisfied by `brick:Zone_Air_Temperature_Sensor`. Require
the most general class the app truly needs, and let subclasses satisfy it.

### 5. `sh:name` on a property shape — name the generated parameter

If the shape will be decompiled to a template, **`sh:name`** on a property shape seeds the
generated parameter name (`sh:name "sat"` → param `sat`) instead of an invented `p1`.
Worth setting even on hand-written shapes — the builder you get for free is much more
usable, and it documents the slot. Only property shapes with a `minCount`/`qualifiedMinCount`
> 0 generate a parameter (`writing_templates.md`).

```turtle
sh:property [
    sh:path brick:hasPoint ;
    sh:name "sat" ;                                   # -> parameter 'sat'
    sh:qualifiedValueShape [ sh:class brick:Supply_Air_Temperature_Sensor ] ;
    sh:qualifiedMinCount 1 ;
] .
```

## The `bmotif:` vocabulary

Libraries tag shapes with `bmotif:` definition types and domains so they're discoverable
by `get_shapes_of_definition_type` / `get_shapes_of_domain` (`validation.md`):

```turtle
@prefix bmotif: <https://nrel.gov/BuildingMOTIF#> .

:vav-cooling-only a sh:NodeShape, owl:Class, bmotif:System_Specification ;
    bmotif:domain bmotif:HVAC .
```

- **`bmotif:System_Specification`** — the definition type for "all metadata required for
  an entity to run a control sequence / application." Guideline 36's system specs
  (`sz-vav-ahu`, `vav-cooling-only`, …) are all tagged this way; find them with
  `sc.get_shapes_of_definition_type(BMOTIF["System_Specification"])`.
- **`bmotif:domain`** — the equipment domain (`bmotif:HVAC`, …); find with
  `sc.get_shapes_of_domain(BMOTIF["HVAC"])`.

`get_shapes_of_definition_type` includes subclasses of the given type, so a more specific
definition type you define (as `rdfs:subClassOf bmotif:System_Specification`) is found by
a query for `System_Specification`. You don't have to use these tags for a shape to work —
they're for *organizing and discovering* shapes in a library. A one-off app shape you
validate against directly doesn't need them.

## Manifests and the `constraint:` vocabulary

A **manifest** is a shape collection holding the model's standing requirements
(`docs/tutorials/model_validation.md`). The common manifest pattern counts instances —
"the model contains exactly 1 AHU" — using BuildingMOTIF's custom `constraint:` shapes,
which ship in the builtin `constraints/constraints.ttl` library:

```turtle
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix owl:   <http://www.w3.org/2002/07/owl#> .
@prefix sh:    <http://www.w3.org/ns/shacl#> .
@prefix constraint: <https://nrel.gov/BuildingMOTIF/constraints#> .
@prefix : <urn:my_site_constraints/> .

: a owl:Ontology ;
    owl:imports <https://brickschema.org/schema/1.4/Brick> .

:ahu-count a sh:NodeShape ;
    sh:message "need 1 AHU" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:AHU .
```

`constraint:exactCount N` + `constraint:class <Class>` on a `sh:targetNode :` shape
asserts "the model contains exactly N instances of Class." Load the constraints library
(`Library.from_ontology("constraints/constraints.ttl")`) and the manifest, then
associate it:

```python
manifest = Library.from_ontology("my_manifest.ttl")
model.add_to_manifest(manifest.get_shape_collection())
ctx = model.validate()   # validates against the manifest by default
```

`add_to_manifest` **merges** into whatever the model already has — call it twice and you get
the union, so a manifest can grow but never shrink. To swap the requirements out wholesale,
use `model.replace_manifest(sc)`, which discards the previous contents. Reach for `replace_`
when re-running a script that would otherwise accumulate stale requirements across runs.

(`update_manifest` is the old name for `add_to_manifest`. It still works and warns; the name
was misleading, since it never replaced anything.)

### ⚠ `constraint:` components validate but block repair

`constraint:exactCount`/`constraint:class` compile to SPARQL-based SHACL, which the
`pyshifty` engine *does* evaluate correctly (a model with no AHU fails; adding one makes
it pass). But that failure comes back as a **blocked witness** (`w.is_blocked` True, no
proposals) — an opaque SPARQL/`Not` constraint the repair calculus can't abduce over
(`repair.md`). So you get the pass/fail, but **zero repair proposals**.

If you want a requirement that pyshifty can both validate *and* repair, express it as
plain SHACL — a `sh:property` with `sh:minCount` (or `sh:qualifiedValueShape` +
`sh:qualifiedMinCount`) targeting the owning class:

```turtle
# Repairable: "every AHU must have at least one supply-air-temp sensor"
:ahu-sat a sh:NodeShape ;
    sh:targetClass brick:AHU ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Supply_Air_Temperature_Sensor ] ;
        sh:qualifiedMinCount 1 ;
    ] .
```

The pyshifty validation notebook does exactly this rewrite for its AHU-setpoint
requirement. Use `constraint:` for *counting* requirements (where "repair" would mean
"mint an equipment," which needs evidence anyway); use plain SHACL for *property*
requirements you want the engine to propose fixes for.

## The manifest header and `owl:imports`

A manifest (and any shape graph that references other ontologies' classes) should declare
itself an ontology and import what it needs:

```turtle
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix : <urn:my_site_constraints/> .

: a owl:Ontology ;
    owl:imports <https://brickschema.org/schema/1.4/Brick>,
                <https://nrel.gov/BuildingMOTIF/constraints>,
                <urn:ashrae/g36> .
```

**`owl:imports` is resolved by OntoEnv** — by default (`ontology_fetch_imports=True`)
those imports are fetched/resolved automatically (`ontology_imports.md`). Give the graph
an `: a owl:Ontology .` declaration: without it, loading and import resolution misbehave in
ways that surface as an empty or silently-passing report.

## Building shapes in Python

`buildingmotif.shape_builder.shape` offers a fluent builder — good for generating shapes
programmatically (e.g. one per equipment from a pointlist spreadsheet):

```python
from buildingmotif.shape_builder.shape import NodeShape, PropertyShape, OR, AND, NOT, XONE
from buildingmotif.namespaces import BRICK, SHAPES

shape = (NodeShape(SHAPES["zone-with-room"])
    .of_class(BRICK["HVAC_Zone"])                 # of_class(..., active=True) -> sh:targetClass
    .has_property(PropertyShape()
        .has_path(BRICK["hasPart"])
        .matches_shape(NodeShape().of_class(BRICK["Room"]), min=1)))
shapes_graph += shape
```

`Shape` subclasses `rdflib.Graph`, so `+=` merges and `.serialize()` prints. Also:
`matches_class`, `has_path(..., one_or_more=True)` for path operators, `always_run()`
for a blank-node target, and the `OR`/`AND`/`NOT`/`XONE` combinators. For hand-written
shapes, Turtle is usually clearer — use the builder when shapes are *generated*.

## Finding application shapes already in a library

Libraries tag their shapes with `bmotif:` definition types. Guideline 36's system
specifications (the metadata an entity needs to run a G36 control sequence) are found
with:

```python
from buildingmotif.namespaces import BMOTIF
sc = g36.get_shape_collection()
for shape in sc.get_shapes_of_definition_type(BMOTIF["System_Specification"]):
    print(shape)
# urn:ashrae/g36/4.1/vav-cooling-only/vav-cooling-only
# urn:ashrae/g36/4.2/vav-with-reheat/vav-with-reheat
# ... (15 system specs)
```

Then target one from a manifest (`sh:node <urn:ashrae/g36/4.8/sz-vav-ahu/sz-vav-ahu>`)
or validate against the library's shape collection directly. A manifest tying an AHU to a
G36 spec:

```turtle
:sz-vav-ahu-control-sequences a sh:NodeShape ;
    sh:message "AHUs must match the single-zone VAV AHU shape" ;
    sh:targetClass brick:AHU ;
    sh:node <urn:ashrae/g36/4.8/sz-vav-ahu/sz-vav-ahu> .
```

## The SHACL subset BuildingMOTIF decompiles

If a shape will be turned into a template, `get_template_parts_from_shape` recognizes:

- `sh:property`, `sh:qualifiedValueShape`, `sh:node`, `sh:class`, `sh:targetClass`
- `sh:datatype`
- `sh:minCount` / `sh:qualifiedMinCount`, `sh:maxCount` / `sh:qualifiedMaxCount`

**Validation** (pyshifty) implements the full SHACL spec it supports — `sh:or`, property
paths, `sh:not`, `sh:closed`, etc. all validate. The *decompilation* (shape → template)
is the narrower subset above: a shape with constructs outside that list still validates
fine, but the generated template won't capture the parts decompilation doesn't understand.
For shapes you also want as builders, stay within the subset; for pure validation shapes,
use whatever SHACL you need.

## Debugging a shape

The failure mode to expect is not a crash — it's a shape that passes when it shouldn't,
or demands nonsense. Diagnose with the repair tree, which shows the shape's *actual*
demands rather than your intent (`validation.md`):

```python
for w in ctx.witnesses:
    print(w.reason())
    print(w.explain())     # the AND/OR/Repeat tree of typed holes
```

**Symptom → cause:**

| Symptom | Likely cause |
|---|---|
| `ctx.valid` is True on a model you know is broken | Shape never fires: no `sh:targetClass`/target, or not loaded. Break the model deliberately and confirm the shape *can* fail. |
| Violation on a VAV that *has* the point | Unqualified `sh:minCount` + `sh:class` — "all hasPoints must be X". Use `sh:qualifiedValueShape`. |
| Every instance fails identically | Requirement is too strict, or the class is wrong (`Temperature_Sensor` vs `Zone_Air_Temperature_Sensor` — check hierarchy direction). |
| `w.is_blocked` | Opaque SPARQL / identity / coinductive constraint (e.g. `constraint:exactCount`): not repairable by data. Rewrite the constraint. |
| Repairs propose absurd equipment | The shape says something you didn't mean. Read `w.explain()`; the tree is what you actually wrote. |

**Test a shape like code**: validate it against a model you know conforms *and* one you
know doesn't. A shape that never fails isn't a requirement.

## When the shape is wrong, fix the shape

If validation demands something the building doesn't have and shouldn't, the right repair
is to the *shape*, not the graph. Say this plainly to the user — "this shape requires a
CO2 sensor on every VAV; your VAVs don't have them, and G36 4.1 doesn't require them" —
rather than minting equipment to satisfy a mistaken requirement. Repairing a model to fit
a wrong shape produces a model that lies (`repair.md`).

## Authoring checklist

- [ ] Instantiable shapes are typed `sh:NodeShape, owl:Class` (both).
- [ ] Pointlists use `sh:qualifiedValueShape` + `sh:qualifiedMinCount`, not
      `sh:minCount` + `sh:class`.
- [ ] The shape *selects* what it targets (`sh:targetClass`, a manifest `sh:node`, or a
      `sh:class` reached from another shape) — or it'll pass vacuously.
- [ ] `sh:name` on property shapes you'll decompile (so parameters get real names).
- [ ] The graph declares `: a owl:Ontology .` and `owl:imports` what it needs.
- [ ] If you want it *repairable*, it's plain SHACL — not `constraint:` (which blocks).
- [ ] You've validated it against a conforming and a non-conforming model.
