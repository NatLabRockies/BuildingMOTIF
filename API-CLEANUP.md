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

---

## Proposed, not yet done

Roughly in priority order.

### 6. `Library.load()` is four constructors in a trenchcoat

`dataclasses/library.py:76-208`. Eight optional kwargs, dispatch on which one is non-`None`,
~130 lines of branching, `raise Exception("No library information provided")` if you guess
wrong. `db_id` / `ontology_graph` / `directory` / `name` are four genuinely different
operations sharing one entry point.

Proposal: `Library.from_ontology(...)`, `Library.from_directory(...)`, `Library.by_name(...)`,
`Library.by_id(...)`; keep `load()` as a thin deprecated shim that dispatches to them.
Non-breaking if the shim stays.

Two behavioral warts to fix in the same pass:

- `overwrite=False` **logs a warning and returns the existing library**
  (`library.py:310-315`, `431-436`). Silent-ish success with different semantics than
  `overwrite=True`. It should either be a documented no-op returning the existing library
  (fine — but then don't warn) or raise.
- Builtin-vs-filesystem resolution tries `resource_exists("buildingmotif.libraries", path)`
  *before* the filesystem (`library.py:130-138`, `188-194`), so a user's local `brick/`
  directory is silently shadowed by the packaged one. Should at minimum log at INFO which
  one won; better, make it explicit (`Library.from_builtin("brick/Brick.ttl")`).

### 7. `@property` methods with arguments that can never be passed

`dataclasses/template.py:183, 219, 239`. `all_parameters`, `dependency_parameters`, and
`parameter_counts` are decorated `@property` but declare
`error_on_missing_dependency: bool = True`. Nobody can ever supply it; the default is the
only reachable behavior. Plain bug.

Fix: drop the parameter, or drop `@property` and make them methods. Dropping the parameter
is non-breaking (nobody can be passing it).

### 8. Five overlapping notions of "parameters" on `Template`

`parameters` (local), `all_parameters` (local + direct deps, unrenamed), `dependency_parameters`
(deps only), `transitive_parameters` (recursive, *with* dependency renaming),
`parameter_counts` (histogram). The transitivity and renaming semantics differ subtly and
the names don't signal which is which.

Proposal: collapse to `parameters(transitive: bool = False, renamed: bool = True)` plus
`parameter_counts()`. Deprecate the rest. Breaking; do it with the #7 fix since it touches
the same properties.

### 9. `ValidationContext.as_templates()` raises on `sh:or` violations

`dataclasses/validation.py:118`. `OrShape` is the only `GraphDiff` subclass that doesn't
implement `resolve()`, so it inherits the base's `raise NotImplementedError`
(`validation.py:56`). Any model with an `sh:or` violation makes the legacy
`as_templates()` blow up rather than return the templates it *could* produce. The code
already admits this: *"this is still kind of broken...ideally we would actually interpret
the shapes inside the or clause"* (`validation.py:682`).

Minimum fix: `OrShape.resolve()` returns `[]` so a partial result still comes back. Better:
generate one template per branch of the `sh:or`. Non-breaking either way — it can only
turn a crash into a result.

### 10. Bare `Exception` in the dataclasses

`library.py:196` (`Directory {src} does not exist`), `library.py:208`
(`No library information provided`), `model.py:132` (`Neither id nor name provided`),
`template.py:624` (`Could not open active sheet in Workbook`). `database/errors.py`
already has proper classes. Callers can't catch these without `except Exception`.

Fix: `ValueError` for bad arguments, `FileNotFoundError` for the missing directory, and the
existing `*NotFound` classes where they apply. Mildly breaking for anyone catching
`Exception` — which still works.

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

### 13. `"default"` as a sentinel string

`compiled_model.py:42` takes `shacl_engine: str = "default"` and treats `"default"` and
falsy as "inherit from the singleton". `None` is the obvious sentinel and the rest of the
codebase already uses it (`Model.compile`, `Model.validate`). Also `Model.compile` passes
the literal `"default"` through at `model.py:291`.

Fix: `Optional[str] = None`. Keep accepting `"default"` for a release. Nearly non-breaking.

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

### 20. `utils.template_to_shape` is dead *and* broken

`utils.py:451`. No callers anywhere — package, tests, docs, or notebooks. It is also
broken for any template with required parameters: `_index_properties` (`utils.py:376`)
binds every parameter to *itself* (`{p: PARAM[p] ...}`), which is an identity
substitution, so the template is still incomplete afterwards. The old code then hit
`assert isinstance(templ_graph, Graph)` and raised `AssertionError`; after the item-5
migration it raises the clearer `IncompleteTemplateError`. Either way it cannot work.

Verified pre-existing: the original `evaluate()` returns a `Template` for that exact call,
so the assertion failed before this branch too.

The same function had a second latent bug on the line below:
`templ.dependency_for_parameter(maybe_param, error_on_missing_dependency)` passed two
arguments to a method that takes one — a `TypeError` on any template with dependency
parameters. Fixed in passing (the method never accepted the flag). It surfaced only
because the item-5 commit staged `utils.py` and `template.py` together, putting them in a
single mypy invocation for the first time; pre-commit's mypy 1.10 catches it, the venv's
1.9 does not. Two runtime bugs in one unreachable function is the argument for deleting
it.

Fix: either delete it, or make `_index_properties` operate on the parameterized body
directly instead of round-tripping through a substitution that does nothing. Deleting is
probably right — `ShapeCollection.infer_templates` is the direction that's actually used.

### 21. Smaller things

- `Model.graph` is a `cached_property` whose cache is invalidated by hand
  (`model.py:206`, `dict.pop("graph", None)`). Same pattern in `CompiledModel.add_graph`.
  Fragile; any new method that swaps the underlying graph must remember to do this.
- `Model.add_triples(*triples)` / `ShapeCollection.add_triples(*triples)` are thin wrappers
  over `graph.add` in a loop. Harmless, but they're a second way to do the same thing and
  neither tutorial uses them.
- `Library.load_from_libraries_yml` returns `None` and its docstring apologizes for it
  ("Does not return a Library!"). Should return `List[Library]`.
- `AlgebraicValidationContext.sparql_diagnostics` and `RepairWitness.witness` are annotated
  `"object"`, which types as "no attributes". They're pyshifty types; a `Protocol` or
  `TYPE_CHECKING` import would document them.
- **`[tool.mypy] files` only globs `buildingmotif/*.py`** (`pyproject.toml:120`) — one level,
  no recursion. So `uv run mypy` checks 11 files and silently skips `dataclasses/`,
  `building_motif/`, `database/`, `ingresses/`, `label_parsing/` — nearly the whole package.
  pre-commit passes staged filenames explicitly so it does check them, which is why this
  hasn't bitten; but the documented command in `CLAUDE.md` gives false confidence. Should be
  `["buildingmotif", "tests", "migrations"]`. Expect a backlog of findings when it's widened.
- `BuildingMOTIF.setup_logging` calls `logging.getLogger()` on the **root** logger, sets it
  to DEBUG, and unconditionally writes `BuildingMOTIF.log` into the current working
  directory. That's a library reconfiguring the host application's logging and littering
  the CWD. Should be opt-in.

---

## Related open issues

Existing tickets this backlog overlaps with: #375 / PR #385 (library.yaml spec and
metadata), #383 (`.yaml` file extension), #382 (empty template files), #339 (alternative
`Model` constructor — see #11), #345 (confusing MinCount text, which is the
`format_count_error` path at `validation.py:88`), #367 (exceptions in the documentation,
see #10).
