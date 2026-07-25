# Soundness-gated repair

This file is about **fixing** a model that validation found to be non-conforming:
proposing triples, gating them for soundness, and applying them with evidence. It is
the second half of the loop; the first half — *validate and read the failures* — is in
`validation.md`. Start there if you haven't run `model.validate(...)` yet.

Repair is only available on the **`pyshifty`** engine (the default), which returns an
`AlgebraicValidationContext` from `model.validate(...)`. The legacy `ValidationContext`
(`topquadrant`, or `pyshacl` — never use `pyshacl`, see `validation.md`) can parse
failures into `GraphDiff`s but cannot propose sound repairs — if you need repair, do not
pass another `shacl_engine`.

Source of truth: `buildingmotif.dataclasses.algebraic_validation` — find it on disk with
`python -c "import buildingmotif.dataclasses.algebraic_validation as m; print(m.__file__)"`.
Theory: `algebraic-repair.md` at the root of the NREL/BuildingMOTIF GitHub repo.

Two runnable notebooks (in `notebooks/` on GitHub) are the worked reference for
everything below — mirror their structure when demonstrating a workflow:

- **`Existing-model-repair-with-pyshifty.ipynb`** — the minimal end-to-end: broken model
  → validate → witnesses → gated proposals → apply → lift to templates.
- **`Existing-model-validation-with-pyshifty.ipynb`** — validates a *real* Medium Office
  model, then a **repair playground** with labelled experiments (A–G): browse ranked
  proposals, apply-and-`advance`, reuse-vs-mint, `as_templates`, `all_repair_templates`,
  deep recursive synthesis, and deletion-direction `sh:not`. Point users here to poke at
  a live graph.

All examples below are verified against an installed `buildingmotif` package (`pyshifty`
engine, self-contained hand-written shapes, a two-template repair library).

## Validate (with repair enabled)

`validation.md` covers the read-only validate call. The only difference here is you pass
`repair_libraries=` so the context can *propose* fixes, not just report them:

```python
ctx = model.validate(
    [shapes_lib.get_shape_collection()],   # omit/None -> the model's manifest
    repair_libraries=[repair_lib],         # templates that seed repair candidates
    error_on_missing_imports=False,        # see validation.md / ontology_imports.md
)
ctx.valid          # bool
ctx.report_string  # human-readable algebraic report
```

`repair_libraries` is optional. Without it, repair still works (recursive synthesis
needs no templates); with it, the engine can reuse existing nodes and mint richer,
domain-shaped instances. Pass the libraries whose vocabulary the model should speak.
`error_on_missing_imports` and the OntoEnv import-resolution behavior are documented in
`validation.md` and `ontology_imports.md` — the same guidance applies when repairing.

For a self-contained hand-written shape graph (no `owl:imports`) you need neither the
flag nor the extra libraries — see the import-resolution gotcha in `writing_shapes.md`.

**pyshifty repairs standard SHACL; SPARQL-based constraints validate but block.** It
fully supports `sh:qualifiedValueShape` / `sh:qualifiedMinCount` (verified — validates
*and* repairs them), so the pointlist idiom in `writing_shapes.md` works as-is. BuildingMOTIF's
custom constraint vocabulary (`constraint:exactCount` and friends from the `constraints`
library) *is* evaluated by pyshifty — it compiles to SPARQL-based SHACL — but its failures
come back as **blocked witnesses** (`w.is_blocked` True, no proposals), because an opaque
SPARQL/`Not` constraint can't be abduced over. If a manifest requirement uses a
`constraint:` component and you want it *repairable*, re-express that one requirement as
plain SHACL (a `sh:property` with `sh:minCount`/`sh:qualifiedValueShape`) — exactly what
the Medium Office validation notebook does with its AHU-setpoint requirement. See
`writing_shapes.md` for the details.

## Witnesses: one per failing (focus, statement)

`validation.md` covers the basic read — `.reason()`, `ctx.diffset`, `ctx.report_string`,
severity filtering. For repair you additionally care about `w.explain()` (the repair tree)
and `w.is_blocked` (whether repair is even possible):

```python
for w in ctx.witnesses:
    w.focus            # the failing node (None = graph-level failure)
    w.reason()         # "urn:bldg/vav1 CountLow on path brick:hasPoint (have 0, need 1)"
    w.is_blocked       # True -> no data repair possible in scope; do not fight it
    print(w.explain()) # the repair tree, indented
```

`w.explain()` prints the AND/OR/Repeat tree of typed holes — the *space* of edits that
would fix this failure. Read it when a proposal looks strange; it shows what the shape
actually demands:

```
Repeat [1..∞]:
  Edits:
    add <urn:bldg/vav1> <brick:hasPoint> ?0
    ?0 : instance of <brick:Temperature_Sensor>
```

