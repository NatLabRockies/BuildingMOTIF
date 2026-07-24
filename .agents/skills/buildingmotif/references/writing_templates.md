# Writing templates

A **Template** is a function that generates an RDF graph. Its *parameters* are the
`urn:___param___#` (`PARAM`) nodes in its body; `name` is the distinguished root
parameter. You write templates to give a building its domain vocabulary — the reusable
fragments that get *filled* to build a model (`templates.md` for filling/matching) and that
the repair engine uses as a candidate generator (`repair.md`).

This file is the **authoring** guide: how to define a template, declare dependencies,
choose parameters, and avoid the mistakes that bite at fill/match time. Folded in from
`docs/explanations/templates.md` and `docs/explanations/shapes-and-templates.md`
(readthedocs), and the real libraries in the repo's `libraries/` directory. Assumes
BuildingMOTIF is an **installed package**.

## The two ways to define a template

You almost always write templates as **YAML**. The alternative — letting BuildingMOTIF
**decompile a SHACL shape** into a template — is for when you've already written the shape
and want the builder for free (covered at the end and in `writing_shapes.md`). Both produce the
same `Template` objects.

## YAML format

A YAML file holds several templates. Each template:

- **name** — the top-level key.
- **`body`** (required) — an RDF graph in Turtle. Parameters are the nodes in the
  `urn:___param___#` namespace (commonly bound to prefix `P` or `p`). The parameters of
  the template are *exactly* those that appear in the body.
- **`optional`** — a list of parameter names that may be left unbound.
- **`dependencies`** — a list of dependency dicts (below).

Other keys (`optional`, `dependencies`) refer to a parameter by its *bare name* (without
the `urn:___param___#` prefix): in the body you write `P:sensor`, elsewhere `sensor`.

A complete example, copied from `docs/explanations/templates.md` — note the `@prefix`
declaration in each body (the body is parsed as Turtle, so it needs its own prefixes):

```yaml
vav-cooling-only:
  body: >
    @prefix p: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    p:name a brick:VAV ;
        brick:hasPoint p:ztemp, p:occ, p:co2, p:dat ;
        brick:hasPart p:dmp ;
        brick:feeds p:zone .
  optional: ['occ', 'co2']
  dependencies:
    - template: damper
      args: {"name": "dmp"}
    - template: https://brickschema.org/schema/Brick#HVAC_Zone
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "zone"}
    - template: https://brickschema.org/schema/Brick#Zone_Air_Temperature_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "ztemp"}
    - template: https://brickschema.org/schema/Brick#Occupancy_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "occ"}
    - template: https://brickschema.org/schema/Brick#CO2_Level_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "co2"}
    - template: https://brickschema.org/schema/Brick#Discharge_Air_Temperature_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "dat"}

damper:
    body: >
      @prefix P: <urn:___param___#> .
      @prefix brick: <https://brickschema.org/schema/Brick#> .
      P:name a brick:Damper .
```

A real, minimal one from the repo's `libraries/ashrae/guideline36/4.9-exhaust-fan.yml` —
one equipment, three points, one of them optional, all dependencies on Brick class
templates:

```yaml
constant-speed-exhaust-fan:
  body: >
    @prefix p: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    p:name a brick:Exhaust_Fan ;
      brick:hasPoint p:start_stop, p:status, p:zat .
  optional: ["zat"]
  dependencies:
    - template: https://brickschema.org/schema/Brick#Start_Stop_Command
      library: https://brickschema.org/schema/1.4/Brick
      args: {"name": "start_stop"}
    - template: https://brickschema.org/schema/Brick#Fan_Status
      library: https://brickschema.org/schema/1.4/Brick
      args: {"name": "status"}
    - template: https://brickschema.org/schema/Brick#Zone_Air_Temperature_Sensor
      library: https://brickschema.org/schema/1.4/Brick
      args: {"name": "zat"}
```

### The body is Turtle — declare your prefixes

The `body:` value is parsed as Turtle, so **every body needs its own `@prefix` lines**.
This is the most common authoring slip: a body that uses `brick:` without declaring it
fails to parse, and the error points at the prefix, not at your intent. Always start the
body with at least:

```
@prefix p: <urn:___param___#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
```

