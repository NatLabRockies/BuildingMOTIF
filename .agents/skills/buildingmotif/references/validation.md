# Validation: writing BuildingMOTIF scripts

This is the script-first reference for **read-only** use of BuildingMOTIF: *does this
model conform, and if not, what exactly is missing?* It is the file to reach for when you
are writing a Python script (or notebook cell) to validate a model, list templates, dump a
shape library's contents, or report validation failures in building terms. **Repair**
(proposing and applying fixes) is a separate concern in `repair.md` — start here, go there
only when the user asks to fix things.

Source of truth on disk (find with
`python -c "import buildingmotif.X as m; print(m.__file__)"`):
`buildingmotif/dataclasses/model.py`, `compiled_model.py`, `validation.py`,
`algebraic_validation.py`, `shape_collection.py`, `library.py`, `template.py`.

## What "validation" means here

Validation answers: **does graph *G* conform to shape graph *S*?** BuildingMOTIF runs
SHACL, but it wraps the result so you read *building* gaps ("VAV-1 has no temperature
sensor"), not raw W3C ValidationReport triples. The flow is always:

```
Model + ShapeCollections  ──compile()──▶  CompiledModel  ──validate()──▶  Context
                                                                          │
                                            ┌─────────────────────────────┤
                                            ▼                             ▼
                              AlgebraicValidationContext         ValidationContext
                              (pyshifty, default — use this)      (topquadrant; never pyshacl)
```

- **compile** = run SHACL inference (the shapes' ontology rules, subclass closure, etc.)
  over the model graph, folding in the shape collections, producing a *compiled graph*
  that has all inferred triples materialized. You usually don't call `compile()` directly
  — `model.validate(...)` does it for you. You'll call it directly only to inspect the
  compiled graph without validating (rare), or to reuse one compiled model against several
  shape sets.
- **validate** = check the compiled graph against the shapes and return a *context* object
  holding the results.

**Two context types, decided by `shacl_engine`** (default `"pyshifty"`):

| Engine | Context type | `ctx.valid` | Failure surface | Repair? |
|---|---|---|---|---|
| `pyshifty` (default) | `AlgebraicValidationContext` | bool | `ctx.witnesses` (one per failing focus+statement) | yes (`repair.md`) |
| `topquadrant` (rare, Java-backed) | `ValidationContext` (legacy) | bool | `ctx.diffset` (focus → `GraphDiff`s parsed from a W3C report) | legacy `as_templates()` only |

Both expose a **compatible read surface**, and that compatibility is now an explicit
contract: the `ValidationResult` protocol in
`buildingmotif.dataclasses.validation_result`, which both context classes satisfy
structurally. It covers `ctx.valid` / `ctx.conforms`, `ctx.report_string`, `ctx.report`
(a W3C SHACL report graph), `ctx.model`, `ctx.shape_collections`, `ctx.shapes_graph`,
`ctx.diffset` (focus → set of failures), `ctx.get_broken_entities()`,
`ctx.get_diffs_for_entity(focus)`, `ctx.get_reasons_with_severity(...)`, and
`ctx.as_templates()`. So a script that only *reads* failures can treat them identically,
and `Model.validate(...)` is typed as returning `ValidationResult` — no `isinstance`
branch needed:

```python
from buildingmotif.dataclasses import ValidationResult

def report(ctx: ValidationResult) -> None:      # works for either engine
    for focus, failures in ctx.diffset.items():
        for f in failures:
            print(focus, f.reason())
```

The individual failures satisfy a `Failure` protocol (`.focus` + `.reason()`), so the
read loop above is engine-independent too. The difference is what those failure *objects*
can additionally do: `RepairWitness` (algebraic, rich, repairable) vs `GraphDiff` (legacy,
parsed, limited). Narrow to the concrete class — or just use `ctx.witnesses` — when you
want the pyshifty-only repair surface.

**Never pass `shacl_engine="pyshacl"`.** `pyshifty` is a strict superset for this skill's
purposes: standard W3C SHACL-Core validation, `ctx.report`/`ctx.report_string` as a
conforming W3C report graph, and — as of `pyshifty` 0.2.7 — improved SPARQL-based
SHACL-AF rule inference (`sh:rule` Triple Rules and SPARQL Construct Rules), which was the
one place a gap could plausibly have pushed someone toward `pyshacl`. It's also the only
engine that repairs. There is no case in this skill's workflows where `pyshacl` is the
right choice. `topquadrant` remains available (needs a JVM; see `SKILL.md`'s
"Installation") only for the rare case of cross-validating against a separate, Java-based
implementation — it is not what this skill teaches by default and is not repair-capable.

## The minimal validate-and-report script

```python
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model

bm = BuildingMOTIF("sqlite://")   # tables are created automatically

# Load the ontology + shapes you need (see ontology_imports.md for owl:imports).
brick = Library.from_ontology("brick/Brick.ttl", run_shacl_inference=False)
shapes_lib = Library.from_ontology("path/to/my_shapes.ttl")  # or inline graph

# Load (or create) the model.
model = Model.from_file("path/to/model.ttl")

ctx = model.validate(
    [shapes_lib.get_shape_collection()],
    error_on_missing_imports=False,   # validate against what's loaded; see below
)

if ctx.valid:
    print("conforms")
else:
    for focus, witnesses in ctx.diffset.items():
        label = focus if focus is not None else "(model-level)"
        for w in witnesses:
            print(f"  {label}: {w.reason()}")
```

This is the loop to copy. Everything below is variations on it: how to read the failures
well, how to get the shapes, how to list templates, how to dump a library.

## Validation is the top of a loop, not a one-shot check

The first `ctx.valid == False` is the **start** of the work, not the end. BuildingMOTIF's
intended workflow is iterative: validate → read the gaps → fix one (with evidence) →
**re-validate** → repeat until conforming. The reason it must loop is that **fixing one
failure surfaces new ones** — add the missing supply fan to an AHU and that fan now has
its own shape requiring points it doesn't have yet (the `model_correction` tutorial walks
through exactly this: the AHU's fan shape fails on the next validation pass). Some fixes
also *discharge* other failures: a node minted for one witness can satisfy another.

So expect to call `model.validate(...)` many times against the same (growing) model, and
read a *fresh* `ctx` each iteration — don't cache the context across edits. The fix step
itself lives in `repair.md` (and the evidence step in `evidence.md`); this file is the
read side you return to every iteration. The overarching loop is described in `SKILL.md`.

One consequence for reading results: **don't report the full violation horizon as a
fixed work order.** The set of failures changes after each fix, so report the *current*
pass's gaps, fix one, re-validate, and report the next pass. Reporting all 20 failures up
front and then grinding through them blind will mislead, because the fix to #3 may make
#7–#12 disappear (or newly appear).

## Reading validation failures in building terms

`ctx.diffset` is a `dict[focus_node, set[Failure]]`. `focus` is the failing entity
(`None` for graph-level failures like "model has no AHU at all"). Each failure has a
`.reason()` returning a human string. Group by focus to present the violation horizon the
way a building engineer reads it:

```python
for focus, failures in ctx.diffset.items():
    who = str(focus) if focus is not None else "the whole model"
    print(who)
    for f in failures:
        print("  -", f.reason())
# urn:bldg/vav1
#   - urn:bldg/vav1 expected at least 1 value on path brick:hasPoint
# urn:bldg/vav2
#   - urn:bldg/vav2 expected at least 1 value on path brick:hasPoint
```

`ctx.report_string` is the engine's own textual report (the pyshifty algebra report for
`pyshifty`, a flattened W3C report string for legacy) — useful as a fallback when a
`.reason()` is opaque, or to paste into a bug report. `ctx.report` is the W3C SHACL
ValidationReport as an `rdflib.Graph` if you need to query it directly (e.g. severity
paths, `sh:resultPath`).

### Severity filtering

```python
from buildingmotif.namespaces import SH
violations = ctx.get_reasons_with_severity(SH.Violation)      # or "Violation"
warnings    = ctx.get_reasons_with_severity(SH.Warning)
```

Returns the same focus→failures shape, filtered. Most app-sufficiency questions care only
about `Violation`; `Warning`/`Info` are informational.

### The `pyshifty` witness (richer, if you have it)

With the default engine each failure is a `RepairWitness`. Beyond `.reason()` it exposes
`.explain()` — the indented AND/OR/Repeat tree of *typed holes* showing the space of edits
that would fix this one failure. `.reason()` is validation information; `.explain()` and
`.repair_summary` are repair information. Do not interpret a repair atom such as
`CountHigh` as the source constraint that failed:

```python
for w in ctx.witnesses:
    print(w.reason())
    print(w.validation_reasons)  # structured value/path/severity findings
    print(w.target_shape)        # named algebra shape/statement, when available
    print(w.violation)           # full native algebraic violation
    print(w.violation_alignment) # how it was paired with the repair witness
    print(w.statement_id)        # native algebra statement identifier
    print(w.constraint_id)       # statement-level algebra id
    print(w.constraint_kind)     # enumerated top-level algebra operator
    print(w.constraint)          # complete top-level algebra constraint
    print(w.selector)            # focus selector for that statement
    print(w.target)              # rendered algebra target
    print(w.graph)               # complete compiled data graph
    print(w.source_constraints)  # native reason-level algebra constraints
    print(w.repair_summary)      # structured repair alternatives
    print(w.explain())
    print("blocked?", w.is_blocked)   # True = opaque constraint, no data repair possible
```

Use `ctx.algebra` for the complete native `validate_algebra()` result and
`ctx.violations` for its unmodified violation tuple. BuildingMOTIF joins the
independently computed validation and repair results by pyshifty's stable
`(focus, statement_id, constraint_id)` identity, reported as
`w.violation_alignment == "stable-id"`. `unavailable` means no safe join could
be made; BuildingMOTIF never falls back to positional correlation.

The algebraic witness is deliberately independent of the shapes graph's Turtle/blank-node
encoding. `w.constraint` is the statement-level algebra used to synthesize repair.
Each `w.validation_reasons` entry has its own `.constraint`, `.constraint_id`, and
`.constraint_kind` identifying the specific, potentially nested algebra node that
produced that cause. Repair atoms likewise carry leaf-level constraint provenance,
but it describes the edit alternative and is not substituted for validation provenance.
`failed_shape` and `failed_component` remain empty unless pyshifty explicitly preserves
those W3C fields; BuildingMOTIF will not infer them from repair atoms. Use `ctx.report`
only when you explicitly want the separate W3C report view.

`w.is_blocked` matters even for read-only validation: a blocked witness (opaque SPARQL,
identity, coinductive back-edge) means the failure is real but *no data edit can discharge
it* — the shape or constraint itself must change. Report that plainly ("this count
constraint can't be fixed by adding data") instead of looping. (Background in `repair.md`;
the legacy `GraphDiff` has no `is_blocked` — every failure there is nominally repairable.)

### "Why didn't my shape fire?"

The classic validation bug is a shape that **passes vacuously** because it never targeted
anything. Diagnose by deliberately breaking the model and confirming the shape *can* fail:

```python
# sanity check: remove a point you know a shape requires, re-validate, confirm it fails
model.add_triples(...)  # or remove — then ctx.valid must become False
```

If a shape that should fire reports `ctx.valid == True` on a model you know is broken,
check (in this order): the shape has `sh:targetClass` (or is reached via a manifest / a
targeting shape), the targeted class is actually instantiated in the model, and the shape
collection was actually passed to `validate(...)` (passing shape collections *replaces* the
manifest — it does not augment it). Details and the common shape bugs in `writing_shapes.md`.

## `error_on_missing_imports`: the one flag to understand

`model.validate(..., error_on_missing_imports=...)` controls what happens when a shape (or
the model) `owl:imports` an ontology OntoEnv could not resolve:

- `True` (default) → raises `OntologyImportsNotFound`, listing the unresolved IRIs.
- `False` → resolves what it can, logs the rest as a warning, and validates against what's
  loaded.

With OntoEnv fetching imports by default (`ontology_fetch_imports=True`), most imports are
resolved automatically and this flag rarely bites (see `ontology_imports.md`). Reach for
`False` when validating a *real* model whose shapes import a site vocabulary you don't
have — you get a report now, against a partial graph. **But** a clean report from a partial
graph is not trustworthy: shapes from a missing import simply didn't fire. Check
`bm.ontology_environment.missing_imports(model.graph)` (or the shape collection's graph) so
you know what you're missing before declaring success.

## Compiling without validating (inspect the inferred graph)

`compile()` runs SHACL inference (the ontology's subclass/property rules, etc.) over the
model + shape collections and returns a `CompiledModel` whose `.graph` is the materialized
inference. Useful when you want to see *what inference produced* — e.g. did the engine
infer `brick:connectedTo` between two points? — without running a full validation:

```python
compiled = model.compile([brick.get_shape_collection()])
g = compiled.graph
# ask a question of the inferred graph directly
ask = g.query(
    "ASK { <urn:bldg/vav1> brick:hasPoint ?t . ?t a brick:Temperature_Sensor }"
)
print(bool(ask))
```

`CompiledModel` also carries `.shape_collections`, `.shacl_engine`, and
`.defining_shape_collection(shape_uri)` (which shape collection defines a given shape —
handy when debugging which library a constraint came from). `compiled.validate(...)` takes
the same args as `Model.validate` minus `shape_collections` (they're already baked in).

## Listing what's in a library

A `Library` holds **templates** (YAML-defined or decompiled from shapes) and a **shape
collection** (the RDF graph the templates/shapes live in). Two views:

```python
lib = Library.from_directory("/path/to/library")   # or ontology_graph=..., name=...

# Templates in the library:
for t in lib.get_templates():
    print(t.name, sorted(t.parameters))
t = lib.get_template_by_name("vav-cooling-only")

# The shape collection (the RDF — shapes, classes, ontology axioms):
sc = lib.get_shape_collection()
print(len(sc.graph), "triples")
print(sc.graph_name)   # the owl:Ontology IRI, or None
```

`lib.name` is the ontology IRI (the subject of `a owl:Ontology` in the loaded graph) —
that's how a library is keyed in the DB, and how `Library.by_name(...)` reloads it.

### Inspecting a template

```python
t = lib.get_template_by_name("vav-cooling-only")
t.name                  # "vav-cooling-only"
t.parameters            # set of *local* params (excluding deps), e.g. {'name','ztemp'}
t.optional_args         # set of optional params
t.parameters_with_dependencies()   # + deps, named as they will be after inlining
t.parameters_with_dependencies(transitive=False, renamed=False)  # direct deps, own names
t.parameter_counts       # Counter over this template + transitive deps
t.body                  # rdflib.Graph — the template body (PARAM nodes are the params)
t.get_dependencies()    # tuple of Dependency records (template + arg bindings)
t.body.serialize(format="turtle")   # read the body as TTL
```

`PARAM` is `urn:___param___#`; a parameter named `name` is the node
`urn:___param___#name`. Parameters are *exactly* the `PARAM`-namespace nodes in the body.
`inline_dependencies()` returns a single flattened template with all deps inlined — read
its `.parameters` to see the full surface, but note inlining can be expensive for matching
(`templates.md`).

### Inspecting a shape collection

```python
from buildingmotif.namespaces import BMOTIF, SH
sc = lib.get_shape_collection()

# All node shapes:
shapes = list(sc.graph.subjects(SH.NodeShape, None))   # raw, or:

# Shapes tagged with a bmotif: definition type (libraries use these to organize):
specs = sc.get_shapes_of_definition_type(BMOTIF["System_Specification"], include_labels=True)
for shape, label in specs:
    print(shape, label)

# Shapes whose domain is X:
sc.get_shapes_of_domain(BMOTIF["HVAC"])

# Shapes that target a given class (or its superclasses) — i.e. "what applies to a VAV?":
from buildingmotif.namespaces import BRICK
applicable = sc.get_shapes_about_class(BRICK["VAV"])
```

`get_shapes_of_definition_type` / `get_shapes_of_domain` / `get_shapes_about_class` are
graph queries — they do **not** resolve `owl:imports`, so they work even on a library whose
import closure isn't fully loaded. Use them to discover shapes; then validate against the
ones you want (see `writing_shapes.md` for the `bmotif:` definition-type vocabulary and writing
your own).

## A complete "is this model sufficient?" script

Putting it together — the script you'll actually write when a user asks "does my model
support application X?":

```python
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.namespaces import SH

bm = BuildingMOTIF("sqlite://")   # tables are created automatically

# 1. Load ontologies + the application's shapes.
brick = Library.from_ontology("brick/Brick.ttl", run_shacl_inference=False)
app_shapes = Library.from_ontology("my_app_requirements.ttl")

# 2. Load the model.
model = Model.from_file("building.ttl")

# 3. Validate against the app's shapes (NOT the manifest — see below).
ctx = model.validate(
    [app_shapes.get_shape_collection()],
    error_on_missing_imports=False,
)

# 4. Report in building terms.
if ctx.valid:
    print("Model supports the application.")
else:
    print("Model is missing requirements:")
    for focus, failures in ctx.diffset.items():
        who = str(focus) if focus is not None else "the whole model"
        for f in failures:
            print(f"  {who}: {f.reason()}")

# 5. If you need to know what's unresolved (don't trust a clean partial-graph report):
missing = bm.ontology_environment.missing_imports(model.graph)
if missing:
    print("WARNING: unresolved imports (shapes from these did not fire):", missing)
```

Two things in this script that trip people up:

- **Passing shape collections replaces the manifest.** `model.validate([sc1, sc2])`
  validates against *only* `sc1, sc2` — the model's standing manifest is **not** added.
  That's usually what you want for an ad-hoc "does it support *this* app?" check. To
  validate against the manifest plus extras, spread `model.manifest.shape_collections()`
  into the list. `model.validate()` with no list validates against the manifest alone —
  that is, against the shape collections of every library the manifest names.
- **The no-argument form is also the faster one.** A manifest is an ontology whose
  `owl:imports` name its members, so `model.validate()` resolves them as a single OntoEnv
  closure rooted at the manifest instead of resolving each collection's imports separately
  — flat in the number of members rather than linear. Passing an explicit list gives up
  that path, since a bare list has no manifest to root a closure at.
- **`error_on_missing_imports=False` is the notebooks' default for real models.** A real
  model's shapes usually `owl:imports` something you haven't loaded; with `True` (the
  default) validation raises and stops. `False` gets you a report now — but always check
  `missing_imports` so a "conforms" result isn't hiding shapes that never fired.

## When to stop reading and switch files

- **You want to fix the failures** (propose/add triples) → `repair.md`. Validation gave
  you the gaps; repair is the loop that closes them with evidence.
- **You're writing/fixing the shapes themselves** (pointlists, app requirements, the
  `bmotif:` vocabulary) → `writing_shapes.md`.
- **Imports failed / you need offline or caching knobs** → `ontology_imports.md`.
- **You're building a model from templates** (not validating an existing one) →
  `building_models.md`.
