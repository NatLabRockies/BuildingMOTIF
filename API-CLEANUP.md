# API cleanup backlog

Working list of interface problems in BuildingMOTIF's consumer-facing API — the surface a
user touches when they *use* BuildingMOTIF on a model, rather than change BuildingMOTIF.
Written up on `gtf-api-cleanup`; items marked **done** landed on that branch, the rest are
proposals with enough detail to pick up cold.

Each entry says what's wrong, where, what to do, and whether the fix breaks callers.

---

## Done on this branch

(Numbering follows the original review order, so the "done" items are not contiguous.)

### 1. Tables are created for every backend — **done**

`BuildingMOTIF.__init__` only auto-created tables for in-memory SQLite, so the first
operation against a file-backed or Postgres database died with a bare
`OperationalError: no such table: shape_collection` from the driver. Every tutorial and
skill doc used in-memory, so nobody hit it until they went to persist something.

Now `setup_tables()` runs unconditionally (it is idempotent — `create_all` only adds
missing tables). `create_tables=False` opts out for schemas managed by the Alembic
migrations under `migrations/`. Non-breaking: explicit `setup_tables()` calls still work.

### 2. `BuildingMOTIF` is a context manager — **done**

BuildingMOTIF spans two stores with no shared transaction: triples are written through to
Oxigraph immediately, but the rows pointing at them are only durable once the SQL session
commits. That requirement was documented in one margin note in `model_creation.md` and one
line of the skill. Forgetting it leaves triples on disk that nothing references — exactly
the orphans `collect_graph_garbage()` exists to sweep up.

`with BuildingMOTIF(uri) as bm:` now commits on clean exit, rolls back on exception, closes
either way, and resets the singleton so the next constructor call builds a fresh instance
instead of returning the closed one. Purely additive.

### 3. `ValidationResult` protocol — **done**

