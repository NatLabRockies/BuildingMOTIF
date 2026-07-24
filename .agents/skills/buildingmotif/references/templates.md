# Finding, choosing, and filling templates

A **Template** is a function that generates an RDF graph. Its parameters are the
`urn:___param___#` (`PARAM`) nodes in its body; `name` is the distinguished root
parameter. Templates are BuildingMOTIF's domain vocabulary: they're what you fill to
*build* a model, and what the repair engine uses as a candidate generator.

This file assumes BuildingMOTIF is an **installed package** (`pip install buildingmotif`
/ `uv add buildingmotif`); all imports come from `buildingmotif.*`. Folded in from
`docs/explanations/templates.md` and `docs/explanations/shapes-and-templates.md`
(readthedocs).

## How a template is defined

Two ways to define templates; both produce the same `Template` objects.

### YAML format (most common)

A YAML file holds several templates. Each template:
- **name** — the top-level key.
- **`body`** (required) — an RDF graph in Turtle. Parameters are the nodes in the
  `urn:___param___#` namespace (commonly bound to prefix `P` or `p`). The parameters of
  the template are *exactly* those that appear in the body.
- **`optional`** — a list of parameter names that may be left unbound.
- **`dependencies`** — a list of dicts (below).

Other keys refer to a parameter by its *bare name* (without the `urn:___param___#`
prefix): in the body you write `P:sensor`, elsewhere `sensor`.

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

damper:
  body: >
    @prefix P: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    P:name a brick:Damper .
```

A dependency dict has: `template` (required, the dependency's name), `library`
(optional, the library to load it from — defaults to the current library), and `args`
(required, mapping the *dependency's* parameter names to *this* template's parameter
names). You need not bind all parameters; unbound ones stay open and affect inlining.

### SHACL shapes (decompiled automatically)

When a Library is loaded from an RDF graph, BuildingMOTIF creates a template for each
node that is **both** `sh:NodeShape` **and** `owl:Class` — the pair that makes a shape
*instantiable*. A `sh:NodeShape` that is not also an `owl:Class` is **not** decompiled.

Decompilation (`buildingmotif.utils.get_template_parts_from_shape`) recognizes this
subset of SHACL:

- `sh:property`, `sh:qualifiedValueShape`, `sh:node`, `sh:class`, `sh:targetClass`
- `sh:datatype`
- `sh:minCount` / `sh:qualifiedMinCount`, `sh:maxCount` / `sh:qualifiedMaxCount`

A `name` parameter is created automatically for the focus node. A parameter is created
for each property shape that carries one of `sh:class`, `sh:node`, or `sh:datatype`
(use of `sh:qualifiedValueShape` is allowed). Only property shapes with a `minCount` or
`qualifiedMinCount` > 0 are included. If the property shape has a **`sh:name`**, that
string seeds the generated parameter name (e.g. `sh:name "ztemp"` → param `ztemp0` — a
recognizable name, instead of the invented `p1`, `p2`, …). The template's name is the
IRI of the node shape.

Disable with `Library.load(..., infer_templates=False)`. You can also decompile an
existing `ShapeCollection` on demand:

```python
from buildingmotif.dataclasses import ShapeCollection, Library
sc = ShapeCollection.create()
sc.graph.parse(data=my_shapes_turtle, format="turtle")
lib = Library.create("my-library")
sc.infer_templates(lib)          # templates appear in lib
```

Implicit dependencies are added when a property shape reaches another node shape via
`sh:class`, `sh:node`, or when the node shape uses `sh:node`. BuildingMOTIF follows
`owl:imports` to find node shapes not defined in the current graph.

This is why a shape you write for an application (`writing_shapes.md`) also gives you the
template to *build* what it requires — and why `sh:name` on a property shape is worth
setting: it names the generated parameter instead of inventing one.

## Loading libraries (order matters)

```python
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library

bm = BuildingMOTIF("sqlite://"); bm.setup_tables()

