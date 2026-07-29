---
name: buildingmotif
description: Use BuildingMOTIF to validate, repair, and build building and water-system metadata models (Brick/223P/WaTr/SHACL). Covers writing scripts to validate a model and expose failures in domain terms, listing templates and inspecting shape libraries, algebraic (pyshifty) validation and soundness-gated graph repair, finding and filling templates, and writing/debugging shapes for pointlists and application requirements. Use when the user mentions BuildingMOTIF, Brick, 223P, WaTr, SHACL shapes/validation, repair proposals or witnesses, pointlists, templates, or asks whether a model is "sufficient" for an application.
---

# BuildingMOTIF

BuildingMOTIF answers one question in several forms: **does this building model carry
enough metadata to run an application, and if not, exactly what is missing and how do
we add it?**

- **Shapes** (SHACL) state requirements: what an application needs.
- **Templates** generate graph fragments: the domain vocabulary for filling gaps.
- **Validation** finds the gaps — *read-only*: does the model conform, and if not, what
  is missing? With the `pyshifty` engine (the default) it also *proposes* repairs.
- **Repair** proposes and applies triples to close the gaps, gated for soundness and
  checked against evidence before applying. Repair is the second half of the loop;
  validation is the first.

This skill assumes **BuildingMOTIF is used as an installed Python package**, not run from
a checkout of the NatLabRockies/BuildingMOTIF repository. That's about the `buildingmotif`
package your scripts `import` — not about these skill files themselves, which (until this
skill is packaged separately) you still have to pull from the repository once, by whatever
lightweight means you like; see `docs/guides/agent-skill.md` if you need that part spelled
out. All imports come from the `buildingmotif` package; the only filesystem paths used are
the user's own model/shape files and the *builtin libraries* that ship inside the package
(see below).

### Installation: install from the `gtf-buildingmotif` branch, not PyPI