`Model.validate()` returned `ValidationContext | AlgebraicValidationContext` depending on
which engine string was set on a singleton constructed somewhere else, forcing an
`isinstance` branch on every caller. The two classes were already written to expose the
same surface (`algebraic_validation.py` literally has a "ValidationContext-compatible
surface" section) — that contract is now explicit as `Protocol`s in
`buildingmotif/dataclasses/validation_result.py`:

- `ValidationResult` — the common read surface; both context classes satisfy it structurally.
- `Failure` — `.focus` + `.reason()`; satisfied by `GraphDiff` and `RepairWitness`.
- `Reason` — `.reason()`; also satisfied by `AlgebraicReason`.

`Model.validate` and `CompiledModel.validate` are annotated `-> ValidationResult`. Four
real divergences were fixed to make that true rather than aspirational:

- `ValidationContext` gained `conforms` (the algebraic side had it, the legacy side didn't).
- `ValidationContext.get_diffs_for_entity` now accepts `None` — the key model-level
  failures are actually stored under.
- `AlgebraicValidationContext.get_diffs_for_entity` returns a `set`, not a `list`, matching
  the legacy context.
- `get_broken_entities` was annotated `Set[URIRef]` but has always been able to return the
  string `"Model"`.

### 4. `ModelNotFound` on by-name lookup — **done**

`TableConnection.get_db_model_by_name` was the one lookup that didn't wrap
`NoResultFound` into the project's own error class (PR #360 added them and missed this
path), so `Model.load(name=...)` leaked a raw SQLAlchemy exception while
`Model.load(id=...)` raised `ModelNotFound`. Same fix applied to
`update_db_template_optional_args`.

### 5. `Template.evaluate()` returns `Template | Graph` — **done**

Which type you got depended on whether the bindings happened to cover every parameter — a
*runtime* property of the arguments. The package carried **ten `isinstance` checks** that
existed only to unpack that union, in `model_builder.py`, `template_matcher.py`,
`utils.py`, both ingress handlers, the API views, and the algebraic repair engine.

Replaced with two single-typed operations on `Template`:

- `substitute(bindings, warn_unused=False)` → **always** a `Template`. Composes, so partial
  binding is `t.substitute(a).substitute(b)`.
- `to_graph(namespaces=None, require_optional_args=False)` → **always** an
  `rdflib.Graph`; raises `IncompleteTemplateError` (a `ValueError`) rather than silently
  handing back a template.
- `is_complete` → every *required* parameter is bound; `missing_parameters` → the ones that
  are not.

All ten internal call sites migrated and every one of those `isinstance` checks deleted.
`evaluate()` is kept, unchanged in behavior, and now raises a `DeprecationWarning`; it is
implemented on top of `substitute`/`to_graph` so the two paths cannot drift.

The deprecation shim originally sketched here — have `evaluate()` return a `Template`
subclass that also proxies `Graph` — was **rejected on implementation**: satisfying
`isinstance(x, rdflib.Graph)` requires actually inheriting from `Graph`, and `Template` is
a `@dataclass` (generated `__eq__`) while `Graph` defines its own `__eq__`/`__hash__` by
identifier. The hybrid would have silently changed template equality semantics. Keeping
`evaluate()` behaviorally identical and adding the new API alongside gets the same
migration window with none of that risk.

**Known cost, deliberately accepted:** `substitute()` and `to_graph()` each copy the body,
so `t.substitute(b).to_graph()` copies twice where the old `evaluate()` copied once.
Measured on an inlined 34-triple, 17-parameter template: 2.74 ms per call, of which the
extra `in_memory_copy()` is 0.85 ms (~31%). That matters only on per-record ingress paths
(`ingresses/template.py`, `ingresses/brick.py`) at thousands of records. It was accepted
because making `to_graph()` mutate in place would break the property that it is repeatable
and leaves the template alone — a much worse trade for a method callers may reasonably call
twice. If profiling ever justifies it, the fix is a private `_finalize()` that mutates a
provably-fresh template, called only where the intermediate is a temporary.

One asymmetry worth knowing: `is_complete` is the *lenient* sense (unbound optionals are
fine, `to_graph()` drops them), while `to_graph()` takes `require_optional_args`. For the
strict sense, `not templ.parameters` says "nothing unbound at all" — see `_ready()` in
`ingresses/template.py`. Folding the flag into `is_complete` would mean making it a method;
it was left as a property because the lenient question is the common one.

### 7 + 8. `Template` parameter accessors — **done**

Two problems on the same five members, fixed together.

**#7, the phantom argument.** `all_parameters`, `dependency_parameters`, and
`parameter_counts` were `@property` but declared `error_on_missing_dependency: bool = True`.
Being properties, nobody could ever supply it, so the default was the only reachable
behavior — a plain bug.

**#8, five overlapping notions of "parameters".** `parameters` (local),
`all_parameters` (direct deps, raw names), `dependency_parameters` (direct deps only, raw),
`transitive_parameters` (whole chain, renamed as inlining would), `parameter_counts`
(whole chain, raw, as a histogram). Three independent axes — depth, renaming, whether to
include the template's own — encoded in names that signalled none of them.

`parameters` **stays exactly as it is**: a property, local-only, and by far the most-used
member (it is all over the package, the tests, and the new `substitute`/`to_graph` code).
Making it a method, as this entry originally proposed, would have been a large break for
the one accessor that was never confusing.

Everything else collapses into one method with the axes named:

```python
parameters_with_dependencies(
    transitive=True, renamed=True, include_self=True, error_on_missing_dependency=True
)
```

- `transitive=False, renamed=False` → the old `all_parameters`
- `transitive=False, renamed=False, include_self=False` → the old `dependency_parameters`
- defaults → the old `transitive_parameters`

Those three are kept as deprecated properties that delegate, with the phantom argument
gone. Tests pin each equivalence. `parameter_counts` keeps its own implementation (a
`Counter` is a genuinely different result, not a flag on a set-returning method) and just
loses the phantom argument.

Two things worth knowing:

- **`renamed=True` is exactly what inlining produces.** Verified as an invariant and
  asserted in tests: `t.parameters_with_dependencies() == t.inline_dependencies().parameters`.
  That is the useful meaning — "what will I have to bind after inlining" — answered without
  doing the inlining.
- **`include_self=False` is not `all - parameters`.** A dependency may legitimately use a
  parameter name the parent also uses (the `vav` fixture's dependency has its own `name`),
  so the set difference silently loses it. This is why `include_self` is a real axis rather
  than something callers subtract; there is a test for exactly this.

Also fixed two skill-doc snippets that wrote `t.all_parameters()` and
`t.parameter_counts()` **with parentheses** — both were properties, so those examples would
have raised `TypeError` on the returned set/Counter.

### 6. `Library.load()` is four constructors in a trenchcoat — **done**

Eight optional keywords, dispatch on which one you happened to pass, ~130 lines of
branching, and `raise Exception("No library information provided")` if you guessed wrong.
`db_id` / `ontology_graph` / `directory` / `name` are four genuinely different operations.

Replaced with named constructors:

- `Library.from_ontology(ontology, overwrite=, infer_templates=, run_shacl_inference=,
  fetch_imports=)` -- takes an `rdflib.Graph`, a path/URL string, **or a `pathlib.Path`**
  (new; `load()` only took `str`).
- `Library.from_directory(directory, ...)` -- also accepts `pathlib.Path`.
- `Library.by_name(name)` / `Library.by_id(db_id)` -- database lookups, no disk access.

`load()` remains, behavior unchanged, now raising a `DeprecationWarning` and dispatching to
the four. It keeps `db_id` as its first *positional* parameter because the package itself
called `Library.load(library_id)` positionally in three places. Its no-argument error is now
a `ValueError` naming the four options rather than a bare `Exception`.

The two string-path branches (str vs `Graph`) had duplicated the whole
load-imports-then-infer-templates tail; they are now one path, which is what made the
method shrink.

**The two behavioral warts, both fixed:**

- `overwrite=False` logged a *warning* and returned the existing library. Returning the
  existing library is what `overwrite=False` means, so it is now logged at INFO with
  accurate wording (the old message in `create()` also said "ovewrite"), and the docstrings
  state the no-op explicitly.
- Builtin-vs-filesystem shadowing is unchanged in *behavior* (builtins still win) but is no
  longer silent: `_resolve_builtin()` logs at INFO when a local path of the same name
  existed and was skipped, and tells you to pass an absolute path to get the local one.

**Two bugs fixed on the way:**

- `resource_exists()` was called with the raw `directory` argument, so passing an absolute
  path emitted `DeprecationWarning: Use of .. or absolute path in a resource path is not
  allowed and will raise exceptions in a future release` -- visible in the test suite today
  and slated to become an error. `_resolve_builtin()` now short-circuits absolute paths,
  which is also strictly more correct: an absolute path can never name a packaged resource.
- **`Library.from_ontology(...).name` returned an `rdflib.URIRef`, not a `str`**, while
  `by_name()`/`by_id()` returned `str`. Since `URIRef.__eq__` is type-strict,
  `Library.from_ontology(g).name == "urn:ex/ont"` was `False`. `Model.from_graph` has always
  normalized this (with a comment saying why); `Library.create` did not. Now it does. This
  also revived a dead guard: `_load_imported_ontology_libraries` skips the root ontology via
  `ontology_name == root_name`, comparing OntoEnv's plain-`str` closure names against that
  `URIRef` -- always `False`. The redundant work was caught by the `_library_exists` check
  immediately after, so this was a wasted query rather than a visible failure.

Non-breaking throughout: `load()` still works with every keyword combination it ever
accepted, including `overwrite=None` (the flags are passed through *uncoerced*, because
`None` was not equivalent to `False` -- it reached OntoEnv as `overwrite is not False` ->
`True` while still taking the `if not overwrite` branch).

**`load()` is now the by-id loader.** Not a shim: `Template.load(id)`,
`ShapeCollection.load(id)`, and `Dependency.load(id)` have always meant "load the row with
this id", and `Library.load` with eight keywords was the outlier. It now does that and
nothing else; `ontology_graph=` / `directory=` / `name=` still work but each warns and
names its replacement. This made the `by_id()` I had first added redundant, so it is gone.
Two new guards: `load()` with no arguments and `load(id, directory=...)` (previously the id
silently won and the other argument was ignored) both raise `ValueError`.

**The whole codebase moved to the new API**, not just the package: 134 `Library.load(kw=)`
call sites across tests, notebooks, `docs/`, and `.agents/`, plus every `Template.evaluate()`
and every deprecated parameter property. The only remaining uses of the deprecated paths are
the tests that exist to cover them.

### 9. `ValidationContext.as_templates()` raises on `sh:or` violations — **done**

`OrShape` was the only `GraphDiff` subclass without a `resolve()`, so it inherited the
base's `raise NotImplementedError`. Any model with an `sh:or` violation made
`as_templates()` blow up.

**Why it was never implemented — this is the interesting part.** It is not an omission.
Every template `resolve()` returns for a focus node is **joined into one** by
`merge_templates_for_focus` — a conjunction. So emitting one template per `sh:or` branch
would build a repair satisfying *every* alternative at once: for
`sh:or ( ElectricMeterShape GasMeterShape )` it would assert the meter is both, inventing
metadata that is false of the building. Picking one branch arbitrarily is no better, since
nothing in the shape says which is true here. **The legacy contract cannot express "choose
one"**, so there is no correct value for `resolve()` to return.

`resolve()` therefore returns `[]`, with the reasoning in its docstring. The win is not
"no crash" but that the *other* failures survive: one unresolvable diff used to discard
every repair in the report. There is a test for exactly that.

**The algebraic backend handles it properly, and structurally.** pyshifty models `sh:or` as
an `Any` node in the repair tree; `TemplateGuidedRepair._base_specs` enumerates those
branches as *separate base plans*, each independently soundness-gated, bounded by
`RepairConfig.max_branches`. Verified on a meter that must have either an electric or a gas
reading: the legacy path raises, while the algebraic path returns eight sound proposals,
some adding `ex:elec` and some `ex:gas`, and no single proposal conjoins the two. That menu
of alternatives is the right representation, and it is what the legacy API structurally
lacks.

**Second bug fixed here:** `OrShape.reason()` did `', '.join(self.shapes)`. `sh:or` branches
are written inline far more often than as named shapes, so they are blank nodes and the
message read `... needs to match one of: n785034978df14dae..., n785034978df14dae...`. It now
describes each branch by what it constrains (`[ns1:elec], [ns1:gas]`), which is the only
part of `OrShape` a user could act on.

### Bonus: `sh:or` is no longer ignored when decompiling shapes (issue #306)

Came out of #9. `get_template_parts_from_shape` carried a literal `# TODO: sh:or?`, so a
shape with a disjunction produced templates for its *other* requirements and silently
dropped the alternatives.

We deliberately did **not** add disjunction to templates. A template generates a fragment;
alternation is a property of the *requirement*, not of the generator, and making a template
disjunctive would force it to choose a branch at fill time -- pushing branch selection into
every caller and making `inline_dependencies` / `parameters` / `to_graph` branch-aware.

Instead a node shape's `sh:or` decompiles into **one template per branch**:

- `<shape>` -- the non-disjunctive requirements (unchanged; dependencies that name the shape
  keep resolving)
- `<shape>-alt1`, `-alt2`, ... -- those requirements plus exactly one branch

so filling any single alternative satisfies the shape, and no template conjoins the
branches. Ordering is the `sh:or` `rdf:List` declaration order -- the only ranking the shape
actually carries, and authors put the common case first. `get_shape_or_branches()` is the
accessor.

Blast radius is small: exactly **1 of Brick's 1444** class+nodeshape candidates carries a
node-level `sh:or` (`ref#BACnetReference`, 2 branches).

Still not handled: `sh:or` nested inside a *property* shape, which constrains one value's
type rather than the whole entity. The other half of the old TODO
(`# TODO: expand otypes to include sh:in, sh:or`) is that case.

**Rejected along the way:** expressing disjunction as several same-named templates in a
library. `tables.py` has `UniqueConstraint("name", "library_id")`, so it is forbidden at the
schema level and would need a migration. Beyond that it destroys a diagnostic (a duplicate
name today is a copy-paste error and nothing else checks library YAML for that), makes
dependencies -- which reference templates *by name* -- fork combinatorially through
inlining, and conflates identity with alternation. An explicit `oneOf:` key listing named
alternatives would be the better shape if this is ever wanted in YAML.

### 20. `utils.template_to_shape` was dead *and* broken — **done**

Deleted, along with the five helpers only it used (`_TemplateIndex`,
`_prep_shape_graph`, `_index_properties`, `_add_property_shape`,
`_add_qualified_property_shape`) -- 152 lines. Verified as a closed cluster first: nothing
outside `utils.py` referenced any of the six.

It had two runtime bugs, neither reachable. `_index_properties` bound every parameter to
*itself* (`{p: PARAM[p] ...}`), an identity substitution, so the template was never complete
and the following `assert isinstance(templ_graph, Graph)` failed; and it passed two
arguments to `dependency_for_parameter`, which takes one. Both pre-existing, both invisible
because the only caller was unreachable.

`ShapeCollection.infer_templates` is the direction that is actually used (shape -> template),
and it now handles `sh:or` too.

### 21. Smaller things — **done**

- **`[tool.mypy] files` only globbed one level** (`buildingmotif/*.py`), so `uv run mypy` --
  the command in `CLAUDE.md` -- checked 11 files and silently skipped `dataclasses/`,
  `database/`, `ingresses/`, `api/`, nearly the whole package. Widened to
  `["buildingmotif", "tests", "migrations"]`, which surfaced **26 real errors in 8 files**;
  all fixed (below). The config also disagreed with the pre-commit hook's flags, so a bare
  run reported 27 spurious `import-untyped` errors the hook suppresses --
  `ignore_missing_imports` and `disable_error_code = ["import-untyped"]` are now in the
  config, and `uv run mypy` finally enforces exactly what the hook and CI do. Clean across
  all 103 files.
- **`shape_builder/shape.py` had 10 implicit-Optional arguments** (`exactly: int = None`).
- **`DBTemplate.dependencies` was annotated `Mapped["DBTemplateDependency"]`** -- singular --
  for a one-to-many relationship, so iterating it was a type error. Annotation-only; no
  schema change, so no migration.
- **`Singleton.clean` was attached with `setattr` inside `__new__`**, invisible to a type
  checker, which is why call sites needed `# type: ignore[attr-defined]`. It is a real
  metaclass method now, and `instance` is declared, so both typecheck.
- **`sparql_diagnostics` and `RepairWitness.witness` were annotated `"object"`**, which types
  as having *no* attributes -- consumers, including our own tests, had to fight the checker.
  Now `SparqlDiagnostic` and `FocusWitness` Protocols describing the surface actually read.
  Runtime reads stay defensive `getattr`, since the concrete shape is pyshifty's to change.
- **`Library.load_from_libraries_yml` returned None** and its docstring apologized for it. It
  returns `List[Library]` in file order. `_resolve_library_definition` now returns the
  library it loaded, raises `FileNotFoundError` rather than bare `Exception` for a missing
  directory, and raises `ValueError` for an entry with none of `directory`/`ontology`/`git`
  (it used to fall off the end and return None). The file is also closed properly now.
- **`BuildingMOTIF.setup_logging` reconfigured the host application.** Worse than recorded:
  it added *two handlers to the root logger per construction, unbounded* -- measured 10 after
  5 constructions -- so a suite that builds and cleans the singleton hundreds of times
  formatted every record hundreds of times. It also forced the root logger to DEBUG and wrote
  a truncating `BuildingMOTIF.log` into the working directory every time (the copy at the
  repo root had reached 3.7 MB; it is gitignored, and nothing referenced it). Now: handlers
  it installed are replaced rather than stacked, the root level is only ever *lowered* as far
  as needed, and the log file is opt-in via `BuildingMOTIF(..., log_file=...)`.

**Left alone deliberately:** `Model.graph`'s hand-invalidated `cached_property` and the
`add_triples` wrappers. Both are noted in the original review as mild; neither is a defect,
and changing them is churn without a user-visible win.

### 10. Bare `Exception` in the dataclasses — **done**

There are now **no `raise Exception(...)` left in the package**. Each site got the type that
actually fits what went wrong, so a caller can catch the case they mean instead of
`except Exception`, which also swallows real bugs:

| where | was | now |
|---|---|---|
| `Model.load()` with neither id nor name | `Exception` | `ValueError` |
| `Library.load()` with no source (fixed in #6) | `Exception` | `ValueError` |
| `Library.from_directory()` on a missing directory (#6) | `Exception` | `FileNotFoundError` |
| `get_template_parts_from_shape`: no `sh:path`, or >1 object type / min count | `Exception` | `ValueError` |
| `TemplateIngress`: a record left parameters unbound | `Exception` | `ValueError` |
| `label_parsing` sequence: a parser returned nothing | `Exception` | `RuntimeError` |
| `generate_spreadsheet`: openpyxl gave no active sheet | `Exception` | `RuntimeError` |

The split is deliberate: `ValueError` where the *caller* passed something wrong (bad
arguments, a malformed shape, a record missing fields), `RuntimeError` where an invariant or
a third-party library misbehaved and there is nothing the caller could have passed
differently.

Non-breaking -- every one of these is still an `Exception` subclass, so existing
`except Exception` handlers are unaffected. There is a test asserting that.

Stale `:raises Exception:` docstrings were corrected too, including one in
`ontology_environment` that describes an error it *propagates* from ontoenv rather than
raises itself.

### 13. `"default"` as a sentinel string — **done**

`CompiledModel.__init__` took `shacl_engine: str = "default"` and treated both `"default"`
and any falsy value as "inherit from the singleton", while `Model.compile` and
`Model.validate` next door already used `Optional[str] = None` for the same idea --
so `Model.compile` had to translate, passing the literal `shacl_engine or "default"`.

Now `Optional[str] = None`, with None meaning inherit, and `Model.compile` forwards its own
argument unchanged. `"default"` is still accepted so nothing breaks; there is a test for
that.

---

## Proposed, not yet done

Roughly in priority order.

### 11. `Model.create(name=...)` where "name" is a namespace URI

`dataclasses/model.py:45`. The parameter is called `name`, is validated as a URI, becomes
the model's `owl:Ontology` subject, and is what every tutorial passes an `rdflib.Namespace`
to. Calling it `name` is why issue #339 asks for a constructor that already exists
(`Model.from_file`) — the family is fine, the naming isn't.

Proposal: rename to `uri` (keep `name` as a deprecated alias), and cross-reference
`from_graph` / `from_file` in the `create` docstring. Non-breaking with the alias.

### 12. `CompiledModel.validate_model_against_shapes` ignores the engine split

`dataclasses/compiled_model.py:71-125` constructs a `ValidationContext` unconditionally,
even under `pyshifty` where every other path returns an `AlgebraicValidationContext`. So
the same instance hands back different context types from two of its own methods.

Fix: route it through the same branch `validate()` uses. Now that `ValidationResult` exists
the return type can be `Dict[URIRef, ValidationResult]`. Breaking for anyone reaching for
`GraphDiff`-specific behavior on the result.

### 14. `shacl_engine` is a bare string everywhere

Valid values are `"pyshifty"`/`"shifty"`/`"pyshacl"`/`"topquadrant"`, normalized by
`normalize_shacl_engine`. A typo is only caught at `get_shacl_backend` time, which may be
deep into a compile.

Proposal: a `ShaclEngine` str-enum in `buildingmotif/shacl.py` that keeps accepting plain
strings. Non-breaking, gives editors autocomplete and validates at the constructor.

### 15. `RepairProposal.apply(session)` leaks the pyshifty session

`algebraic_validation.py:361-367`. `apply` and `advance` require the caller to reach into
`ctx.session` (the raw pyshifty `RepairSession`) and hand it back to the proposal that came
from that very context. The proposal already knows its witness, which knows its context.

Fix: default `session=None` and resolve it from `self`'s provenance; keep the explicit
parameter for callers driving their own session. Non-breaking.

### 16. `AlgebraicValidationContext.report` silently re-runs validation

`algebraic_validation.py:1265-1281`. Reading `.report` calls `shifty.validate()` a second
time to synthesize a W3C-shaped report graph. It's `cached_property`, so only once — but
a property that costs a full validation pass is surprising, especially in the loop where
you validate repeatedly.

Fix: leave the behavior, document the cost in the docstring, and mention `report_string`
(free — it comes off the algebra) as the cheap alternative.

### 17. `Model.update_manifest` doesn't update, it merges

`dataclasses/model.py:301`. It does `self.get_manifest().graph += manifest.graph`. There is
no way to *replace* a manifest through the public API.

Fix: rename to `add_to_manifest` (deprecate the old name) and add `replace_manifest`
built on `ShapeCollection.replace_graph`, which already exists.

### 18. `Template.add_dependency` hand-rolls overload dispatch

`dataclasses/template.py:146-160`. Two `@overload` stubs, then a `*args/**kwargs`
implementation that dispatches on `len(args) + len(kwargs)` and rebinds the name `args` to
mean two different things. A 2-vs-3 argument count decides which signature you got; get it
wrong and it silently does nothing (no `else`).

Fix: at minimum add an `else: raise TypeError(...)`. Better: `add_dependency(template, args)`
and `add_dependency_by_name(library, template, args)` as two real methods.

### 19. `TemplateBuilderContext` is not first-class

`buildingmotif/model_builder.py`. It exists to collapse the four-lines-per-entity model
building loop, but it isn't in any tutorial, isn't reachable from `Model`, and compiles to
a detached graph the caller must `add_graph` themselves.

Deferred deliberately — noted here so it isn't rediscovered as new.

---

## Related open issues

Existing tickets this backlog overlaps with: #375 / PR #385 (library.yaml spec and
metadata), #383 (`.yaml` file extension), #382 (empty template files), #339 (alternative
`Model` constructor — see #11), #345 (confusing MinCount text, which is the
`format_count_error` path at `validation.py:88`), #367 (exceptions in the documentation,
see #10).
