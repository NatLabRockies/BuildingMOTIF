# Storage Architecture

This page explains how BuildingMOTIF persists data so that future developers
understand the backend. It covers the two stores BuildingMOTIF uses, how they
are linked, the consistency model, copy-on-write graph replacement, and
garbage collection.

## Two stores, one system

BuildingMOTIF keeps its data in **two different stores**, each chosen for what
it is good at:

| Store | Backed by | Holds |
| --- | --- | --- |
| **Relational store** | SQLAlchemy over a SQL database (SQLite by default) | *Metadata*: libraries, shape collections, models, templates, template dependencies, names, descriptions |
| **Graph store** | [Oxigraph](https://github.com/oxigraph/oxigraph) (via the `rdflib-oxigraph` plugin) | *RDF triples*: the actual contents of every model, shape collection, and template body |

The relational store is managed by
`buildingmotif.database.table_connection.TableConnection` and the
graph store by
`buildingmotif.database.graph_connection.GraphConnection`. The
`buildingmotif.building_motif.building_motif.BuildingMOTIF` object
owns both and is the only place they are coordinated.

### Why two stores?

Earlier versions of BuildingMOTIF stored triples *inside* the SQL database
(via `rdflib-sqlalchemy`). That gave single-database transactionality but was
slow, because a relational database is a poor SPARQL engine: every query is
translated into joins and there are no native triple indexes.

Oxigraph is a purpose-built RDF store with proper indexes, so SPARQL queries
and graph operations are dramatically faster. The cost of that speed is that
triples now live in a **separate** store from the metadata, and the two must
be kept consistent without a shared transaction. The rest of this page is
about how we do that correctly.

```{note}
Run SPARQL through the Oxigraph-backed graph (`graph.query(...)` /
`store.query(...)`) rather than iterating triples in Python. Iterate triples
only when you genuinely need to walk the whole graph. rdflib's `Graph.query`
already dispatches to Oxigraph's native SPARQL engine for store-backed graphs,
so no special handling is needed.
```

## Loading files: native vs. rdflib

Parsing a large ontology with `Graph.parse` adds triples one at a time through
rdflib's Python layer, which is slow. `GraphConnection.load_file_into_graph`
instead uses Oxigraph's native (Rust) loader to parse a file directly into a
named graph — roughly an order of magnitude faster on large files (e.g. Brick).
The library directory loader uses this path.

Native loading is for **trusted on-disk RDF only**: the native parser requires
syntactically valid IRIs, so it must not be used for in-memory graphs that may
carry generated template parameters with invalid IRIs (those still go through
the wrapper). It also does not populate rdflib's namespace manager, so callers
re-bind the standard prefixes (`bind_prefixes`) afterward. If the native parser
cannot handle a file, the method transparently falls back to `Graph.parse`, so
behavior is never worse than before.

## The `graph_id` pointer

Each metadata row that owns RDF content stores a **`graph_id`** (a string).
That `graph_id` is the identifier of the named graph in Oxigraph that holds
the row's triples:

- `DBModel.graph_id` → the model's triples
- `DBShapeCollection.graph_id` → the shape collection's triples (a model's
  manifest is stored as one, though it holds only `owl:imports` naming the
  libraries the model must satisfy — see `explanations/manifests.md`)
- `DBTemplate.body_id` → the template body's triples

These identifiers are **UUIDs** (`str(uuid.uuid4())`), generated when the row
is created. They are *not* the model name or ontology IRI — those live as
triples *inside* the graph. The `graph_id` is an opaque pointer, which is the
key property that makes copy-on-write (below) possible.

```
   Relational store (SQLAlchemy)              Graph store (Oxigraph)
  ┌────────────────────────────┐            ┌───────────────────────────┐
  │ DBModel                    │            │ named graph <uuid-A>      │
  │   id = 1                   │            │   :model a owl:Ontology . │
  │   name = "urn:my/model"    │  graph_id  │   :ahu1 a brick:AHU .     │
  │   graph_id = "uuid-A" ─────┼───────────▶│   ...                     │
  └────────────────────────────┘            └───────────────────────────┘
```

### OntoEnv graphs share the store