The PyPI release lags this skill — `pyshifty`/algebraic repair, the OntoEnv-backed import
resolution, and the Oxigraph store are all only on `gtf-buildingmotif`, an integration
branch on NatLabRockies/BuildingMOTIF that carries the latest merged features ahead of their
individual PRs into `develop` (see the repo's `BRANCHES.md` if you have a checkout handy —
you don't need one for this). Install straight from that branch with `uv`:

```bash
# in a project managed by uv
uv add "buildingmotif @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"

# add the Java-backed TopQuadrant SHACL engine too (needs a JVM on PATH)
uv add "buildingmotif[topquadrant] @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"

# one-off install, no persistent pyproject.toml
uv pip install "buildingmotif @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"

# run the CLI without installing anything persistent
uvx --from "git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif" buildingmotif …
```

This is still an **installed package**, not a source checkout: `uv` clones the branch into
an isolated build environment and installs the built wheel into your project's venv, so you
get `import buildingmotif` from `site-packages` — no repo directory to `cd` into or run
scripts relative to. Everything in this skill (imports, builtin library paths, "not run
from a checkout") holds exactly as it would installing from PyPI; only the source URL
changes. `pyshifty` is a required dependency (not an extra) on this branch, so the default
`shacl_engine="pyshifty"` path needs nothing beyond the plain install above.

`gtf-buildingmotif` is a moving integration target (rebased/force-pushed as feature
branches land) — pin `@<commit-sha>` instead of `@gtf-buildingmotif` for a reproducible
install, e.g. in CI or a shared requirements file.

## Core rule: never invent metadata

A repair adds triples asserting facts about a **real building**. The engine guarantees a
repair is *logically* sound (it introduces no new SHACL violation) — it says nothing
about whether the repair is *true of the building*. A gated proposal that invents a
temperature sensor which does not physically exist is a sound repair and a false model.

So the loop is always: **gap → evidence → user → apply**. Find evidence in the user's
documents; when evidence is absent or ambiguous, ask the user. Never silently accept a
proposal just because it passed the gate, and never present a synthesized node as if it
were discovered.

## The iterative workflow (validate → fix → re-validate → repeat)

Validation and repair are **not one-shot**. The intended workflow — the one the tutorials
and notebooks walk through — is a loop, because **fixing one failure surfaces new ones**.
Adding the missing supply fan to an AHU makes the model pass *that* requirement, but the
fan now has its own shape requiring points it doesn't have yet. So:

1. **Validate** → `ctx = model.validate(...)` (`validation.md`).
2. **Read the gaps** in building terms — `ctx.diffset`, `w.reason()` (`validation.md`).
3. **Fix one failure** with evidence — pick a witness, find evidence, apply a repair
   (`repair.md` + `evidence.md`). Repair one witness at a time, not all at once.
4. **Re-validate** → back to step 1 with the patched model. New failures may appear;
   some old ones may now be discharged by what you just added.
5. Repeat until `ctx.valid` is `True` (or you've reported a shape that's wrong for the
   building — a legitimate exit, `writing_shapes.md`).

This is why `validation.md` and `repair.md` are separate but paired: validation is the
*top* of the loop (run it every iteration), repair is the *body* (fix one, then hand
back to validation). Do not batch a pile of repairs and validate once at the end —
repairs interact, and you won't know which one broke or unblocked what.

## Workflow router

| Task | Read |
|---|---|
| **Validate a model** and read/expose failures; list templates; inspect a shape library; write the validate-and-report script | `references/validation.md` |
| **Build a model** — template library + `Model.create` + `TemplateBuilderContext`, bind to evidence, compile, validate | `references/building_models.md` |
| Discover/verify Brick class names and inspect class shapes before asserting `a brick:X` | `references/brick_vocabulary.md` |
| Model ASHRAE 223P (`s223:`) topology — equipment/connections/connection points, properties, roles/domains/media | `references/223p_vocabulary.md` |
| Model a water treatment system with WaTr (`watr:`) — unit processes, treatment-process types, water media/constituents, and WaTr-on-223P patterns | `references/watr_vocabulary.md` |
| Build from point lists, BMS labels, BACnet object names, or other source metadata; map suffixes/tokens to Brick classes | `references/point_labels.md` |
| **Fix a model** — propose/apply repairs, drive the gap→evidence→user→apply loop | `references/repair.md` |
| **Write shapes** (pointlists, app requirements, manifests, `bmotif:` tags, `constraint:` vocabulary) | `references/writing_shapes.md` |
| **Write templates** (YAML bodies, parameters, dependencies, decompiling shapes) | `references/writing_templates.md` |
| Find evidence in point lists / submittals / BACnet dumps | `references/evidence.md` |
| Find, choose, and fill templates (evaluate, match against a model) | `references/templates.md` |
| Ontology `owl:imports` resolution, OntoEnv, offline/cache knobs | `references/ontology_imports.md` |

**If you only need to know whether a model conforms and what's missing, you want
`validation.md`, not `repair.md`.** Repair is for proposing and applying fixes; it is
the second half of the loop and assumes you have already validated.

## Setup (get this right or nothing else works)

```python
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model, Library

bm = BuildingMOTIF("sqlite://")   # in-memory; use a file/postgres URI to persist
bm.setup_tables()
```

`shacl_engine` defaults to **`pyshifty`**, so `model.validate(...)` already returns an
`AlgebraicValidationContext` (witnesses + repair). You do not need to pass
`shacl_engine="pyshifty"`; passing another engine silently downgrades you to the legacy
`ValidationContext` and makes `repair_libraries` a no-op warning.

### OntoEnv and the graph store

BuildingMOTIF resolves `owl:imports` through [OntoEnv](https://github.com/gtfierro/ontoenv),
an external ontology-dependency manager that ships as a main dependency. **Import fetching
is on by default** (`ontology_fetch_imports=True`), so loading a library whose shapes
`owl:imports` Brick/QUDT/REC now resolves and fetches them automatically — the
"could not resolve import of `<…qudt…>`" failures from the rdflib-sqlalchemy era are
gone in the common case. RDF triples (models, shape collections, template bodies, and
OntoEnv's resolved ontologies) live in an [Oxigraph](https://github.com/oxigraph/oxigraph)
store; metadata lives in SQL. See `references/ontology_imports.md` for the full model and
the knobs (`ontology_cache_path`, `ontology_search_directories`, `ontology_offline`,
`ontology_strict`, per-load `fetch_imports=`). The two you'll reach for:
`ontology_offline=True` (+ `ontology_search_directories`) for reproducible/airgapped
loads, and `ontology_cache_path` to persist resolved ontologies across sessions.

### Where libraries live (builtin vs. repo-only)

BuildingMOTIF resolves certain string paths against the **builtin libraries** packaged
inside `buildingmotif/libraries/` (via `pkg_resources.resource_exists` on the
`buildingmotif.libraries` namespace). These ship with the package install (see
"Installation" above):

| Builtin path (pass to `Library.load`) | Contents |
|---|---|
| `brick/Brick.ttl` | the full Brick ontology — **1444 templates**, including the class templates other libraries depend on |
| `constraints/constraints.ttl` | `bmotif:` constraint shapes (`exactCount`, etc.) for writing manifests |
| `bacnet/brick.yml` | BACnet→Brick templates used by the BACnet ingress |

**Sample application libraries** (`ashrae/guideline36`, `chiller-plant`,
`pointlist-test`, `223p`, `medium-office`, `ZonePAC`, …) are **not shipped in the
package** (see [NatLabRockies/BuildingMOTIF#133](https://github.com/NatLabRockies/BuildingMOTIF/issues/133)).
They live only in the repository's `libraries/` directory. To use them as a package user:

- **clone the repo** and point `Library.load(directory=...)` at the path, **or**
- **bulk-load via `libraries.yml`** with a `git:` entry that clones the repo at load
  time (see `references/templates.md`), **or**
- write your own templates/shapes inline — the YAML and SHACL formats are documented in
  `references/templates.md`.

### Other ontologies (Brick nightly, 223P, WATR, QUDT) — not shipped, not in the repo

None of these are builtin or in the repo's `libraries/`. With `ontology_fetch_imports=True`
(the default) OntoEnv fetches whichever of these a shape or model actually `owl:imports`,
so most of the time you don't load them by hand at all — see `references/ontology_imports.md`.
Reach for the table below when you need a newer/specific version than what auto-fetch
resolves, or a local copy for `ontology_search_directories` / offline loads:

| Ontology | Where to get it | Notes |
|---|---|---|
| **Brick** (unreleased/newer than the builtin) | [Nightly Build release on GitHub](https://github.com/BrickSchema/Brick/releases/tag/nightly) — `Brick.ttl` asset, rebuilt continuously off `master` | The builtin `brick/Brick.ttl` (above) is pinned to a release; use the nightly asset when you need a fix that hasn't been tagged yet. `Brick-only.ttl` (no imports) and `Brick+imports.ttl` are also published there. |
| **223P** | [open223.info](https://open223.info) — `/223p.ttl` for the current version | Community-maintained ASHRAE 223P tooling/ontology hub, not an official ASHRAE distribution. Modeling patterns and vocabulary: `references/223p_vocabulary.md`. |
| **WATR** | [watermetadata.org](https://watermetadata.org) — ontology download link on the site (`water.ttl`); source at [github.com/DataDrivenCPS/water-ontology](https://github.com/DataDrivenCPS/water-ontology) | NAWI-funded water-systems metadata ontology; Brick's counterpart for water. |
| **QUDT** | dereference its own namespace URIs (e.g. `http://qudt.org/schema/qudt/`, `http://qudt.org/vocab/unit/`) | Don't vendor a copy — QUDT's IRIs are the canonical, dereferenceable source; OntoEnv/rdflib resolve them directly when fetching is on. |

Same load-order rule as Brick applies here: if a library's templates depend on 223P or WATR
class templates, load that ontology **before** the dependent library.

### Loading Brick (the one load-order rule that matters)

```python
# Builtin resource path — auto-resolved from the package, no local files needed.
# ~6s; with ontology_fetch_imports=True (the default) OntoEnv also resolves Brick's
# owl:imports (REC, QUDT pieces). If you only need the class templates and want it
# faster, pass fetch_imports=False — the 1444 class templates load regardless.
brick = Library.load(ontology_graph="brick/Brick.ttl", run_shacl_inference=False)
```

Load Brick **before** any library that depends on it. Libraries like
`libraries/ashrae/guideline36` declare dependencies on Brick class templates
(e.g. `brick:Damper_Position_Command`). If Brick is not loaded first,
`inline_dependencies()` raises `TemplateNotFound` naming a Brick class — that error
means "load Brick first", not "the template is broken".

Use the **canonical** `brick/Brick.ttl` (builtin), with `run_shacl_inference=False`.
Do **not** substitute `Brick-full.ttl` or leave inference on — those do not produce the
class templates that other libraries depend on. See `references/templates.md`.

Loading Brick is **fast** — ~6s, and `get_templates()` over its 1444 templates is
~0.3s. If something appears to hang, it is almost certainly `TemplateMatcher`, which is
exponential in template size (`references/templates.md`), not the library load.

### One gotcha when validating against library shapes

Validating a model against a **self-contained** shape graph (one you wrote, with no
`owl:imports` to unshipped ontologies) works out of the box — this is the normal case
and what `references/writing_shapes.md` and `references/repair.md` teach.

Validating against a library whose shapes transitively `owl:imports` Brick's QUDT/REC
dependencies (the guideline36 shapes do this) used to raise
`Could not resolve import of <…qudt…>` because some QUDT collections are not packaged.
**With OntoEnv (now the default, `ontology_fetch_imports=True`) those imports are
fetched/resolved automatically**, so this case usually just works now — see
`references/ontology_imports.md`. Remaining failures mean an import OntoEnv couldn't find
locally *or* fetch (genuinely broken, or you're offline): go online, load the file
yourself, add its directory to `ontology_search_directories`, or pass
`error_on_missing_imports=False` to proceed against what's loaded. Details in
`references/writing_shapes.md` and `references/ontology_imports.md`.

## The shape of a session

Most real requests are one of these:

1. *"Is my model good enough for X?"* → write/obtain shapes for X, **validate**, and
   report the gaps in building terms (not SHACL jargon). → `references/validation.md`
   (then `references/writing_shapes.md` for writing the shapes).
2. *"Fix my model."* → the repair loop, with evidence and user confirmation. →
   `references/repair.md` + `references/evidence.md` (validate first, per `validation.md`).
3. *"Build a model of this equipment."* → use BuildingMOTIF's machinery: create/reuse a
   template library, `Model.create`, `TemplateBuilderContext` to wire templates and bind
   to real identifiers from evidence, then compile and validate. →
   `references/building_models.md` (+ `references/writing_templates.md` if you need to
   author templates, `references/evidence.md` for the identifiers,
   `references/brick_vocabulary.md` to verify class names — or
   `references/223p_vocabulary.md` if the model is 223P topology, not Brick points;
   add `references/watr_vocabulary.md` when the domain is water treatment).
4. *"Build a model from this point list / BMS labels / BACnet object names / schedule."*
   → first map source tokens to verified Brick classes, then synthesize graph fragments or
   template bindings and validate. → `references/point_labels.md` +
   `references/brick_vocabulary.md` + `references/building_models.md`.
5. *"What's in this library?" / "list the templates" / "show me the shapes"* →
   `references/validation.md` (the library/template/shape-collection inspection scripts).

Report findings the way a building engineer reads them: "VAV-1 has no temperature
sensor" beats "`CountLow` on path `brick:hasPoint`". Keep the SHACL detail available for
when they ask.

## Reference material (when docs aren't on disk)

Because this skill runs against an installed package, the in-repo documentation and
notebooks are not on the local filesystem by default. They are all on the web:

- Docs (Sphinx/jupyter-book): <https://buildingmotif.readthedocs.io/> — see especially
  `explanations/templates.md`, `explanations/shapes-and-templates.md`,
  `explanations/point-label-parsing.md`, `tutorials/model_validation.md`,
  `tutorials/model_creation.md`, `reference/cli_tool.md`.
- Repair theory (`algebraic-repair.md`) and runnable notebooks:
  <https://github.com/NatLabRockies/BuildingMOTIF> (`algebraic-repair.md` at the repo root;
  `notebooks/Existing-model-repair-with-pyshifty.ipynb` — minimal end-to-end;
  `notebooks/Existing-model-validation-with-pyshifty.ipynb` — real-model validation plus
  a repair playground with labelled experiments A–G;
  `notebooks/Template-Usage.ipynb`, `notebooks/Shape_Builder.ipynb`).
- API autodoc: `docs/reference/apidoc/` in the repo, mirrored on readthedocs.

The reference files in this skill fold in the load-bearing parts of those docs so you
rarely need to leave the session, but the links above are authoritative.