# 1. Brick FIRST — builtin resource, auto-resolved from the installed package.
#    run_shacl_inference=False is required: inference-on does NOT produce the class
#    templates other libraries depend on. By default (ontology_fetch_imports=True)
#    OntoEnv also resolves Brick's owl:imports (REC, QUDT pieces); pass
#    fetch_imports=False to load just Brick faster if you only need class templates.
brick = Library.load(ontology_graph="brick/Brick.ttl", run_shacl_inference=False)

# 2. then libraries that depend on it. guideline36 is repo-only (not packaged) —
#    load it from a clone, or git-load it (see "Getting repo-only libraries" below).
g36 = Library.load(directory="/path/to/clone/libraries/ashrae/guideline36")  # 115 templates
```

Deviating from this recipe is the top cause of
`TemplateNotFound: Name: https://brickschema.org/schema/Brick#Damper_Position_Command` —
a Brick *class* named as a missing template means Brick isn't loaded (or was loaded in a
way that didn't infer class templates). Fix the load order; don't edit the library.

### Getting repo-only libraries (guideline36, chiller-plant, pointlist-test, 223p, …)

Only `brick/`, `constraints/`, and `bacnet/` ship in the package. For everything else,
three options, all of which end in a directory or ontology graph that `Library.load`
accepts:

1. **Clone the repo** once and pass the directory path:
   `Library.load(directory="/abs/path/to/libraries/ashrae/guideline36")`.
   Templates in a directory library are the `.yml` files; shapes are the `.ttl` files.
2. **`libraries.yml` + git** — let BuildingMOTIF clone it at load time:
   ```yaml
   - git:
       repo: https://github.com/NREL/BuildingMOTIF
       branch: main
       path: libraries/ashrae/guideline36
   ```
   then `Library.load_from_libraries_yml("libraries.yml")`. The CLI equivalent is
   `buildingmotif load -l libraries.yml` (use `uvx buildingmotif` to run without a
   persistent install). `buildingmotif get_default_libraries_yml` writes a sample
   `libraries.default.yml` in the cwd showing all three keys (`directory`, `ontology`,
   `git`).
3. **Load a remote ontology URL** directly — e.g. the nightly Brick:
   `Library.load(ontology_graph="https://github.com/BrickSchema/Brick/releases/download/nightly/Brick.ttl")`.
   (The builtin `brick/Brick.ttl` already covers the Brick case without a download.)

`Library.load(ontology_graph=<str>)` treats the string as a **path** (builtin resource
lookup first, then the local filesystem) **or a URL**. To load **inline** Turtle from a
Python string, parse it into an `rdflib.Graph` first and pass the graph — passing the
raw string will be misread as a filename:

```python
import rdflib
g = rdflib.Graph(); g.parse(data=turtle_string, format="turtle")
lib = Library.load(ontology_graph=g)
```

Brick load takes **seconds**, not minutes. Persist it if you want: use a file URI
(`BuildingMOTIF("sqlite:///bm.db")`) once, then on later runs
`Library.load(name="Brick")` (loads the previously-stored DB record by name).

## Finding the right template

**By name**, when you know it: `lib.get_template_by_name("vav-cooling-only")`.

**By browsing**, to see what a library offers:

```python
for t in g36.get_templates():
    print(t.name, sorted(t.parameters))
# sz-vav-ahu ['clg_coil', 'co2', 'damper', 'filter_pd', 'htg_coil', 'ma_temp',
#             'name', 'oa_ra_damper', 'oa_temp', 'occ', 'ra_temp', 'sa_fan',
#             'sa_temp', 'ztemp']
```

Parameter names are the fastest way to judge fit: they tell you what the template
expects you to know. Skim names and parameters before matching — 115 templates is small
enough to read and matching is expensive.

**By matching against the model** — the real tool for "which template describes this
equipment?" `TemplateMatcher` computes VF2 subgraph monomorphisms of the template into
the building graph, using the ontology's class hierarchy for semantic feasibility:

```python
from buildingmotif.template_matcher import TemplateMatcher
from rdflib import Graph, RDF, RDFS, OWL

# Project the ontology to only the triples the matcher reads — much faster than
# passing all of Brick, and (unlike a subClassOf-only trim) semantics-preserving.
full = brick.get_shape_collection().graph
onto = Graph()
for pred in (RDFS.subClassOf, RDFS.subPropertyOf):
    for triple in full.triples((None, pred, None)):
        onto.add(triple)
for triple in full.triples((None, RDF.type, OWL.Class)):   # keep `a owl:Class`!
    onto.add(triple)

t = g36.get_template_by_name("vav-cooling-only")   # NOT inlined — see performance below

m = TemplateMatcher(model.graph, t, onto)
m.largest_mapping_size                         # PROPERTY, not a method — no parens
for mapping in m.mappings_iter(m.largest_mapping_size):
    mapping                                    # {building_node: template_node}
    m.building_subgraph_from_mapping(mapping)  # what matched, in the model
    rem = m.remaining_template(mapping)        # a Template of what's still MISSING
    print(sorted(rem.parameters) if rem else "complete match")
```

`mappings_iter(None)` yields all mappings, most complete first. `remaining_template`
returns `None` when the mapping already binds every parameter (a complete match), and
warns about unbound parameters — that warning is the expected result here, not a problem.

Verified output for a small hand-written VAV template (params `name`, `ztemp`, `damper`;
5 body triples) matched against a model containing only a zone temp sensor:

```
largest mapping size: 4
mapping: {'vav1': 'name', 'sat': 'ztemp', 'Brick#VAV': 'VAV',
          'Brick#Zone_Air_Temperature_Sensor': 'Temperature_Sensor'}
remaining params: ['damper']
```

Note `sat` matched the `ztemp` parameter through the **class hierarchy** —
`Zone_Air_Temperature_Sensor` satisfies a template asking for `Temperature_Sensor` —
and the gap report is exactly the one missing point. That is the whole tool in one
example.

Two things make this the workhorse:

- **`largest_mapping_size` ranks candidate templates.** Run several templates against
  the same equipment; the one with the largest mapping is the best description of it.
- **`remaining_template(mapping)` is a gap report.** It's the part of the template the
  model doesn't have yet — the to-do list for making this equipment conform, already
  shaped as a fillable template.

### TemplateMatcher performance: read this before you use it

`TemplateMatcher` is **exponential in template size and linear in ontology size**, and it
will appear to hang. `generate_all_subgraphs` enumerates every node-induced subgraph of
the template — `2^|nodes|` of them — and runs a VF2 match for each, where every semantic
feasibility check walks the ontology. Measured on `vav-cooling-only`:

| template | nodes | subsets | ontology | time |
|---|---|---|---|---|
| non-inlined | 8 | 256 | trimmed (~2,000 triples) | **0.85s** |
| non-inlined | 8 | 256 | full Brick (53,882 triples) | **22.4s** |
| **inlined** | **16** | **65,536** | full Brick | **did not finish in 7 min** |