[OntoEnv](https://github.com/gtfierro/ontoenv) also stores its resolved
ontology graphs in the *same* Oxigraph store, through
`buildingmotif.ontology_environment.BuildingMOTIFGraphStore`. Those
graphs are keyed by their **ontology IRI** (e.g.
`https://brickschema.org/schema/Brick`), not by a UUID, and no SQL row points
at them — OntoEnv's own registry is their source of truth. This distinction
(UUID-keyed BuildingMOTIF graphs vs. IRI-keyed OntoEnv graphs) matters for
garbage collection.

## Consistency model

There is **no transaction that spans both stores**. The `rdflib-oxigraph`
plugin's `commit()`/`rollback()` are no-ops; Oxigraph only guarantees that each
*individual* operation (one `extend`, one `update`) is atomic. So we cannot
"commit both stores together."

Instead, BuildingMOTIF arranges writes so that the only possible failure mode
is **harmless**, not corrupting:

1. **Write triples to the graph store first.** Each write goes to a *new*,
   not-yet-referenced named graph (see copy-on-write).
2. **Commit the SQL pointer last.** The SQL row is what makes a graph
   "official." Flipping the `graph_id` happens inside the SQLAlchemy session
   and commits with it.

Because the pointer flip is the last step, a crash or error can only leave an
**orphan graph** (triples that no row references) — never a **dangling
pointer** (a row that references missing or half-written triples). Orphans are
invisible to users and are reclaimed by garbage collection. Dangling pointers
would be user-visible corruption, and this ordering makes them impossible.

## Copy-on-write graph replacement

Replacing the contents of a model or shape collection is the operation most
prone to corruption, because the naive approach is two operations:

```python
# DON'T: if the second step fails, the first already destroyed the data
shape_col.graph.remove((None, None, None))   # clear
shape_col.add_graph(new_content)             # refill  ← may fail here
```

Oxigraph's per-operation atomicity does not help across these two steps. So
BuildingMOTIF never mutates a graph in place to replace it. Instead it uses
**copy-on-write (COW)** via `Model.replace_graph` /
`ShapeCollection.replace_graph`, backed by
`buildingmotif.database.graph_connection.GraphConnection.replace_graph_contents`:

1. Write the new contents into a **fresh** `graph_id` (a single atomic graph
   store write). The old graph is untouched.
2. **Flip the SQL pointer** (`update_db_model_graph_id` /
   `update_db_shape_collection_graph_id`) to the new `graph_id`.
3. Rebind the in-memory dataclass to the new graph view.

The old graph becomes an orphan, reclaimed later by garbage collection.

### Why COW composes cleanly with rollback

Because the pointer flip is just a column update inside the SQLAlchemy session,
it participates in the normal SQL transaction. This gives a clean correctness
story for free:

- If anything fails before the flip, the old graph is intact and the new graph
  is an orphan.
- If the caller calls `session.rollback()` after a flip, the `graph_id` reverts
  to the old value. The old graph still holds the original contents, and the
  newly written graph becomes an orphan.

Either way the old data survives and only orphans accumulate. This is why the
replacement call sites (e.g. `Library.load`'s ontology load, the
`PUT /models/<id>/graph` API endpoint) need only a plain `session.rollback()`
on error — no manual graph cleanup.

```{note}
COW is also the groundwork for **model versioning**: because each replacement
writes a new immutable graph and the row just points at the current one,
retaining old `graph_id`s (instead of garbage-collecting them) would yield a
version history. That retention layer is not implemented yet.
```

## Garbage collection

COW replacement and row deletion both leave orphaned named graphs behind.
`buildingmotif.building_motif.building_motif.BuildingMOTIF.collect_graph_garbage`
reclaims them:

1. `TableConnection.get_all_graph_ids` collects the **live set** — every
   `graph_id`/`body_id` referenced by any row.
2. `GraphConnection.collect_garbage` deletes every named graph whose
   identifier is a **UUID** and is **not** in the live set.

The UUID filter is the critical safety guard: only BuildingMOTIF's own graphs
(models, shape collections, template bodies) use UUID identifiers, so
**OntoEnv's IRI-keyed ontology graphs are excluded by construction** and never
deleted, even though they share the store and have no SQL row.

GC runs automatically (best-effort) in `BuildingMOTIF.close()`, and can be
invoked manually whenever no write transaction is in flight. It is safe to run
repeatedly.

```{warning}
Do not run garbage collection while a write transaction is mid-flight. It reads
the committed/flushed live set from SQL; a graph that has been written but whose
referencing row has not yet been flushed could be incorrectly reclaimed.
`close()` and idle points are safe.
```

## Where this lives in the code

- `buildingmotif.database.graph_connection` — `GraphConnection`,
  `replace_graph_contents`, `collect_garbage`, the UUID/IRI helpers, and the
  `BuildingMOTIFOxigraphGraph` wrapper.
- `buildingmotif.database.table_connection` — `TableConnection`,
  the `graph_id` pointer updates, and `get_all_graph_ids`.
- `buildingmotif.building_motif.building_motif` — wires the two stores
  together and exposes `collect_graph_garbage`.
- `buildingmotif/dataclasses/model.py`,
  `buildingmotif/dataclasses/shape_collection.py` — the `replace_graph` methods.

```{note}
The `graph_id`/`body_id` columns already exist in the schema, so the
copy-on-write and GC work added **no new SQL columns** and required no Alembic
migration. A future versioning layer that retains historical graphs would need
a schema change (and a migration).
```