To present the whole violation horizon grouped by focus node (the notebooks' way of
reading a real model's report), iterate `ctx.diffset`:

```python
print(ctx.report_string)
for focus, witnesses in ctx.diffset.items():
    print(focus)
    for w in witnesses:
        print("  - " + w.reason())
```

Other surfaces: `ctx.witnesses_by_focus()`, `ctx.diffset` (legacy-compatible),
`ctx.get_broken_entities()`, `ctx.get_reasons_with_severity(SH.Violation)`.

`w.is_blocked` means the failure involves opaque SPARQL, identity, or a coinductive
back-edge — no data edit can discharge it. Report it as "this constraint can't be fixed
by adding data; the shape or the constraint itself needs to change." Don't loop on it.

## Proposals: gated, ranked, and **not** all useful

```python
for p in w.proposals(limit=8):
    p.origin        # "synthesized" | "template:<name>" | "pyshifty-candidate" | "blocked"
    p.is_sound      # gate proved: introduces NO new violation
    p.is_progress   # gate proved: REMOVES this violation
    p.additions     # rdflib Graph of triples to add
    p.deletions     # rdflib Graph of triples to remove
    p.reused_nodes  # existing model nodes reused rather than minted
    p.num_additions
```

**The gotcha that will bite you: `is_sound` does not mean the repair works.**
`proposals()` returns only sound proposals, but soundness merely means "adds no *new*
violation". A proposal that binds the hole to some arbitrary existing node is sound and
useless. Real output for a VAV missing a temperature sensor:

```
[synthesized]                     sound=True progress=True  adds=2
[template:make-temperature-sensor] sound=True progress=True  adds=2
[pyshifty-candidate]              sound=True progress=False adds=1   <- sound, does nothing
[pyshifty-candidate]              sound=True progress=False adds=1   <- sound, does nothing
```

Always filter on **`is_progress`**:

```python
useful = [p for p in w.proposals() if p.is_progress]
```

Note the ranking already prefers progress, then minimal additions, then maximal reuse,
then template/synthesized provenance — so `proposals()[0]` is usually right. Filter
anyway; when nothing makes progress, that is a finding to report, not a proposal to apply.

### Reuse vs. mint — the distinction that matters

**Check `reused_nodes`, not `origin`.** Any origin can reuse: a `synthesized` proposal
is reuse-first and will bind an existing conforming node when one exists. Verified — a
model with a loose `Zone_Air_Temperature_Sensor` yields
`origin=synthesized adds=1 reused=['urn:bldg2/loose_sat']` as the **top** proposal,
because reuse needs only 1 addition where minting needs 2.

| condition | meaning | truth risk |
|---|---|---|
| `reused_nodes` **non-empty** | binds to nodes already in the model (reuse-first synthesis, or VF2 monomorphism against a template) | **low** — connects facts you already asserted |
| `reused_nodes` **empty**, `is_progress` true | **mints new individuals** that don't exist yet | **high** — asserts new things about the building |
| `pyshifty-candidate`, `is_progress` false | flat guess from the data graph | ignore |

`origin` tells you *which generator* produced it, useful for explaining provenance;
`reused_nodes` tells you whether you're about to **claim equipment exists**. Only the
latter decides whether you need evidence.

Reuse repairs mostly say "connect two things you already told me about." Mint repairs
say "this equipment exists." Only the second needs evidence or user confirmation, and it
is the common case. Treat minted URIs (`urn:buildingmotif:repair#n1`) as *placeholders
for real building entities* — never leave them in a model; they become template
parameters for the user to name.

## The repair loop (one witness per iteration)

Repair is the **body** of the iterative workflow (`SKILL.md`); validation is the top.
You drive it one witness at a time, re-validating after each applied fix — *not* batching
a pile of repairs and validating once at the end. Two reasons batching is wrong:
repairs interact (a node minted for one witness can discharge or break another —
`algebraic-repair.md` §8(iii), the generator treats witnesses independently), and fixing
one failure surfaces new ones (the equipment you just added has its own shapes, which now
run for the first time — the `model_correction` tutorial hits this exactly when the AHU's
supply-fan shape fails on the next pass).

Each iteration:

1. **Translate the gap into building language.** "VAV-1 needs a temperature sensor."
2. **Search for evidence** that the thing exists → `evidence.md`. A point list naming
   `VAV1_ZN_T` is evidence; nothing found is also information.
3. **Decide who decides:**
   - Reuse proposal + evidence agrees → apply, and say what you reused.
   - Mint proposal + evidence names the real point → apply, binding parameters to the
     *real* identifier, and cite the document.
   - No evidence, or several plausible readings → **ask the user** (below).
4. **Apply** one repair (below).
5. **Re-validate** — `ctx = model.validate(...)` again over the patched model. Read the
   *fresh* `ctx`: some old failures are gone, some new ones may have appeared, and a fix
   here may have discharged a witness you hadn't touched yet. That's the next iteration.
6. Repeat until `ctx.valid` (or until a failure turns out to be a wrong *shape*, not a
   wrong model — `writing_shapes.md`).

The pyshifty session API lets you re-validate the patched graph in place before
committing it to the model — `p.advance(ctx.session)` returns a new session over
`G ⊕ ΔG` whose `.witnesses()` is the next-iteration horizon (see "Applying a repair"
below). Use it to confirm a fix worked and to preview the next failures without a full
re-validate round trip.

### Asking the user

Use `AskUserQuestion` when evidence is missing or ambiguous. Give them the *building*
choice, not the SHACL choice, and put evidence in the descriptions:

> **VAV-1 has no temperature sensor. What's true of the building?**
> - *Zone sensor `VAV1_ZN_T` (recommended)* — found in `points.csv` line 42, unmapped
> - *No sensor exists* — the shape shouldn't require one for this VAV; relax the shape
> - *Sensor exists but isn't in any document* — I'll add it; you give me the point name

Never offer "mint `urn:buildingmotif:repair#n1`" as a user-facing option. The user knows
their building, not our IRIs.

## Applying a repair

**Preferred — lift into templates** so minted individuals become named parameters:

```python
templates = ctx.as_templates()          # best sound repair per failure, merged per focus
for t in templates:
    print(t.parameters)                 # e.g. {'repaired1'}
    model.add_graph(t.substitute({"repaired1": BLDG["VAV1_ZN_T"]}).to_graph())  # REAL names
```

This is the point of the template lift: `as_template()` keeps the focus and reused nodes
concrete and turns each minted individual into a parameter, so the user supplies the
real identifier. Bind parameters to identifiers from the evidence, not autogenerated ones
(`t.fill(BLDG)` invents names — fine for a smoke test, wrong for a real model).

Other entry points:

- `ctx.all_repair_templates(progress_only=True)` — *every* sound repair, grouped by
  focus, un-merged: the full menu of alternatives to show a user.
- `w.repair_templates()` — same, for one failure.
- `p.as_template(lib)` — lift one specific proposal you chose.

**Direct application** (no naming step — use for deletions or when nothing is minted):

```python
patched = p.apply()        # returns G ⊕ ΔG as a fresh graph; mutates nothing
session2 = p.advance()     # a new session over G ⊕ ΔG
len(session2.witnesses())  # confirm the violation is gone
```

Both default to the session the proposal came out of, so you do not pass one. Only supply an
explicit `p.apply(session)` if you are driving a session you built yourself — a proposal built
by hand, with no originating session, raises `ValueError` telling you to pass one.

`p.outcome.fixed` / `p.outcome.introduced` record exactly what the gate proved.

## Deletion repairs

Not every fix adds. A violated `sh:not` is discharged only by deletion, and the gate
treats it identically (`p.deletions` non-empty, `p.num_additions == 0`).

**Deletions need more care than additions, not less.** Deleting `vav2 brick:status
"decommissioned"` satisfies the shape and may erase a true fact. Always confirm a
deletion with the user, and consider that a deletion-only repair often means the *shape*
is wrong for this building.

## When no proposal makes progress

Don't force it. Diagnose in this order:

1. `w.explain()` — does the shape demand something unreasonable?
2. `w.is_blocked` — unrepairable in scope by construction.
3. **Search budgets.** Generation is heuristic and bounded by `RepairConfig`
   (`max_templates=25`, `max_branches=4`, `build_fuel=6`, `candidate_limit=16`);
   `Repeat` nodes instantiate at their *minimum* count only. A deep or wide requirement
   can exceed the budget:

   ```python
   from buildingmotif.dataclasses import RepairConfig
   ctx = model.validate([sc], repair_libraries=[lib],
                        repair_config=RepairConfig(build_fuel=10, max_templates=None))
   ```

   Reach for a focused `repair_libraries` before raising budgets. The engine now
   relevance-filters templates before matching, so `max_templates` rarely binds and
   `max_templates=None` is usually safe (`templates.md`); a small targeted library is
   still cheaper and clearer than a big one.
4. **The shape may be wrong.** If the requirement doesn't match the building, fix the
   shape (`writing_shapes.md`). This is a legitimate and common outcome — say so plainly.

Offered repairs are guaranteed sound but the search is deliberately **incomplete**
(`algebraic-repair.md` §7–8): "no proposal found" never means "no fix exists."