Use `>` (folded scalar) so newlines are preserved as Turtle needs. The parameter prefix
can be `p:`, `P:`, or any prefix bound to `urn:___param___#` — they're equivalent, just be
consistent within a body.

## Parameters

A parameter is any node in the `urn:___param___#` namespace that appears in the body. The
**`name` parameter is mandatory** and is the template's root — the entity the template
builds (the VAV, the fan, the coil). Other parameters are the things the template
connects to `name`: points, parts, fed zones.

**Name parameters well** — they're the API of the template, and they're what a filler
reads to know what to bind. `ztemp`, `dat`, `dmp` are clear; `p1`, `p2` are not. (When a
template is *decompiled* from a shape, `sh:name` on the property shape seeds the parameter
name — `writing_shapes.md`; for hand-written YAML you control the name directly, so make it
descriptive.)

### `optional` vs required

A parameter is **required** unless listed in `optional`. `substitute()` always returns a
`Template`; its `is_complete` is True once every required parameter is bound, and
`to_graph()` then produces the graph (`templates.md`). Unbound optional parameters do not
block `to_graph()` — the triples mentioning them are dropped, unless you pass
`require_optional_args=True`.

Mark a parameter optional when the template *can* include it but the building often
won't have it — `zat` (zone air temp) on an exhaust fan that may or may not report it. A
shape requiring that point would use `sh:minCount 0` or an `sh:or` alternative; the
template's `optional` mirrors that the fill is optional, not that the requirement is.

## Dependencies

Dependencies let one template pull in another's body, so you compose equipment from parts
without restating the parts' triples. A dependency dict has:

- **`template`** (required) — the dependency's name. For a Brick class, this is the full
  IRI (`https://brickschema.org/schema/Brick#HVAC_Zone`) of the class template Brick
  auto-generates.
- **`library`** (optional) — the library to load it from. Omit for a same-library
  dependency; set to the ontology IRI (e.g. `https://brickschema.org/schema/1.4/Brick`)
  for a cross-library one. **Must match the version actually loaded** — `1.3` vs `1.4`
  mismatches cause `TemplateNotFound`.
- **`args`** (required) — a dict mapping the *dependency's* parameter names to *this*
  template's parameter names. The dependency's parameter is bound to the value this
  template's parameter gets at fill time. You need not bind all of the dependency's
  parameters; unbound ones stay open and affect inlining.

In `vav-cooling-only` above, the `damper` dependency binds the damper template's `name`
to this template's `dmp` parameter — so whoever fills `dmp` is naming the damper. The
`HVAC_Zone` dependency binds the zone template's `name` to `zone`.

### Load order

**Load libraries containing dependencies before the dependents.** Load Brick before any
library that depends on Brick class templates. If you don't, `inline_dependencies()`
raises `TemplateNotFound` naming a Brick class — that error means "load Brick first", not
"the template is broken" (`templates.md`).

## Templates from SHACL shapes (decompilation)

When a Library is loaded from an RDF graph, BuildingMOTIF creates a template for each
node that is **both** `sh:NodeShape` **and** `owl:Class` — the pair that makes a shape
*instantiable*. A `sh:NodeShape` that is not also an `owl:Class` is **not** decompiled.

Decompilation (`get_template_parts_from_shape`) recognizes this subset of SHACL:

- `sh:property`, `sh:qualifiedValueShape`, `sh:node`, `sh:class`, `sh:targetClass`
- `sh:datatype`
- `sh:minCount` / `sh:qualifiedMinCount`, `sh:maxCount` / `sh:qualifiedMaxCount`

A `name` parameter is created automatically for the focus node. A parameter is created
for each property shape that carries one of `sh:class`, `sh:node`, or `sh:datatype`
(use of `sh:qualifiedValueShape` is allowed). **Only property shapes with a `minCount` or
`qualifiedMinCount` > 0 are included** — a `maxCount`-only property shape generates no
parameter. If the property shape has a **`sh:name`**, that string seeds the generated
parameter name (e.g. `sh:name "ztemp"` → param `ztemp` — a recognizable name, instead of
the invented `p1`, `p2`, …). The template's name is the IRI of the node shape.

### `sh:or` becomes alternative templates

A template generates a *fragment*; it cannot itself be disjunctive. So a node shape carrying
`sh:or` decompiles into **several** templates -- one per way of satisfying it -- rather than
one template that somehow means both:

| template | body |
|---|---|
| `<shape>` | the shape's non-disjunctive requirements only |
| `<shape>-alt1` | those requirements **+ the first `sh:or` branch** |
| `<shape>-alt2` | those requirements **+ the second branch** |

Fill **one** alternative, not all of them. Each already includes the common part, so any
single one satisfies the shape; filling two would assert both branches, which is exactly the
false-metadata trap `sh:or` exists to avoid.

**Order is meaningful.** `sh:or` takes an `rdf:List`, which is ordered, and that authoring
order is the only ranking the shape carries -- authors conventionally put the common or
preferred case first. `-alt1` is the first branch written. Present alternatives in that order
rather than inventing a ranking.

`sh:or` nested inside a *property* shape (constraining one value's type, rather than the
whole entity) is still not decompiled.

Disable with `infer_templates=False` on the loader. You can also decompile an
existing `ShapeCollection` on demand:

```python
from buildingmotif.dataclasses import ShapeCollection, Library
sc = ShapeCollection.create()
sc.graph.parse(data=my_shapes_turtle, format="turtle")
lib = Library.create("my-library")
sc.infer_templates(lib)          # templates appear in lib
```

### Implicit dependencies

BuildingMOTIF adds dependencies to a shape-derived template when a property shape reaches
another node shape via `sh:class`, `sh:node`, or when the node shape uses `sh:node`. It
follows `owl:imports` to find node shapes not defined in the current graph — so a shape
that `sh:class brick:Air_Temperature_Sensor` adds a dependency on Brick's class template,
found by walking the manifest's `owl:imports` of Brick. This is why a shape you write for
an application (`writing_shapes.md`) also gives you the template to *build* what it requires — and
why `sh:name` on a property shape is worth setting even when you write the shape by hand.

## Which form should I write?

| You want to... | Write |
|---|---|
| Build a specific equipment from parts, with custom structure a shape doesn't capture | **YAML** — full control over the body and parameters |
| Reuse an application requirement shape as a builder | **Shape + decompilation** — write the shape (`writing_shapes.md`), get the template free |
| Provide repair candidates | **YAML** — small, focused templates (a few triples) that the repair engine matches (`repair.md`, `templates.md`) |

The repo's `libraries/` use **both** side by side: `.yml` files for equipment templates
(exhaust fan, VAV) and `.ttl` files for the SHACL shapes (system specifications). A
library directory can hold both; `Library.from_directory(...)` loads all `.yml` as
templates and all `.ttl` as shapes (decompiling the instantiable ones).

## Authoring checklist

Before considering a template done:

- [ ] Every `body:` declares its `@prefix` lines (including `urn:___param___#`).
- [ ] `name` parameter exists and is the root entity (the thing being built).
- [ ] Parameter names are descriptive (`ztemp`, not `p1`).
- [ ] `optional` lists only parameters the building may legitimately lack.
- [ ] Dependencies' `library:` matches the loaded ontology version; deps load before
  dependents.
- [ ] You've **evaluated** it once with real bindings and added the result to a model
  (`templates.md`) — a template that parses but produces the wrong graph is the failure
  mode you'll only catch by filling it.
- [ ] If it'll be matched by `TemplateMatcher` or used in repair, the body is **small**
  (a few triples) — matching is exponential in template size (`templates.md`).

## Test a template like code

A template is code; validate it against a known fill. Bind it to real identifiers,
evaluate, add to a scratch model, and confirm the triples you expect appear (and no
others):

```python
from rdflib import Namespace
from buildingmotif.dataclasses import Library
BLDG = Namespace("urn:bldg/")
lib = Library.from_directory("my_library")
t = lib.get_template_by_name("vav-cooling-only")
g = t.substitute({"name": BLDG["vav1"], "ztemp": BLDG["vav1_ZN_T"], "dmp": BLDG["vav1_dmp"],
                "zone": BLDG["zone1"], "dat": BLDG["vav1_DAT"], "occ": BLDG["vav1_occ"],
                "co2": BLDG["vav1_CO2"]}).to_graph()   # raises if anything is unbound
# spot-check the triples you care about
assert (BLDG["vav1"], None, BLDG["vav1_ZN_T"]) in g
```

A template that returns a `Template` instead of a `Graph` has an unbound required
parameter — check `t.parameters` against your bindings.
