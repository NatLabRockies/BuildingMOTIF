# Ontology imports and OntoEnv

BuildingMOTIF resolves `owl:imports` through [OntoEnv](https://github.com/gtfierro/ontoenv),
an external ontology-dependency manager. This is what makes "validate a model whose shapes
`owl:imports` Brick/QUDT/REC" actually work without the user hand-loading every transitive
dependency. It is a main dependency (`ontoenv` in `pyproject.toml`) and ships with the
package — no extra install.

This file covers the resolution model and the knobs that control it. Source of truth on
disk: `buildingmotif/ontology_environment.py` (`OntologyEnvironment`,
`BuildingMOTIFGraphStore`, `OntologyImportsNotFound`) and the `ontology_*` params on
`buildingmotif.building_motif.building_motif.BuildingMOTIF.__init__`.

## The one-paragraph model

Every `BuildingMOTIF` instance owns an `OntologyEnvironment` (`bm.ontology_environment`)
wrapping an `ontoenv.OntoEnv`. When a library or shape collection is loaded with import
fetching on (the default), OntoEnv walks the graph's `owl:imports`, resolves each one
(local search directories first, then remote fetch unless offline), and stores the
resolved closure in BuildingMOTIF's **Oxigraph graph store** — the same store that holds
models and shape collections, but keyed by **ontology IRI** rather than UUID. Later
`owl:imports` of the same ontology are satisfied from that cache. Unresolved imports are
reported, not silently dropped.

The net effect for a skill user: **the import-resolution gotcha that used to bite
validations against library shapes is largely gone.** A shape that `owl:imports` a remote
ontology now gets that ontology fetched by default. You only need to think about imports
when you want to *suppress* fetching (offline, speed) or when an import genuinely cannot
be resolved.

## What OntoEnv does at load time

`Library.load(ontology_graph=..., fetch_imports=...)` (and `directory=`) registers the
graph with OntoEnv and, when `fetch_imports` is true, resolves its import closure:

- `bm.ontology_environment.add(source, fetch_imports=...)` — registers the ontology,
  optionally fetching its `owl:imports`. Returns the ontology's IRI (the subject of
  `a owl:Ontology`).
- `bm.ontology_environment.closure_copy(name)` — returns the resolved import closure as
  a fresh `rdflib.Graph` plus the list of ontology names in the closure.
- For each imported ontology, BuildingMOTIF creates a `Library` row (with
  `infer_templates=False`, `run_shacl_inference=False`) so the dependency is queryable
  like any other library.

So loading Brick also brings in its declared imports (REC, QUDT pieces, etc.) as their
own library rows — this is why the "could not resolve import of `<…qudt…>`" failures from
the old rdflib-sqlalchemy era no longer happen by default.

## The knobs (on `BuildingMOTIF.__init__`)

```python
bm = BuildingMOTIF(
    "sqlite:///bm.db",
    # OntoEnv workspace. A path persists the resolved-ontology cache across sessions
    # (fast reload). Omit for an in-memory temporary env (rebuilt each process).
    ontology_cache_path="./bm-ontoenv",
    # Extra directories OntoEnv scans (recursively) when resolving imports, in addition
    # to the builtin libraries and any graph already in the store.
    ontology_search_directories=["/path/to/my/ontologies"],
    # Default for *library loading*: should Library.load fetch owl:imports? Most users
    # want True (the default). Set False to load just the file you named and nothing more.
    ontology_fetch_imports=True,
    # If True, OntoEnv never fetches remote imports — only local search resolves them.
    # Use when running without network, or to make loads deterministic/offline-reproducible.
    ontology_offline=False,
    # If True, unresolved imports are a hard error instead of a warning. Useful in CI to
    # catch a model that quietly dropped a dependency.
    ontology_strict=False,
)
```

Two of these are the ones you will actually reach for:

- **`ontology_offline=True`** when you have no network (CI airgap, laptop on a plane) or
  you want to guarantee loads are reproducible from local files. Pair with
  `ontology_search_directories` pointing at a checkout of the ontologies you need.
- **`ontology_cache_path`** when you load ontologies repeatedly (a notebook, a long-lived
  service). The first load resolves and caches; later processes with the same path reuse
  the resolved graphs without re-fetching. With the default (no path), the env is
  in-memory and dies with the process.

`ontology_fetch_imports` is the *default* for `Library.load`; `Library.load(...,
fetch_imports=False)` overrides it per-load (e.g. load Brick fast for template work
without pulling QUDT).

## Per-load control: `Library.load(fetch_imports=...)`

```python
# Default: fetches imports (uses bm.ontology_fetch_imports, which is True by default).
brick = Library.load(ontology_graph="brick/Brick.ttl", run_shacl_inference=False)

# Skip import fetching — load exactly this file. Faster, and fine when you only need the
# class templates (template decompilation doesn't need the QUDT/REC closure).
brick = Library.load(ontology_graph="brick/Brick.ttl",
                     run_shacl_inference=False, fetch_imports=False)
```