(The trimmed timing was measured with a `subClassOf`-only graph; the correct projection
above — which also keeps `subPropertyOf` and `a owl:Class` — is the same order of size
and speed, and unlike the bare trim it doesn't corrupt the match. Use the projection.)

Two rules follow:

1. **Project the ontology.** It's read only for semantic feasibility, via exactly three
   triple patterns: `rdfs:subClassOf`, `rdfs:subPropertyOf`, and `(x a owl:Class)`.
   Restricting to those (as above) is far faster and gives identical matches. Do **not**
   keep only `subClassOf` — dropping the `a owl:Class` declarations makes the matcher's
   class check *permissive* (it silently matches unrelated classes), a correctness bug,
   not just a speedup. This is the same projection the repair engine applies internally
   (`_ontology_projection`).
2. **Inline only when you must, and only for small templates.** Each added node
   *doubles* the work. An un-inlined body holds only its own triples, so inlining is
   what exposes dependency structure to the match — but 8 nodes → 16 nodes took it from
   under a second to unfinishable. Match the un-inlined template first; inline only if
   you specifically need to match the dependencies' interior.

If a match is taking more than a few seconds, stop and shrink one of the two inputs.
Don't wait it out, and don't blame the library load — full Brick loads in ~6s.

## Filling a template

```python
t.parameters                       # required params
t.optional_args                    # optional
t.all_parameters                   # including dependencies' (property, no parens)
t.parameter_counts                 # how often each is used (property, no parens)

# bind real identifiers -> Graph if fully bound, else a partially-bound Template
g = t.evaluate({"name": BLDG["VAV-1"], "ztemp": BLDG["VAV1_ZN_T"]})
if isinstance(g, Graph):
    model.add_graph(g)
```

`evaluate()` returns a **`Template` when parameters remain unbound** and a `Graph` only
when it's complete — always check, or bind incrementally and evaluate again. Unbound
optional args are dropped from the body unless `require_optional_args=True`.

`t.fill(BLDG)` autogenerates bindings (`name_a1b2c3`). It's for smoke tests and demos.
**Never use it to build a real model**: it names real equipment with random hex. Bind to
identifiers from the user's documents (`evidence.md`).

For fluent multi-template model building, `TemplateBuilderContext`
(`buildingmotif.model_builder`) wires templates together by shared parameter names,
compiles them into one graph, and is the right tool for constructing a whole model. See
`building_models.md` (and the `Model-Builder.ipynb` notebook on GitHub) for the full
build-a-model workflow — `Model.create`, binding parameters to evidence, compiling, and
validating as you go.

## Templates in repair

Templates passed as `repair_libraries=[...]` become candidate sources:

- **reuse** — existing model nodes monomorphic to a template (`reused_nodes` non-empty:
  low truth risk, connects facts already asserted);
- **mint** — a freshly grounded instance, pulling in domain structure beyond the bare
  shape requirement (asserts new things: needs evidence).

Only templates with a `name` parameter are usable (`_ground_template` returns `None`
otherwise).

**The engine filters `repair_libraries` for relevance before matching.** For each
failing hole it works out the `rdf:type`s the hole requires (from the hole's shapes),
then keeps only templates whose `name` type is *comparable* to a required type along
`rdfs:subClassOf` — a subclass it can **mint**, a superclass it can **reuse** via a
more-specific existing node. Templates that can't possibly fill the hole are dropped
*before* the expensive monomorphism search runs. Templates that type `name` only through
a dependency are kept (relevance is undecidable, so the engine stays conservative and
never drops a possible fix). Verified: an 81-template library with one relevant template
is cut to that one; a superclass-typed template survives for the reuse path.

Because of the filter, `RepairConfig.max_templates` (default **25**) applies to the
*already-filtered* candidate set and so rarely binds — the engine reaches for the cap
only when many genuinely-relevant templates survive. When it does bind it drops in
library order and warns once. So passing a large library is no longer a hard cliff, but
it's still wasteful (the filter must type-check every template, and any survivors beyond
the cap are dropped arbitrarily). **Prefer a small, purpose-built library** — a
two-template repair library is enough for most gaps.

Budgets are caller-controllable via `RepairConfig`:

```python
from buildingmotif.dataclasses import RepairConfig

ctx = model.validate(
    [sc],
    repair_libraries=[small_lib],
    repair_config=RepairConfig(max_templates=None),   # None = uncapped (filter still applies)
)
```

`RepairConfig(max_templates=25, max_branches=4, build_fuel=6, candidate_limit=16)` —
the defaults reproduce the historical hard-coded values. With the relevance filter,
`max_templates=None` is usually safe now: the filter, not the cap, is what bounds the
per-template monomorphism searches.

Two more things the engine does so repair-time matching stays cheap, both transparent to
callers:

- It **projects the ontology** to just the triples the matcher reads
  (`rdfs:subClassOf` + `rdfs:subPropertyOf` + `a owl:Class`) once, instead of walking all
  of `shapes_graph + data_graph` on every subgraph check.
- It **memoizes** each template's reuse candidates (they don't change across witnesses).

Keep repair templates **small** (a few triples) regardless — a small body is both a
better repair unit and cheaper to match, and it's what a good repair template looks like
anyway.