`fetch_imports=None` (the default) inherits `bm.ontology_fetch_imports`. Pass an explicit
bool to override for this one load.

## Validation-time resolution: `resolve_imports`

`ShapeCollection.resolve_imports()` is what validation calls (via `model.validate` /
`CompiledModel`) to fold an ontology's closure into the shapes. It goes through OntoEnv:

```python
sc = brick.get_shape_collection()
resolved = sc.resolve_imports(error_on_missing_imports=False)
```

- It calls `bm.ontology_environment.import_dependencies(graph, recursion_depth=...,
  fetch_missing=bm.ontology_fetch_imports)`, which inlines the import closure into a copy
  of the graph.
- `recursive_limit` (on `resolve_imports`) caps the depth; `-1` (default) is unlimited.
- After resolving, it asks `bm.ontology_environment.missing_imports(graph)` for anything
  it could not satisfy. With `error_on_missing_imports=True` (the default) that raises
  `OntologyImportsNotFound(imports)` listing the unresolved IRIs; with `False` it logs a
  warning and proceeds with what it has.

This is why `model.validate(..., error_on_missing_imports=False)` works against a partial
model: OntoEnv resolves what it can, and the validator proceeds over the resolved shape
graph even if some imports are missing. With `ontology_fetch_imports=True` and network
available, "missing" usually means an ontology OntoEnv couldn't find locally *or* fetch
— the rare genuinely-broken import, not the common "you forgot to load QUDT."

## When imports still fail

OntoEnv resolves an import by (1) finding it in a search directory, (2) finding it already
in the graph store, or (3) fetching it remotely (unless `offline`). A import fails to
resolve when all three are false: it's not on disk locally, not already loaded, and either
you're offline or the IRI isn't fetchable. Symptoms and fixes:

| Symptom | Cause / fix |
|---|---|
| `OntologyImportsNotFound: Could not resolve ontology imports: <…>` | An `owl:imports` OntoEnv couldn't satisfy. Load the file yourself, add its directory to `ontology_search_directories`, go online (`ontology_offline=False`), or pass `error_on_missing_imports=False` to proceed without it. |
| Validation passes vacuously / shapes don't fire | An import that carried the `sh:targetClass` or class hierarchy didn't resolve, so the shapes are incomplete. Check `bm.ontology_environment.missing_imports(graph)`; don't just silence with `error_on_missing_imports=False` and trust the result. |
| Slow first load of Brick | OntoEnv is fetching the transitive closure (QUDT, REC). This is one-time per cache. Persist with `ontology_cache_path`, or `fetch_imports=False` if you only need templates. |
| Loads not reproducible in CI | Remote fetching is non-deterministic. Use `ontology_offline=True` + `ontology_search_directories` pinned to a checkout. |

**Don't reflexively pass `error_on_missing_imports=False` to hide an import failure.**
It's correct for "validate a real model now, against what's loaded" (the notebooks' use);
it's wrong as a way to ignore a shape graph whose imports you haven't sorted out, because
the shapes you didn't load are the ones that won't fire. Resolve the import or confirm
with `missing_imports` that you're only missing things you don't need.

## The graph store

OntoEnv's resolved ontologies live in the **same Oxigraph store** as BuildingMOTIF's own
graphs (models, shape collections, template bodies), through
`buildingmotif.ontology_environment.BuildingMOTIFGraphStore`. Two distinctions that matter
only if you're poking at the store directly:

- BuildingMOTIF graphs are keyed by **UUID** `graph_id`s referenced by SQL rows.
- OntoEnv graphs are keyed by **ontology IRI** and have *no* SQL row — OntoEnv's own
  registry is their source of truth.

Because of the IRI (not UUID) keying, OntoEnv graphs are **excluded from garbage
collection** by construction — `collect_graph_garbage` only deletes UUID-keyed graphs not
in the live set. You will not accidentally delete a cached ontology by running GC. See
`docs/explanations/storage-architecture.md` (in the repo / readthedocs) for the full
two-store model.

## Direct OntoEnv access (rarely needed)

Most users never touch `bm.ontology_environment` directly — `Library.load` and
`resolve_imports` cover it. The methods are there if you need them:

```python
env = bm.ontology_environment
env.ontology_names()                      # IRIs of all registered ontologies
env.graph_copy("https://brickschema.org/schema/Brick")   # fresh copy of one
env.closure_copy("https://brickschema.org/schema/Brick") # (graph, [names]) closure
env.missing_imports(some_graph)           # what owl:imports can't be resolved
env.add("/path/to/onto.ttl", fetch_imports=True)         # register + resolve manually
env.ensure_and_get_closure(graph, name)   # register if needed, return closure
```

`OntologyEnvironment.graph_name(graph)` static method returns a graph's ontology IRI (the
subject of `a owl:Ontology`) or `None` — useful when you have a bare `rdflib.Graph` and
need to know whether OntoEnv can key it.
