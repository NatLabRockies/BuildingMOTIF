# Branches merged into `gtf-buildingmotif`

`gtf-buildingmotif` is an **integration branch**: a single place to run the latest work while
the individual features wait on PR review into `develop`. Nothing is developed here directly.

The workflow is:

1. Develop a feature on its own branch, **cut from `develop`** — never from another feature
   branch.
2. Open a PR from that branch into `develop`.
3. Also merge that branch into `gtf-buildingmotif` (`--no-ff`) so the combined state is usable
   before the PRs land.

Keeping every feature branch rooted at `develop` is what makes each PR independently
reviewable and mergeable in any order. **The four original feature branches — `gtf-ontoenv`,
`gtf-new-pyshifty`, `gtf-uv`, `gtf-buildingmotif-skill` — are all cut from `develop` at
`64ae7a0c`**, none based on another.

Conflicts between features are resolved **on this branch only**; the feature branches stay
clean so their PRs stay small.

**Exception: the two API branches are cut from `gtf-buildingmotif`, not `develop`** —
deliberately, at the maintainer's request, so they land after the four above:

- `gtf-api-cleanup`, cut at `64ae7a0c`-plus-merges, merged as #17.
- `gtf-api-ergonomics`, cut from `gtf-buildingmotif` at `7c89302e` (i.e. **after**
  `gtf-api-cleanup` merged), merged as #18. It uses APIs that exist only on `gtf-api-cleanup`
  (`ShapeCollection.replace_graph`, the `ValidationResult`/diagnostic protocols), so the two are
  **stacked in effect even though neither is branched from the other**.

Consequences to plan for: neither is independently mergeable into `develop` until #396/#398/#399
land, and when they are rebuilt onto `develop` they must be rebuilt **in order**
(`gtf-api-cleanup` first) or landed as a single PR. See their branch notes below.

## Merge order

Merged in this order, oldest first. Order matters only for reading the history — the conflicts
all surfaced in the `gtf-new-pyshifty` merge.

| # | Merge commit | Branch | Branch tip merged | Commits | PR |
|---|---|---|---|---|---|
| 1 | `5caefe0e` | `gtf-buildingmotif-skill` | `0f5dc4d2` | 1 | not opened |
| 2 | `266aabc5` | `gtf-ontoenv` | `01280864` | 12 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 3 | `63d8f7cf` | `gtf-new-pyshifty` | `ec3646e4` | 4 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 4 | `188c54b6` | `gtf-new-pyshifty` (updated tip) | `4b15e064` | 6 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 5 | `0198b66a` | `gtf-new-pyshifty` (source-triples fix) | `3e4d5cda` | 7 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 6 | `621d1f7c` | `gtf-uv` | `ad254f00` | 1 | [#398](https://github.com/NatLabRockies/BuildingMOTIF/pull/398) open |
| 7 | `37f59ded` | `gtf-new-pyshifty` (required-pyshifty + repair hardening) | `52d75e6c` | 8 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 8 | `551cfd30` | `gtf-ontoenv` (directory-load registration fix) | `6aa8377b` | 1 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 9 | `4fe44201` | `gtf-new-pyshifty` (origin reconciliation) | `887a70f1` | 12 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 10 | `91f210b8` | `gtf-new-pyshifty` (0.2.x pin relaxation) | `049a619f` | 2 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 11 | `1f87e952` | `gtf-buildingmotif-skill` (install/packaging docs) | `133c6f10` | 1 | not opened |
| 12 | `198d6861` | `gtf-new-pyshifty` (bump pyshifty to 0.2.7) | `94936937` | 1 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 13 | `408aceb3` | `gtf-buildingmotif-skill` (never recommend pyshacl) | `5ddf29c1` | 1 | not opened |
| 14 | `c3e0cd92` | `gtf-buildingmotif-skill` (223P vocab, prefer non-deprecated) | `ae23ad19` | 1 | not opened |
| 15 | `77be64e3` | `gtf-new-pyshifty` (prefix-loss fix + SPARQL diagnostic reporting) | `6d7bfad2` | 1 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 16 | `aaf2e2a0` | `gtf-buildingmotif-skill` (parameter-property parens fix) | `73e68144` | 1 | not opened |
| 17 | `7c89302e` | `gtf-api-cleanup` (consumer API cleanup) | `34967435` | 25 | not opened |
| 18 | `bf7584b8` | `gtf-api-ergonomics` (Model naming, manifests, repair sessions) | `8cef24e6` | 3 | not opened |
| 19 | `dda5084f` | `gtf-api-ergonomics` (agent-skill API refresh) | `8ea7ce7c` | 1 | not opened |
| 20 | `a66bf370` | `gtf-api-ergonomics` (second stale `advance` in the skill) | `f70798a6` | 1 | not opened |
| 21 | `9eebfc13` | `gtf-api-ergonomics` (repair notebook `advance()`) | `243e9d03` | 1 | not opened |
| 22 | `3c856ff7` | `gtf-ontoenv` (ontoenv 0.6.0a8 + closure_names) | `0004678a` | 1 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 23 | `ba01c56d` | `gtf-ontoenv` (drop deprecated `init_from_store`) | `bc0e6d65` | 1 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 24 | `cf56b615` | `gtf-ontoenv` (ontoenv 0.6.0a9 + container protocol) | `390c0c23` | 1 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 25 | `3935bedc` | `gtf-ontoenv` (recover from stale catalog marker) | `d0084dea` | 1 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 26 | `40c5116d` | `gtf-ontoenv` (ontoenv 0.6.0 stable) | `c3185156` | 1 | [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) open |
| 27 | `0d65a812` | `gtf-test-isolation` (singleton leak under `-n auto`) | `c02d82f3` | 1 | not opened |
| 28 | `a4a256fd` | `gtf-matcher-perf` (hoist loop-invariant graph conversions) | `1b5e0f6e` | 1 | not opened |
| 29 | `9c32301a` | `gtf-new-pyshifty` (notebook repair cap, repair_libraries doc) | `3f011108` | 2 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 30 | `f637e240` | `origin/gtf-buildingmotif` (catch up: drop swept files) | `f809f25c` | 2 | n/a |
| 31 | `01f7f689` | `origin/gtf-buildingmotif` (catch up: WaTr skill reference) | `e510b024` | 2 | n/a |
| 32-36 | — | **not recorded** — see "Gap in the merge table" below | — | — | — |
| 37 | `f56ea637` | `gtf-new-pyshifty` (pyshifty 0.4 interface) | `770073ab` | 2 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |
| 38 | `738bca85` | `gtf-new-pyshifty` (data-as-shapes prefix fix) | `bd3e48f5` | 1 | [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) open |

Merges 4 and 5 were made while the source-triples fix briefly lived on its own branch
(`gtf-compile-source-triples`); that branch has since been folded into `gtf-new-pyshifty` by
fast-forward and deleted. The merge commit message still names it — the commits are the same
either way. **All four feature branches are rooted at `develop`; none is stacked.**

One commit remains only on this branch: `a60bf48f`. Its content is duplicated by `b757c342`
on `gtf-new-pyshifty`, so nothing is lost if this branch is rebuilt.

**As of 2026-07-25 every feature-branch tip is an ancestor of `gtf-buildingmotif`** — verified
with `git merge-base --is-ancestor` for all six. There is nothing outstanding to merge forward;
`gtf-buildingmotif` is the union of every branch above at its current tip. Re-check this before
assuming it still holds, since any new commit on a feature branch breaks it silently.

## History rewrite: removed Claude/Anthropic co-author trailers (2026-07-23)

Every commit below that was authored with Claude Code carried a `Co-Authored-By: Claude ...
<noreply@anthropic.com>` trailer. These were stripped — message text only, no tree changes —
from `gtf-buildingmotif-skill`, `gtf-uv`, `gtf-new-pyshifty`, and the commits/merges that exist
only on `gtf-buildingmotif`. `gtf-ontoenv` never had any such trailers and was left untouched
(it also carries the open PR #396, so it wasn't a candidate for rewriting regardless).

Every hash in this document is post-rewrite. Old → new mapping, for anyone holding a reference
(PR comments, local notes, other clones) to a pre-rewrite hash:

| Old hash | New hash | Commit |
|---|---|---|
| `283f692a` | `5caefe0e` | Merge `gtf-buildingmotif-skill` |
| `0843b4f9` | `0f5dc4d2` | docs: add BuildingMOTIF agent skill |
| `40b98c20` | `266aabc5` | Merge `gtf-ontoenv` |
| `427a0c60` | `63d8f7cf` | Merge `gtf-new-pyshifty` (early) |
| `f1896988` | `a60bf48f` | fix: keep normalize_shacl_engine re-exported from utils |
| `4db867aa` | `188c54b6` | Merge updated `gtf-new-pyshifty` |
| `5024714c` | `4b15e064` | fix: normalize shacl_engine before assigning in the constructor |
| `a0597644` | `b757c342` | fix: mark normalize_shacl_engine as a deliberate re-export |
| `7d8e6be1` | `0198b66a` | Merge `gtf-compile-source-triples` |
| `be093917` | `3e4d5cda` | fix: preserve source triples through backend compilation |
| `45e980e4` | `621d1f7c` | Merge `gtf-uv` |
| `9f5caa96` | `ad254f00` | build: replace poetry with uv |
| `4ddce6e6` | `37f59ded` | Merge `gtf-new-pyshifty` (required-pyshifty) |
| `c58861d2` | `52d75e6c` | fix: make pyshifty required and harden the algebraic repair layer |

`ec3646e4` and `01280864` are unchanged (not reworded). Verified at each step that the new
commit's tree is byte-identical to the old one (`git diff <old> <new>` empty throughout), so
this is purely a message edit — no working-tree drift anywhere in the chain.

`gtf-new-pyshifty` was rewritten locally only at this point, since `origin/gtf-new-pyshifty` had
diverged onto a different set of follow-up commits that didn't exist on the local branch;
force-pushing the rewrite here would have destroyed those, so it was **not pushed** yet. See
"Reconciling `gtf-new-pyshifty` with origin" below for how that divergence was resolved.
`gtf-uv` and `gtf-buildingmotif-skill` have no `origin/` counterpart, so nothing to reconcile
there. `gtf-buildingmotif` itself had never been pushed as of this rewrite — that changed
2026-07-24, when it and `gtf-new-pyshifty` were pushed as fast-forwards after merge #12 (see
the Merge order table above); `origin/gtf-buildingmotif` now exists and tracks this branch.

Merge #8 (`551cfd30`, tip `6aa8377b`) was made by a separate concurrent session directly on top
of the rewritten `gtf-buildingmotif` tip (`37f59ded`) — its own commit has no Claude trailer, so
it needed no rewriting.

## Second history rewrite: same trailers, reintroduced by merge #18 (2026-07-25)

The 2026-07-23 rewrite above did not stick as a *policy*. The three commits written on
`gtf-api-ergonomics` two days later each carried a fresh
`Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>` trailer, and they were pushed that way
before anyone looked. Stripped again — message text only — and force-pushed.

| Old hash | New hash | Commit |
|---|---|---|
| `421ef6f4` | `f2d87820` | feat: RepairProposal remembers the session it came from |
| `5e444d40` | `9ff3d38e` | feat: Model.create takes uri, and manifests can be added or replaced |
| `ba3e219c` | `8cef24e6` | docs: record the outcomes of API-CLEANUP items 11 and 14-17 |
| `37f01d55` | `bf7584b8` | Merge `gtf-api-ergonomics` into `gtf-buildingmotif` (#18) |

The merge commit had no trailer of its own; it was rebuilt only because its parent changed.
`gtf-buildingmotif` was reset to `7c89302e` and re-merged, so merge #18 exists twice in the
reflog. Tree verified byte-identical before and after on both branches (`b0133ab3` throughout),
same check as the first rewrite. Force-pushed with `--force-with-lease`; both branches had been
pushed less than an hour earlier and nobody else had touched them.

**A full audit of all seven branches found nothing else** — no trailers on `gtf-api-cleanup`,
`gtf-buildingmotif-skill`, `gtf-ontoenv`, `gtf-new-pyshifty` or `gtf-uv`, and no attribution in
any *tracked file* added by any of them. Two things a naive `grep -i claude` flags that are
**not** attribution and were deliberately left alone:

- `gtf-api-cleanup`'s mypy commit says "the command CLAUDE.md documents" — a reference to a
  file in the repo, not a credit.
- `gtf-buildingmotif-skill`'s packaging commit says the docs "note Claude Code vs.
  Codex/other-agent usage" — describing what the added documentation is *about*. The agent-skill
  guide names agent tools because that is its subject; rewriting the commit message would not
  change the file, and the file is correct.

Local backup tags `backup/pre-trailer-strip-ergonomics` and `backup/pre-trailer-strip-buildingmotif`
point at the pre-rewrite tips. They are local-only and safe to delete once nobody needs the old
hashes.

**Anything committed here from now on must omit the trailer** — it is not stripped
automatically, and the first rewrite's mapping table above shows how noisy it is to fix after
the fact.

### Enforced by a local `commit-msg` hook (not committed)

`.git/hooks/commit-msg` rejects `Co-Authored-By:` lines naming Claude/Anthropic, any
`noreply@anthropic.com`, and `Generated with ... Claude` footers. It lives in the **common** git
dir, so it covers all five worktrees (`bmotif-gtf`, `BuildingMOTIF`, `bmotif-pyshifty`,
`bmotif-uv`, `bmotif-tmp`), not just this one.

**It is deliberately local and uncommitted** — `.git/hooks` is not tracked, so it will not
follow a clone, a fresh worktree, or anyone else's checkout. If this repo is re-cloned the hook
must be recreated by hand; nothing in a PR will remind you.

It ignores `#` comment lines and does not fire on prose mentions, so the two legitimate cases
above (`CLAUDE.md documents ...`, `notes Claude Code vs. Codex ...`) still commit fine — that
was checked against both message shapes, plus the trailer form, the emoji-footer form, and a
clean message. `--no-verify` bypasses it.

## Branch notes

### `gtf-buildingmotif-skill` — merged clean

Adds `.agents/skills/buildingmotif/` (`SKILL.md` + 10 reference files). Recovered from
`neutra:~/src/bmotif-unified/.agents/skills/buildingmotif/`, where it was written on
2026-07-17; that copy still exists and is byte-identical. Docs only, no code.

#### Follow-up (merge #11, `1f87e952`, tip `133c6f10`) — install/packaging docs, agent-skill guide

`SKILL.md`'s "installed package, not a checkout" line was being misread as applying to the
skill's own markdown files, not just the `buildingmotif` package it teaches an agent to
`import` — clarified in place. Adds a verified sparse/blobless `git clone` (and a `curl |
tar` fallback for environments without `git`) as the way to fetch just
`.agents/skills/buildingmotif/` without a full repository clone, since the skill isn't
published anywhere else yet; flags packaging it as its own release asset (mirroring Brick's
`nightly` release asset) as the un-done long-term fix. Notes Claude Code vs. Codex/other-agent
usage. Adds `docs/guides/agent-skill.md` (structure, install, two example prompts, why the
validate/repair loop suits an agentic workflow) and wires it into `docs/_toc.yml`. Also
swapped `NREL/BuildingMOTIF` → `NatLabRockies/BuildingMOTIF` in every URL this commit touched,
after confirming via `gh api repos/NREL/BuildingMOTIF` that the org was renamed (old links
still redirect, but the new links don't depend on that).

Committed on `gtf-buildingmotif-skill` first (via a throwaway sibling worktree, so the commit
is scoped to that branch's own base — `docs/_toc.yml` on this branch is missing two lines
(`tutorials/pyshifty_validation_repair.md`, `explanations/storage-architecture.md`) that only
exist on `gtf-buildingmotif` via later merges, and the skill-branch commit deliberately does
**not** carry those, to keep the eventual PR clean), then merged into `gtf-buildingmotif`
(`--no-ff`, `ort` strategy). `docs/_toc.yml` auto-merged with no conflict — the three-way
merge combined this branch's new `guides/agent-skill.md` line with the two lines
`gtf-buildingmotif` already had from other branches, correctly, with no manual resolution
needed.

#### Merge #16 (`aaf2e2a0`, tip `73e68144`) — parameter properties were being called like methods

Three skill snippets wrote `t.all_parameters()` and `t.parameter_counts()` with parentheses.
Both are `@property`, so those examples raise `TypeError` (calling the returned `set`/`Counter`)
rather than doing what they claim — an agent following the reference verbatim hits the error,
not the data. Found while doing the `Template` parameter-accessor cleanup on
`gtf-api-cleanup`; committed **here instead of there** because it is a real bug in the skill
docs against `develop`'s API, independent of that branch's changes.

Docs only, no code. Merged clean via the usual sibling-worktree-then-merge process.

**Expect a conflict on these exact lines when `gtf-api-cleanup` merges.** That branch replaces
them with `parameters_with_dependencies(...)` (it deprecates `all_parameters`), so the
resolution is to take `gtf-api-cleanup`'s version — it supersedes this fix. The fix still earns
its place here because the skill branch's own PR lands on `develop`, where `all_parameters` is
current API and the parens bug is live.

### `gtf-ontoenv` — merged clean

Replaces the `rdflib-sqlalchemy` triple store with Oxigraph, routes `owl:imports` through
OntoEnv, adds copy-on-write graph replacement and orphan GC. Raises the Python floor to 3.11
and adds `ontoenv 0.6.0-a5` + `oxrdflib`. See `docs/explanations/storage-architecture.md`.

PR [#396](https://github.com/NatLabRockies/BuildingMOTIF/pull/396) → `develop`, open since
2026-06-28.

#### Follow-up fix (merge #8, `551cfd30`, tip `6aa8377b`) — directory-loaded libraries never registered with OntoEnv

`Library.load(ontology_graph=...)` (single file) registers the ontology with OntoEnv via
`bm.ontology_environment.add(...)`, which is what makes its `owl:imports` resolvable later.
`Library.load(directory=...)` never did this: `_load_shapes_from_directory`
(`buildingmotif/dataclasses/library.py`) loaded every file in the directory straight into the
shape collection's graph via Oxigraph's native loader and skipped OntoEnv registration
entirely. Surfaced as: loading `libraries/ashrae/guideline36/` (a directory), then validating
against anything with `owl:imports <urn:ashrae/g36>` (e.g.
`notebooks/mediumOffice-validation/constraints/mediumOffice_constraints.ttl`) — OntoEnv didn't
know `urn:ashrae/g36` existed, fell back to treating it as a relative file path, and failed
with "No such file or directory".

Fix: register each file in the directory with `bm.ontology_environment.add(filename,
fetch_imports=False, overwrite=True)` alongside the existing bulk graph load. Verified this
generalizes beyond guideline36 (one manifest file + plain shape fragments) to `libraries/brick/`
and `libraries/brick/imports/` (many files, each independently declaring `owl:Ontology` and
`owl:imports`-ing each other) — per-file registration handles both shapes, since registering the
*merged* directory graph as a single ontology would break wherever a directory contains more
than one `owl:Ontology` declaration.

Verified directly against `ontoenv.OntoEnv`: before the fix, `missing_imports()` on a graph
importing `urn:ashrae/g36` reports it missing after loading the guideline36 directory; after,
it resolves. `test_validate_model_against_shapes` (the only existing unit test that loads this
directory) passes both before and after — it validates only against the ashrae_g36 shape
collection directly, never the manifest that carries the `owl:imports`, so it doesn't exercise
this path and wouldn't have caught the regression.

### `gtf-new-pyshifty` — 4 conflicts, resolved here

PR [#399](https://github.com/NatLabRockies/BuildingMOTIF/pull/399) → `develop`, open since
2026-07-23.

Adds the `pyshifty` SHACL backend, algebraic validation, and template-guided repair.

The conflicts came from the two feature branches disagreeing about **where SHACL inference
runs**. `gtf-ontoenv` had moved it into `CompiledModel.__init__`; `gtf-new-pyshifty` moved it
into a backend abstraction. Resolution on this branch:

- Took the **backend** structure (`Model.compile` → `get_shacl_backend()` →
  `backend.compile_model_graph()`), with `CompiledModel` storing the compiled graph as-is.
  This is the one decision that belongs to no feature branch — it is a choice *between* two
  branches and cannot live on either. `rerere` is enabled on this repo so the resolution is
  replayed automatically if this merge is ever redone.
- `poetry.lock`: regenerated with `poetry lock`, not hand-merged. `pyproject.toml` auto-merged
  and carries both sides.

Three fixes that first surfaced here were pushed **down onto feature branches** so a rebuild
of this branch cannot lose them:

| Fix | Now lives on | Also on this branch as |
|---|---|---|
| `normalize_shacl_engine` re-export from `utils` (flake8 F401) | `b757c342` | `a60bf48f` |
| Normalize `shacl_engine` at the constructor call site (mypy) | `4b15e064` | merge `188c54b6` |
| Preserve source triples through backend compilation | `3e4d5cda` | merge `0198b66a` |

All three are on `gtf-new-pyshifty`, because all three are about code that only exists there
(`buildingmotif/shacl.py` and its callers). The first two are latent defects on that branch
independent of the merge: the flake8 error is live today, and the mypy error is invisible only
because `[tool.mypy] files` does not glob `buildingmotif/building_motif/` — pre-commit catches
it the moment that file is touched.

`3e4d5cda` (source triples) is the one that came out of the merge. `compile_model_graph`
returned only what the engine handed back, so an engine whose `infer()` returns just the
inferred closure (shifty) dropped the model's own triples. It re-adds the pre-inference graph
in `ShaclBackend.compile_model_graph` and `ShiftyBackend.compile_model_graph` — the same
behavior `01280864` protected on `gtf-ontoenv`, re-expressed for the backend architecture.
**Verified standalone** — see below.

#### Update merge `37f59ded` (tip `52d75e6c`) — `pyshifty` made required, in uv form

A review follow-up on `gtf-new-pyshifty` (`52d75e6c`): promotes `pyshifty` from an optional
extra to a **required** dependency pinned to 0.2.x; adds `require_shifty()` so a missing
(now-required) package raises a clear, actionable error instead of a bare `ModuleNotFoundError`;
logs every previously-silent `except Exception` in the repair engine at debug; fixes
`merge_templates_for_focus` to *always* return a `Template` (a name-only merge used to fully
evaluate to a bare `Graph` and trip `assert isinstance(..., Template)`); adds a `GateOutcome`
`Protocol` and widens `Model`/`CompiledModel.validate` to
`Union[ValidationContext, AlgebraicValidationContext]` (clearing three pre-existing mypy errors
in those files); and drops `pytest.importorskip("shifty")` from the test now that the package
is required (a missing required package should fail, not skip).

The six source/test files auto-merged clean. The only conflict was the same poetry-vs-uv split
the `gtf-uv` merge established, but this time on the **incoming** side — `52d75e6c` edits
poetry-format `pyproject.toml`/`poetry.lock`, which no longer exist here. Resolution (this
branch only):

- `poetry.lock`: modify/delete → deleted (uv wins).
- `pyproject.toml`: kept the uv/PEP-621 layout; re-expressed the intent by moving `pyshifty`
  out of `[project.optional-dependencies]` into required `[project.dependencies]` as
  `pyshifty>=0.2.0,<0.3` (the PEP-508 equivalent of the `^0.2.0` pin).
- `uv.lock`: regenerated with `uv lock`; `pyshifty` is now a required root dep. `uv lock --check`
  passes.

This merge also **clears the black note** in the `gtf-uv` section below: `52d75e6c` reformats
the two `algebraic_validation` files with black 22.12.0, so `uv run black --check` is now clean
tree-wide.

#### Reconciling `gtf-new-pyshifty` with origin (2026-07-23, merge `887a70f1`)

`origin/gtf-new-pyshifty` had moved on its own, independent line of development from the same
`ec3646e4` base: `04fad29b` ("refactor: simplify algebraic validation and SHACL backend code")
through `6d7615f3` ("bump pyshifty") — 11 commits including a `RepairConfig` +
relevance-filter template-guided-repair feature (`a82685c5`), template-name-uniqueness scoping
(`9cfb8159`), and its own independent "make pyshifty required" pass that landed on an exact
`pyshifty = "0.2.5"` pin rather than local's `^0.2.0` caret. Neither line of history contained
the other's commits. Resolved by merging `origin/gtf-new-pyshifty` into local
`gtf-new-pyshifty` (`git merge origin/gtf-new-pyshifty`, not a rebase, so the merge commit is a
descendant of `origin`'s tip and the push is a plain fast-forward — no force needed) and pushing
the result, so **local and origin now agree** at `887a70f1`.

Seven files conflicted:

- `pyproject.toml`: both sides had independently made `pyshifty` required (local via caret
  `^0.2.0`, origin via a sequence of exact-pin bumps ending `0.2.5`). Kept origin's exact pin
  (its own deliberately-maintained version) with local's explanatory comment.
- `poetry.lock`: regenerated with `poetry lock`, not hand-merged.
- `model.py` / `compiled_model.py`: both sides touched the same `validate()` signature lines for
  unrelated reasons — local widened the return type to
  `Union[ValidationContext, AlgebraicValidationContext]`, origin added a new
  `repair_config: Optional[RepairConfig]` parameter. Combined both.
- `algebraic_validation.py` (the deep one): combined local's `GateOutcome` `Protocol` typing,
  `require_shifty()` (actionable error on a missing package, used in place of origin's bare
  `import shifty`), and debug-logging in `except Exception` handlers with origin's own
  `_get_summary()` dedup helper, `RepairConfig`, and `defaultdict`-based focus grouping. The
  debug logging was added to origin's `_get_summary()` helper too (rather than keeping two
  parallel implementations), so every caller gets the same diagnostic behavior local's fix
  intended, not just the call sites local had touched directly.
- `utils.py`: **dropped** local's `normalize_shacl_engine` re-export (`b757c342`/`a60bf48f`)
  rather than keeping it. It existed solely because `tests/unit/test_utils.py` imported the
  helper from `buildingmotif.utils`; origin's refactor deleted that test and import entirely, so
  in the merged tree the re-export has no remaining consumer and would just resurrect the
  flake8 F401 problem it was written to fix. This means `b757c342`/`a60bf48f` are now
  superseded — the fix they made is a no-op past this merge.
- `test_algebraic_validation.py`: combined origin's new imports (`warnings`, `RepairConfig`) and
  dropped an `import pytest` origin's own history had left unused.

Verified: pre-commit (isort/black/flake8/mypy, the same hook set and mypy invocation CI uses —
notably *not* filtered by `[tool.mypy] files`, so this catches more than a bare `mypy` run)
passes on every touched file; `poetry lock` regenerated and internally consistent; imports of
every touched module resolve.

This reconciliation was scoped to `gtf-new-pyshifty`/`origin` only; it was brought into
`gtf-buildingmotif` separately as merge #9 (`4fe44201`) — see below.

#### Merge #9 (`4fe44201`, tip `887a70f1`) — bringing the origin reconciliation into `gtf-buildingmotif`

Merge-base was `52d75e6c` (`gtf-new-pyshifty`'s pre-reconciliation tip, already in
`gtf-buildingmotif` via merge #7), so only the delta from the reconciliation above needed
resolving here — the same 12 commits, now layered onto this branch's other already-merged
work (`gtf-ontoenv`, `gtf-uv`).

Six files conflicted, plus one already-familiar poetry-vs-uv split:

- `poetry.lock`: modify/delete → deleted (uv wins, same resolution as every prior poetry/uv
  split on this branch).
- `pyproject.toml`: `pyshifty` was already required on both sides; took incoming's exact
  `0.2.5` pin, re-expressed in uv/PEP-508 form as `"pyshifty==0.2.5"`, over this branch's
  existing `">=0.2.0,<0.3"` caret, keeping the explanatory comment. **Deliberately did not**
  carry over incoming's `pytest-xdist` as a main dependency — on this branch it's supplied via
  `uv run --with pytest-xdist`, not a project dependency, and that convention was kept.
- `building_motif.py` / `api/app.py`: both sides touched the same lines for unrelated reasons —
  this branch's `OntologyEnvironment` import / `graph_store_path` param (from `gtf-ontoenv`) vs.
  incoming's `DEFAULT_SHACL_ENGINE` constant replacing a `"pyshacl"` literal default. Combined
  both in each file.
- `test_223p_templates.py` / `test_brick_templates.py`: **the one worth flagging.** Git's own
  auto-merge (no conflict markers — this is the dangerous part) silently spliced incoming's old
  per-test `PyshiftyBackend`/`AlgebraicValidationContext.from_compiled(...)` manual-call pattern
  into this branch's already-restructured session-fixture test functions, producing code that
  referenced names that don't exist in that scope (`resolved_shape_graph`, module-level
  `s223`/`brick`) and one broken line continuation. This branch had already moved past that
  pattern in `a44a0911` ("perf: defer ontology loading from collection to session fixture," a
  `gtf-ontoenv` commit, merge #2) — converting to a session-scoped fixture + cheap
  YAML/TTL-based template-name enumeration so parametrization doesn't require loading every
  template's `Library` up front. Incoming's line of `gtf-new-pyshifty` never merged
  `gtf-ontoenv`, so it never saw that change and kept building on the old structure. Resolved by
  reverting both files to this branch's existing pattern in full — `m.validate(...)` already
  auto-routes through the algebraic path for the `pyshifty` engine (see `compiled_model.py`
  above), so the manual backend/context calls were redundant, not just misplaced — and dropping
  the now-unused `PyshiftyBackend`/`AlgebraicValidationContext` imports. The one legitimate
  change in each file, `shacl_engine="pyshifty"` (canonical name) replacing the `"shifty"` alias,
  was kept.
- `test_compiled_model.py`: combined imports — this branch's `Literal`/`RDFS` (used by an
  existing test) alongside incoming's `RepairConfig`/`ValidationContext`/`SH`/`A` (used by new
  tests for the `repair_libraries`/`repair_config` engine-mismatch warnings).

**Take the auto-merge lesson seriously going forward:** the two test files above show that git
merging cleanly (no `<<<<<<<` markers) is not proof the result is correct when both sides have
substantially restructured the same function — always diff a heavily-diverged file's *logic*
against what each side actually intended, not just check for marker absence.

Verified: `uv sync`, flake8, mypy (project's configured scope), black, and isort all pass clean
on the full merged tree. `pytest`: `test_compiled_model.py` (9 passed), `test_utils.py` (23
passed), `test_algebraic_validation.py` (18 passed). `test_223p_templates.py` has one failure
(`html5rdf`/rdflib HTML-literal parse error, `BTU-Meter-energy` template) confirmed
**pre-existing** — reproduced identically in a throwaway worktree at the pre-merge commit
(`551cfd30`), so not caused by this merge. `test_brick_templates.py` (124 parametrized cases,
loads the full Brick ontology + qudt files once per session) was not run to completion in this
environment — repeated attempts at 100s/280s/590s and an unbounded run all timed out or were
killed before finishing — but it passes flake8/mypy, and its diff against the pre-merge file is
a clean revert to the existing pattern plus the one intentional `"pyshifty"` rename noted above.
**Running it to completion is the next verification gap** for this merge.

#### Merge #10 (`91f210b8`, tip `049a619f`) — relax the pyshifty pin to the 0.2.x line

Brings in the two-commit fix from PR #399: relaxing the exact `pyshifty==0.2.5` pin to accept
any 0.2.x release, then correcting a mistake caught along the way — a bare two-component
version string (`"0.2"` in Poetry) parses as an **exact** match (`==0.2`, i.e. only `0.2.0`),
not a caret range, unlike a three-component string. The fix uses an explicit caret (`^0.2` in
Poetry). Re-expressed on this branch in uv/PEP-508 form as `"pyshifty>=0.2,<0.3"`.

One conflict (`pyproject.toml`, same line as merge #7/#9) plus the usual poetry.lock
modify/delete (uv wins). `uv.lock` regenerated — a plain `uv lock` kept the already-locked
`0.2.5` rather than jumping to the latest `0.2.6` (same "prefer already-compatible" behavior
as Poetry), so `uv lock --upgrade-package pyshifty` was needed to force it.

A separate, uncommitted local change on this branch (manually bumping the exact pin to
`pyshifty==0.2.6`) was in progress concurrently and got stashed before this merge. It's now
superseded: the range-based pin already resolves to `0.2.6` via the lock, so the manual bump
was dropped when the stash was restored rather than reapplied.

Verified: `uv sync`, mypy (project's configured scope) clean; `pyshifty==0.2.6` installed and
importable.

#### Merge #12 (`198d6861`, tip `94936937`) — bump pyshifty to 0.2.7

On `gtf-new-pyshifty` (poetry-based): `poetry update pyshifty` bumped `poetry.lock` from
0.2.6 to 0.2.7 (`pyproject.toml`'s `^0.2` caret already covered it, so only the lock changed).
Verified there first — `poetry install --sync --extras topquadrant`, `import shifty` /
`importlib.metadata.version("pyshifty") == "0.2.7"`, flake8/mypy clean,
`test_algebraic_validation.py` (18 passed) — before merging.

Same conflict shape as every prior pyshifty merge: `poetry.lock` modify/delete → deleted (uv
wins). `pyproject.toml` needed **no** change this time — this branch's existing
`"pyshifty>=0.2,<0.3"` range already accepts 0.2.7, unlike the 0.2.6 bump (merge #10), which
needed an explicit `uv lock --upgrade-package pyshifty` because a plain `uv lock` keeps the
already-locked version rather than jumping to latest; same command used here for the same
reason. Re-verified on the merged tree: `uv sync --extra topquadrant`, mypy clean,
`test_algebraic_validation.py` (18 passed).

#### Merge #13 (`408aceb3`, tip `5ddf29c1`) — never recommend pyshacl

`references/validation.md` and `references/repair.md` framed `pyshacl` and `topquadrant`
as an interchangeable "legacy" pair you might reach for; reworded to call out `pyshacl`
explicitly as never the right choice, since `pyshifty` already covers standard W3C SHACL
reports (`ctx.report`/`ctx.report_string`) and, as of `pyshifty` 0.2.7, has improved
SPARQL-based SHACL-AF rule inference — the one place a real gap could previously have
justified reaching for `pyshacl`. `topquadrant` stays documented as a rare, Java-backed
fallback for cross-validation against a separate implementation; it just isn't paired with
`pyshacl` as an equivalent option anymore. Docs only, no code — merged clean, same
sibling-worktree-then-merge process as merge #11.

#### Merge #14 (`c3e0cd92`, tip `ae23ad19`) — 223P vocabulary reference, prefer non-deprecated classes

Adds `references/223p_vocabulary.md`: ASHRAE 223P (`s223:`) topology — Equipment/System/
Connectable/ConnectionPoint/Connection/Junction/DomainSpace/Zone, the
`hasConnectionPoint`/`cnx`/`mapsTo` connection pattern, properties/sensors, role/domain/
medium enumerations, discovery snippets, gotchas. Verified against `223p.ttl`'s own
`rdfs:comment` definitions and `libraries/ashrae/223p/nrel-templates/` on disk, not written
from the spec alone — every code snippet run against the real ontology file before being
committed to the doc. Wired into `SKILL.md`'s workflow router and "Other ontologies" table,
and into `docs/guides/agent-skill.md`'s file tree.

Also added deprecation-awareness to class verification in both vocabulary references:
- `brick_vocabulary.md`'s `brick_class()` now follows `owl:deprecated` +
  `brick:isReplacedBy` before returning a class. Verified count: 199 `brick:`-namespaced
  classes carry `owl:deprecated true` in the packaged ontology, 198 with a replacement —
  in **both directions** (older `rec:` ICT classes deprecated in favor of newer `brick:`
  ones, and `brick:` location/room classes deprecated in favor of `rec:` ones, e.g.
  `brick:Auditorium` → `rec:Auditorium`). Don't assume a direction; check every candidate.
- `223p_vocabulary.md`'s new `s223_class()` does the same check, though the vendored
  `223p.ttl` has no deprecated `s223:` classes today. The real deprecation surface in 223P
  is **QUDT** quantity-kind/unit terms (`qudt:deprecated` + `dcterms:isReplacedBy`) used by
  every `QuantifiableObservableProperty`/`QuantifiableActuatableProperty` — `223p.ttl` ships
  SHACL rules that flag these automatically but only at `sh:severity sh:Info`, so they don't
  fail `ctx.valid` or show up under `Violation` severity filtering; documented a `qudt_check`
  helper for it.

Docs only, no code — merged clean, same sibling-worktree-then-merge process as merge #11.

#### Merge #15 (`77be64e3`, tip `6d7bfad2`) — sh:sparql/sh:rule prefix-loss fix, SPARQL diagnostic reporting

Prompted by a request to improve how shifty's SPARQL-constraint reporting surfaces in the
algebraic validation report. Investigating pyshifty 0.2.7's new `Reason.sparql_diagnostic`
(query/bindings/result rows for a failed `sh:sparql` constraint) turned up a real, silent
correctness bug in the `pyshifty` backend integration, not just a reporting gap:

**The bug:** BuildingMOTIF always hands `shifty` an `rdflib.Graph` for the shapes graph.
shifty's Python binding lowers a `Graph` argument to N-Triples before it reaches the native
engine — N-Triples has no `@prefix` declarations — but `sh:prefixes` (and any prefixed name
inside an embedded `sh:sparql`/`sh:rule` query body) resolves against exactly those
declarations. Result: a SPARQL-based constraint or rule using a prefixed name (i.e. virtually
all of them, since nobody hand-writes fully-qualified IRIs inside embedded SPARQL text)
silently never fires once its shapes come from a stored library — no error, no diagnostic,
just a vacuous `conforms`. Verified end to end through `Library.load` → Oxigraph storage →
`Model.validate`, with a `brick:`-namespaced `sh:sparql` constraint that validated correctly
before storage and silently no-op'd after, and separately confirmed `shifty.infer()` produces
`inferred_count == 0` with zero diagnostics for the equivalent `sh:rule`/`sh:construct` case.

**The fix:** `buildingmotif/shacl.py` gains `_shifty_shapes_input()`, used by
`PyshiftyBackend.infer`/`validate`: serializes the shapes graph to Turtle **bytes** (not a
bare `Graph`, and not `str` — shifty's `_to_rdf_input` treats a `str` shapes argument as a
filesystem path first, which raised `OSError: File name too long` on a large serialized
ontology like Brick; `bytes` skips that branch entirely) with BuildingMOTIF's own well-known
prefixes re-bound via `bind_prefixes` (since the storage layer doesn't persist a source
file's namespace bindings at all — only triples). Two supporting fixes: `copy_graph()` now
preserves namespace bindings (it silently dropped them, which would have undone the above the
moment any caller copied the graph); `bind_prefixes()` gained the previously-missing
`ref:`/`s223:`/`bacnet:` bindings. A fully custom, downstream-defined namespace is still not
covered — that binding is gone the instant its shape collection is persisted, and restoring it
would mean capturing/round-tripping namespace bindings through the storage layer itself, well
beyond this fix's scope.

**The reporting improvement:** `AlgebraicReason`/`RepairWitness` in `algebraic_validation.py`
now surface `Reason.sparql_diagnostic` (query, bound variables, result rows) in
`reason()`/`explain()`. The repair-tree side (`RepairSession.witnesses()`, which
`AlgebraicValidationContext.witnesses` wraps) reports every SPARQL failure as a generic opaque
leaf with no detail; the *separate* `validate_algebra()` call the same context also runs has
the rich diagnostic. `AlgebraicValidationContext._reasons_for` correlates the two positionally
per focus (verified empirically: a witness's `summary()` atoms and its matched violation's
`reasons` line up 1:1, including for multiple `sh:sparql` constraints on one shape) — a count
mismatch just skips enrichment rather than risking a wrong pairing. Also fixes a latent
`witness.target()` bug (it's a property, not a method — the `except Exception` around it was
silently swallowing a `TypeError` on every call) and a message-duplication bug where an
author-supplied `{$this}`-style `sh:message` had the focus node prepended a second time.

Six files, no conflicts (fast-forward-shaped merge onto this branch's history) — committed on
`gtf-new-pyshifty` first (in the existing `/Users/gabe/src/NREL/bmotif-pyshifty` worktree, its
own poetry/`rdflib-sqlalchemy` toolchain) and verified there (mypy/flake8/black/isort clean,
`test_utils.py` + `test_algebraic_validation.py` + `test_compiled_model.py`: 52 passed) before
merging here. Re-verified on this branch's uv toolchain: mypy/flake8/black/isort clean; the
same three test files plus `test_model.py`/`test_library.py` pyshifty-parametrized cases: 121
passed (13m — includes the two `test_model.py` cases that load the full Brick ontology, which
is what originally surfaced the `str`-vs-`bytes` file-path-guessing crash).

### `gtf-uv` — 6 conflicts, resolved here

PR [#398](https://github.com/NatLabRockies/BuildingMOTIF/pull/398) → `develop`, open since
2026-07-23.

Replaces poetry with uv (PEP 621 + hatchling + `uv.lock`, CI/CD/Dockerfiles/pre-commit/dev-docs
on `uv sync`/`uv run`/`uv build`). It is a **content-neutral** tooling migration: on its own
branch the dependency set, versions, extras, and Python floor match `develop` exactly. All the
dependency-content differences below exist only because `gtf-buildingmotif` already carries the
`gtf-ontoenv`/`gtf-new-pyshifty` changes — the merge had to re-express those in uv format,
which is a resolution that lives **only on this branch** and is invisible in the eventual
`gtf-uv` PR into `develop`.

Resolution on this branch:

- `pyproject.toml`: took gtf-uv's PEP 621 + hatchling + `[dependency-groups]` structure, then
  folded in the deltas from the other branches — `requires-python >=3.11`, dropped
  `rdflib-sqlalchemy`, added `oxrdflib`, `ontoenv==0.6.0a5`, and the `pyshifty` optional dep +
  extra; dropped the now-unused 3.10 classifier. `rerere` recorded this (and the four below).
- `uv.lock`: **regenerated with `uv lock`**, not hand-merged, so it reflects the merged
  dependency set (adds ontoenv, oxrdflib, pyoxigraph, pyshifty; removes rdflib-sqlalchemy).
- `poetry.lock`: modify/delete → deleted (uv wins).
- `ci.yml` / `cd.yml`: kept gtf-uv's uv steps **and** HEAD's newer action pins
  (`actions/checkout@v7`, `actions/setup-python@v6`, `actions/setup-java@v5`), which a naive
  take of either side would have dropped.
- `buildingmotif/api/Dockerfile`: HEAD had already moved the base to `python:3.11`, so gtf-uv's
  now-stale "python:3.9 was previously used" comment was dropped.
- `developer_documentation.md`: HEAD's `>=3.11` floor + gtf-uv's uv install instructions.

**Known pre-existing issue surfaced here, not caused by the migration:** `uv run black --check`
(and the new CI styling job) uses the venv's black `22.12.0` and flags
`buildingmotif/dataclasses/algebraic_validation.py` + its test, which are byte-identical to
pre-merge HEAD and come from `gtf-new-pyshifty`. pre-commit pins black `22.3.0` (which does not
flag them), so the old `poetry run black` CI would have failed the same way. The fix belongs on
`gtf-new-pyshifty` (reformat with 22.12, or align the pinned version), not in this merge.

**Resolved:** fixed on `gtf-new-pyshifty` in `52d75e6c` (reformatted both files with black
22.12.0) and merged here as #7 (`37f59ded`). `uv run black --check` is now clean tree-wide.

### `gtf-api-cleanup` — merged as #17 (`7c89302e`), based on `gtf-buildingmotif`

**The one branch here not cut from `develop`.** Requested to be based on `gtf-buildingmotif`
so it lands after the existing branches; it depends on their combined state (the pyshifty
`AlgebraicValidationContext`, which exists only on `gtf-new-pyshifty`, and the Oxigraph
two-store split from `gtf-ontoenv`, which is what makes the commit-boundary problem real).
**Consequence to plan for: it cannot open a PR into `develop` until #396/#398/#399 land, or
it must be rebuilt onto `develop` afterwards.**

Consumer-facing API cleanup, driven by `API-CLEANUP.md` (repo root), which is the authoritative
record: 17 of 21 reviewed items done plus one feature, each entry giving the file references,
what was actually wrong, and why the fix took the shape it did. **Read that rather than
re-deriving any of this.** 80 files, +3822/-890.

#### What landed

**Setup and lifecycle**
- Tables are created for every backend. Previously only in-memory SQLite auto-created them,
  so the first operation against a file-backed or Postgres database died with a bare
  `OperationalError: no such table`. `create_tables=False` opts out for Alembic-managed schemas.
- `BuildingMOTIF` is a context manager: commits on clean exit, rolls back on exception, closes
  either way, resets the singleton. This is the ergonomic answer to the two-store split
  `gtf-ontoenv` introduced -- triples write through to Oxigraph immediately while the rows
  pointing at them need a SQL commit.
- `setup_logging` no longer reconfigures the host application. It was adding **two root-logger
  handlers per construction, unbounded** (10 after 5 constructions), forcing root to DEBUG, and
  writing a truncating `BuildingMOTIF.log` into the cwd every time. Handlers are now replaced,
  the root level is only ever lowered, and the log file is opt-in via `log_file=`.

**Single-typed APIs** (each replaced a union or a sentinel that forced callers to branch)
- `Model.validate()` -> `ValidationResult` protocol; both context classes satisfy it
  structurally. Four real divergences had to be fixed to make that true.
- `Template.evaluate()` -> `substitute()` (always a Template) + `to_graph()` (always a Graph).
  Removed **ten `isinstance` checks** that existed only to unpack the old union.
- `Library.load()`'s four keyword-dispatched operations -> `from_ontology` / `from_directory` /
  `by_name`, with `load(id)` becoming the by-id loader like `Template.load(id)` and
  `ShapeCollection.load(id)` always were.
- Five overlapping `Template` parameter accessors -> `parameters` (unchanged) plus
  `parameters_with_dependencies(transitive=, renamed=, include_self=)`.
- `CompiledModel`'s `"default"` engine sentinel -> `None`, matching its neighbours.

**Correctness**
- `as_templates()` no longer raises `NotImplementedError` on any `sh:or` violation, which used
  to discard *every* repair in the report rather than just the unresolvable one.
- `validate_model_against_shapes` now matches the configured engine; it returned a legacy
  `ValidationContext` even under pyshifty, so one object gave different context types from its
  two validation methods.
- `Template.add_dependency` had **three** bugs: wrong arity was a silent no-op, the keyword form
  its own `@overload` documented raised `IndexError`, and unknown/duplicate keywords were
  ignored.
- `Library.from_ontology(...).name` returned a `URIRef` where `by_name()` returned `str`; since
  `URIRef.__eq__` is type-strict, `lib.name == "urn:ex/ont"` was False.
- No `raise Exception(...)` left in the package -- `ValueError` for caller error, `RuntimeError`
  for broken invariants, all still `Exception` subclasses so `except Exception` still works.
- Deleted `utils.template_to_shape` and its five private helpers (152 lines): no callers, and two
  unreachable runtime bugs.

**New capability**
- A shape's `sh:or` decompiles into ordered alternative templates (`<shape>-alt1`, `-alt2`, ...
  in `rdf:List` declaration order) instead of being silently dropped -- issue #306. Templates
  stay non-disjunctive by design: they generate fragments, and alternation belongs to the
  *requirement*. `API-CLEANUP.md` records why same-named templates were rejected as the
  mechanism (blocked by `UniqueConstraint("name", "library_id")`, destroys a duplicate-name
  diagnostic, forks dependency inlining combinatorially).

**Tooling**
- `[tool.mypy] files` globbed one level, so `uv run mypy` checked 11 of ~103 files and skipped
  nearly the whole package. Widened; the 26 errors that surfaced were all real and are fixed.
  The config also disagreed with the pre-commit hook's flags, so a bare run reported 27 spurious
  `import-untyped` errors; both are aligned now, and `uv run mypy` enforces what CI does.

#### Deprecations

`Template.evaluate()`, `Library.load(ontology_graph=/directory=/name=)`, `all_parameters`,
`dependency_parameters`, `transitive_parameters`, and the three-argument `add_dependency` all
still work and all warn. **The whole codebase was migrated off them** -- 134 `Library.load`
call sites, 25 `evaluate()` sites, and every parameter-accessor use across tests, notebooks,
`docs/`, and `.agents/`. Verified by a full run's warnings summary: zero BuildingMOTIF
deprecation warnings across the suite. The only remaining uses are the tests that exist to
cover the deprecated paths.

#### Merge #17 (`7c89302e`, tip `34967435`) — two conflicts, both anticipated

`references/templates.md` and `references/validation.md`. Merge #16 on
`gtf-buildingmotif-skill` had fixed `t.all_parameters()` / `t.parameter_counts()` being
written with parentheses (they are properties, so those examples raised `TypeError`);
`gtf-api-cleanup` rewrites those same lines because it deprecates `all_parameters` in favour
of `parameters_with_dependencies()`.

**Resolved by taking `gtf-api-cleanup`'s version in both** — it supersedes, since the member
being called correctly is no longer the recommended API. The skill-branch fix still earns its
place on its own branch, whose PR targets `develop`, where `all_parameters` is current API and
the parens bug is live. This conflict was predicted and written down here *before* the merge;
`rerere` has now recorded both resolutions.

#### Notebook migration -- the part that needed judgement

Notebooks were transformed by parsing the JSON and matching balanced parens, then audited by
hand, because the mechanical rule `evaluate(...)` -> `substitute(...).to_graph()` is **wrong
wherever a call was only partially bound** (`to_graph()` raises there instead of returning a
Template). Two cases: `Template-Usage.ipynb` bound only `name` then read `.parameters`; and
`223PExample.ipynb` collects fifteen results into a list that a later cell fills via
`isinstance(templ, Graph)` -- invisible to an attribute-usage audit, found by chasing the
leftover `isinstance` checks. **If this branch is ever rebuilt, re-audit rather than re-running
the script.**

### `gtf-api-ergonomics` — merged as #18 (`bf7584b8`), based on `gtf-buildingmotif`

The remaining `API-CLEANUP.md` items after #17, on a fresh branch cut from `gtf-buildingmotif`
at `7c89302e`. **Same rebasing consequence as `gtf-api-cleanup`** — not cut from `develop`, and
it additionally builds on `gtf-api-cleanup`'s work (`ShapeCollection.replace_graph`, the
`AlgebraicValidationContext` protocols), so the two should be rebuilt or landed together.

Three commits, 13 files, +405/-90.

#### What landed

- **`Model.create(uri=...)`** — the parameter was called `name`, validated as a URI, used as the
  `owl:Ontology` subject, and passed an `rdflib.Namespace` by every tutorial. Renamed, with
  `name=` kept as a deprecated keyword-only alias; passing both raises `TypeError` rather than
  silently preferring one. Positional `Model.create(BLDG)` is unaffected. This naming is the
  root of **issue #339** ("an alternative constructor for model which takes in a graph path") —
  `Model.from_file` has existed all along, so that issue is a discoverability failure, not a
  missing feature, and the `create` docstring now cross-references `from_graph`/`from_file`.
- **`add_to_manifest` / `replace_manifest`** — `update_manifest` did `graph += manifest.graph`:
  the name promised replacement, the code merged, and there was **no way to replace a manifest
  through the public API** — it could grow but never shrink. Both operations now exist under
  honest names, `replace_manifest` built on `ShapeCollection.replace_graph` so it inherits
  copy-on-write. `update_manifest` still works and warns.
- **`RepairProposal.apply()` / `.advance()`** no longer require the caller to fish `ctx.session`
  out of the context and hand it back to a proposal that came out of that very session. The
  proposal carries it; an explicit session still wins. `_session` is excluded from `repr` and
  equality — it is provenance, not identity — and a hand-built proposal without one raises
  `ValueError` naming what to pass instead of `AttributeError` on `None`.
- **`AlgebraicValidationContext.report`** documents that reading it re-runs `shifty.validate()`.
  Behavior unchanged; the algebraic engine produces no W3C report as a by-product. It is a
  `cached_property`, but contexts are re-created each loop iteration, so "once per context" can
  mean once per iteration. Points at `report_string`, which is free.

40 call sites migrated (33 `Model.create` keyword uses, 7 `update_manifest`). Zero BuildingMOTIF
deprecation warnings in the full-run warnings summary, so the migration is complete.

#### Item 14 rejected — the backlog entry was wrong

`API-CLEANUP.md` claimed a mistyped `shacl_engine` is "only caught deep into a compile". It is
not: `normalize_shacl_engine` validates at the `BuildingMOTIF` constructor, at `validate()`, and
at `compile()`, each raising `ValueError` listing the valid choices — all three verified before
implementing anything. A `ShaclEngine` enum would add editor autocomplete and nothing else,
while still having to accept plain strings (every doc, test, and notebook passes them), creating
two ways to say one thing. The entry is kept, marked rejected, with the disproof, rather than
deleted.

**Item 19 (`TemplateBuilderContext`) is deferred**, by decision, not oversight — it is the one
reviewed item left undone.

#### One skill edit lives here, not on `gtf-buildingmotif-skill`

`references/writing_shapes.md` switches two snippets to `add_to_manifest`. Unlike merge #16's
skill fix, this one **cannot** go on the skill branch: `add_to_manifest` does not exist on
`develop`, so that branch's PR would document a method its target does not have.

#### Merge #18 — clean, and deliberately not re-tested

No conflicts; nothing landed on `gtf-buildingmotif` between the branch point and the merge, so
the merge commit's tree is **byte-identical** (same tree hash `b0133ab3`) to the tip that the
full suite already ran against — **535 passed, 1 skipped**, versus a 518 baseline plus 17 new
tests. Re-running the suite would have exercised the same tree.

#### Merge #19 (`dda5084f`, tip `8ea7ce7c`) — agent-skill API refresh

An audit of all 11 skill files against both API branches. `gtf-api-cleanup` had already carried
its own changes in (`substitute`/`to_graph`, `from_ontology`/`by_name`,
`parameters_with_dependencies`, the `sh:or` alternatives, the context manager, auto-created
tables), so only three gaps remained — all from `gtf-api-ergonomics`, which had fixed just the
one file that happened to conflict during merge #18:

- `building_models.md` still described `Model.create`'s parameter as `name` — the exact
  confusion the rename exists to remove.
- `repair.md` passed `p.apply(ctx.session)`, now the exception rather than the rule.
- `writing_shapes.md` documented `add_to_manifest` but not `replace_manifest`, so the
  merge-vs-replace distinction the split exists to express was invisible.

Docs only, no code, so no test run. Both new claims were checked against the implementations
rather than from memory (`replace_manifest` delegates to `ShapeCollection.replace_graph`;
`_resolve_session` raises `ValueError` naming `ctx.session`). The `templates.md` notes on
`evaluate()` and the deprecated parameter accessors are deliberate and stay — they describe
what an agent will meet in existing code.

Committed on `gtf-api-ergonomics` for the same reason as merge #18's skill edit:
`replace_manifest` and the zero-argument `apply()` do not exist on `develop`.

**This is the second time skill drift was found only by asking.** The skill is not covered by
any test, and nothing in the merge process checks it against the API it documents — so after
any consumer-facing change, grep it for the old names.

#### Merges #20 (`a66bf370`) and #21 (`9eebfc13`) — the sweep that should have come first

Two follow-ups, both found by running the grep *after* committing #19 rather than before:

- `repair.md` had a **second** `p.advance(ctx.session)`, an inline mention 44 lines above the
  code block #19 fixed. Fixing the obvious occurrence and not sweeping the file is how one
  becomes two commits.
- `notebooks/Existing-model-repair-with-pyshifty.ipynb` threaded `ctx.session` through
  `advance()` in a code cell whose own surrounding prose already said `advance()`. Behaviour is
  identical — an explicit session still wins — so the committed cell outputs stay valid.

`notebooks/`, `docs/` and `libraries/` were then swept for every API either branch changed
(`Model.create(name=)`, `update_manifest`, `evaluate()`, the three deprecated parameter
accessors, keyword `Library.load`): **nothing else stale**. `gtf-api-cleanup`'s notebook
migration and merge #18's call-site migration had already covered them; only the repair-session
change (#15), which landed after those sweeps, had leaked.

### Merges #27, #28, #29 — three test/perf fixes, all clean (2026-07-28)

Prompted by two failures the maintainer hit on `uv run --with pytest-xdist pytest -n auto`:
two `test_libraries` params failing on `UNIQUE constraint failed: library.name`, and the
`Existing-model-validation-example` notebook.

**#27 `gtf-test-isolation`** — cut from `develop`, because the bug is *entirely pre-existing*
there: `develop` already has the tests that leak the singleton
(`tests/library/test_brick_templates.py:53,74`, `test_223p_templates.py:76,95` assigning
`BuildingMOTIF.instance = bm` and never clearing it), the `bm` fixture that has no setup-time
clean, and the test that trips over it (`test_library.py:190` creating a library named
`https://brickschema.org/schema/1.4/Brick`). Nothing about it belongs to any of the four
features. Only reachable under `-n auto`, because sequentially all of `tests/unit` runs before
`tests/library`.

**#28 `gtf-matcher-perf`** — also cut from `develop`; `develop:buildingmotif/template_matcher.py:229`
has the unhoisted conversion verbatim. Independent of #27, so the two PRs can land in either
order.

**#29 `gtf-new-pyshifty`** — the notebook cap and the `repair_libraries` doc fix could not go to
`develop`: it has no `buildingmotif/shacl.py`, no `algebraic_validation.py`, and no mention of
pyshifty at all. Note the branch ref was **one commit behind `origin`** (`94936937` vs
`6d7bfad2`); fast-forwarded before committing, so nothing forked.

**No conflicts in any of the three**, but #29 was the one to watch and is worth recording: the
notebook cell it edits differs between the two branches, because `gtf-api-cleanup`/
`gtf-api-ergonomics` migrated it here (`all_parameters` -> `parameters_with_dependencies`,
`evaluate()` -> `substitute().to_graph()`) and those branches do not exist on
`gtf-new-pyshifty`. The patch applied cleanly on both bases and the merge resolved correctly —
the merged cell has the new cap *and* this branch's newer API — but it was verified by reading
the merged cell, not assumed from "no conflict".

One design note carried in the commit rather than the diff: the cap counts **repairs collected,
not entities visited**. Only 42 of 88 failures yield a sound proposal and the first is the 47th,
so `diffset[:N]` would have produced an empty demo.

### Merge #30 — local branch had diverged from its own remote (2026-07-28)

Worth knowing before the next push: `gtf-buildingmotif` was **behind `origin` by 2 while ahead by
7**. The remote carried `f809f25c` / `03c3ebbe`, which delete `buildingmotif/progressive_creation.py`
and a stray `brick2af/examples/test.log` swept in during the a8 pin bump. Merged (not rebased —
this branch's history is merge-based). Clean: nothing in #27-#29 touches either file, and no
module still references `progressive_creation`.

`develop` is level with `origin/develop`, and `gtf-buildingmotif` already contains all of it, so
there is nothing to pull down from `develop`.

### Merge #37 — pyshifty 0.4 interface, merged clean (2026-08-30)

Two commits on `gtf-new-pyshifty` (`ca89c9c0`, `770073ab`) taking the interfaces pyshifty
0.4 exposes, plus the pin bump to `pyshifty>=0.4,<0.5` and the matching `uv.lock`. Merged
with no conflicts, but it **auto-merged against the `gtf-manifest` work** in
`compiled_model.py` (which had added the `manifest` constructor parameter and the
`resolved_shapes` path in `shacl.py`). Both survived; the full unit suite was run on the
merge result, not only on the feature branch.

What the two commits add:

- `RepairWitness.target_shape` reads the failing shape off the witness (`Failure.shape_iri`)
  instead of off the *paired* violation, so it no longer goes `None` when the
  `(focus, statement_id, constraint_id)` join misses (`alignment == "unavailable"`).
- `RepairWitness.missing_edges` — a cardinality deficit as node/path/count/qualifier, i.e.
  the edge that would close it, without walking a repair tree.
- `AlgebraicValidationContext.preview(proposal)` — the run the model would have under
  `G ⊕ ΔG`, pure, off a lazily built `EvidenceSession`.
- `CompiledModel.shape_map()`, backing `shape_to_df`/`shape_to_table`. `shape_to_df` keeps
  its old contract; `include_nonconforming=True` is the widened view.
- The `Failure` protocol in `algebraic_validation.py` is spelled `ShiftyFailure`, because
  `validation_result.Failure` already exists and means something different (the protocol
  `RepairWitness` *satisfies*, not the one it *wraps*).

**A required fix, not an optional one:** pyshifty 0.4 rejects an explicitly supplied
zero-triple shapes graph instead of reporting vacuous conformance.
`AlgebraicValidationContext.__post_init__` passed `shapes_input` unconditionally and so
raised `ValueError: explicit shapes graph is empty` for an empty shape-collection list.
`PyshiftyBackend.validate`/`.infer` had always guarded this; the context had not, even
though its own `report` property did. Regression test:
`test_empty_shape_collection_list_validates`.

#### Upstream bug found and worked around

**pyshifty 0.4.0 `shape_map()` does not resolve `sh:name` when a node shape has exactly one
property shape**; with two or more it resolves them correctly. The smallest repro is one
`sh:NodeShape` with a single `sh:property` carrying `sh:name` — `Binding.name` comes back
`None`; add a second `sh:property` and both names appear. This is why `CompiledModel._slot_index`
reads the slot names out of the shapes graph and matches them to bindings on
`(path IRI, qualifier class IRI)` rather than trusting `Binding.name`. Regression test:
`test_shape_to_df_names_a_single_slot_shape`. **Remove the fallback once this is fixed
upstream** — the `Binding.name` read is already preferred when it is populated.

Related, and worth knowing before anyone passes a custom `name_path`: a *prefixed* path is
resolved against the prefixes declared in the document shifty parses, and an unresolvable
one raises `ValueError: undeclared prefix`. `_shifty_shapes_input` re-binds BuildingMOTIF's
well-known prefixes (including `sh:`), so the default is safe; anything else needs a full
IRI in angle brackets. Same root cause as the `sh:sparql` prefix-loss fix in merge #15.

#### `origin/gtf-new-pyshifty` had been overwritten with `gtf-buildingmotif`

Found while picking a base for this work, and **not resolved** — recorded so the next
person does not rediscover it.

The 2026-07-29 push-status entry below says `gtf-new-pyshifty` was deliberately not pushed
and warns that "something else is pushing to it". That has since gone further: the local
branch sat at `3f011108` (the row-29 tip) while `origin/gtf-new-pyshifty` was 98 commits
ahead at `37fe5fb1`, whose first parent is `8b16aeec`, *a `gtf-buildingmotif` merge commit*.
Someone committed on top of `gtf-buildingmotif` and pushed that to the `gtf-new-pyshifty`
remote ref.

Consequences:

- **PR #399 no longer proposes only pyshifty.** Its head is the integration branch, so the
  PR carries `gtf-ontoenv`, `gtf-uv`, `gtf-buildingmotif-skill`, `gtf-manifest` and the
  knowledge-base work as well — 126 commits and 117 files against `develop`.
- `37fe5fb1` ("expose native algebraic provenance", the 0.3 uptake) exists **only** on that
  line. It is not on any branch rooted at `develop`, so a clean rebuild of
  `gtf-new-pyshifty` from `develop` has to bring it across explicitly or lose it.
- This work was cut from `origin/gtf-new-pyshifty` at the maintainer's direction, because
  that is where the pyshifty work actually lives; it therefore inherits the situation rather
  than fixing it. The local branch was fast-forwarded to origin first (0 ahead, 98 behind —
  nothing local-only was lost).

Rebuilding a pyshifty-only branch for #399 means cherry-picking `37fe5fb1`, `ca89c9c0` and
`770073ab` — plus the earlier pyshifty commits listed in rows 3-29 — onto `develop`. Nobody
has done that.

#### Gap in the merge table

Rows 32-36 were never recorded. The merge commits themselves carry the numbering
(`34241fd1` #30 through `d8fd503b` #34, all `gtf-manifest`), then `2f0ccbff`
(`gtf-knowledge-base`) and `c7101b56` (`gtf-buildingmotif-skill`) went in unnumbered.
Reconstruct them from `git log --merges --first-parent 01f7f689..` if the detail is needed;
this entry does not attempt it.

### Merge #38 — data-as-shapes prefix fix, 1 conflict resolved here (2026-08-30)

One commit (`bd3e48f5`). Found by running the unit suite against an unreleased pyshifty
0.4.1 build: `test_model_compile[pyshifty]` failed with
`ValueError: invalid shapes graph: ... Prefix not found`.

**It was not a pyshifty regression.** Three call sites hand shifty a data graph with *no*
shapes argument, which makes the data graph its own shapes graph — so a SHACL-SPARQL body
inside it has to arrive with the prefix declarations its query text resolves against, the
same guarantee `_shifty_shapes_input` gives a real shapes graph. It was not getting it.
`Library.from_ontology("Brick-full.ttl")` therefore ran inference over a Brick graph our
storage layer had already stripped the `ref:` binding from, and Brick's own rules and
constraints use `ref:hasExternalReference`. **Those queries had been silently skipped all
along** — the rules never fired and nothing said so. pyshifty 0.4.1 raises instead of
skipping, which is the only reason it surfaced.

Fix: `_shifty_data_input`, guarded by `_has_sparql_bodies` so the copy-and-serialize
(~1.3s on Brick, against ~3.3s for the inference itself) is only paid by a graph that
actually carries SPARQL bodies. Applied to `PyshiftyBackend.infer`, `.validate`, and the
empty-shape-collection branch of `AlgebraicValidationContext` (repair session, algebra
pass, and W3C report path), which had the identical latent bug.

Regression test `test_pyshifty_inference_keeps_prefixes_when_data_is_also_shapes`; verified
to fail with the fix reverted, and valid on both pyshifty lines (0.4.0 silently infers
nothing, 0.4.1 raises).

Still outstanding, and **not** fixed here: the storage layer does not round-trip namespace
bindings at all. `bind_prefixes` restores BuildingMOTIF's well-known prefixes, which covers
any shape written against one of our own ontologies, but a custom downstream-defined prefix
is still lost when its graph is persisted — now loudly rather than silently. Fixing that
means persisting bindings through `GraphConnection`; it deserves its own issue.

#### The conflict — `buildingmotif/shacl.py`, resolved by keeping both sides

Purely additive, and it exists on no feature branch. `gtf-manifest` had added
`_resolved_shape_graph` immediately after `_shifty_shapes_input`; `gtf-new-pyshifty` added
`_has_sparql_bodies` and `_shifty_data_input` at the same spot. Neither touches the other,
so both were kept, manifest's first. Verified afterwards that every top-level `def`/`class`
from both parents survives the merge (11 + 12 with 10 shared = 13).

## Verification status

- **Not re-run after merge #30.** The 722-passed result below predates it. #30 only deletes an
  unreferenced module and a log file, so the risk is low, but the number is stale by one merge.
- `pytest tests/unit tests/library -n auto` on `gtf-buildingmotif`: **722 passed, 1 skipped**,
  23m14s (2026-07-28), with merge #27 applied. This is the run that clears the
  `UNIQUE constraint failed: library.name` failures — it is also the first recorded run that
  collects `tests/library` *together with* `tests/unit`, which is what exposed them.
- `tests/integration/test_notebooks.py -k Existing-model-validation-example` on
  `gtf-buildingmotif`: **1 passed, 225s** (2026-07-28), with merge #29 applied. Was a 600s cell
  timeout before. The other 18 notebooks were deselected and are **still not run**.
- **Gap on #27/#28: neither was re-run on its own branch.** Both were verified in the merged
  tree here (and the merged tree is byte-identical to what was tested — 5 files, `git diff
  40c5116d..HEAD`), and both patches apply to `develop` cleanly, but `tests/library` runs
  *without* pyshifty on `develop`, so the isolation fix wants one run there before #27's PR goes
  up. #28's own check: `generate_all_subgraphs` output is byte-identical before/after under a
  fixed `PYTHONHASHSEED`, and `test_template_api.py` + `test_algebraic_validation.py` pass
  (29 tests) — plus 7.66s -> 6.36s on a 4-node guideline36 template against a 6k-triple model.
- `pytest tests/unit` on `gtf-buildingmotif`: **369 passed, 1 skipped**, 25m14s (2026-07-22).
  Includes `test_validate_model_against_shapes` across all three engines, which exercises the
  conflict resolutions above. Pushing the three fixes down onto feature branches left the
  working tree **byte-identical** (`git diff a60bf48f` is empty), so that result still stands.
- `pytest tests/unit` on `gtf-new-pyshifty` (standalone, own venv with `rdflib-sqlalchemy`):
  **361 passed, 2 skipped**, 44m32s (2026-07-22). flake8 and mypy (`--ignore-missing-imports`)
  both clean. This clears the earlier "not verified standalone" note on `3e4d5cda` — the
  source-triples fix, and the two lint/type fixes pushed onto this branch, all hold on the
  branch itself, not just in the merged tree. The count differs from the integration branch
  (361 vs 369) because the two branches wire up different engines and storage backends, so the
  parametrized fixtures expand differently; both are green.
  - Install note: `--all-extras` needs `LDFLAGS="-L$(brew --prefix openssl@3)/lib"` on macOS or
    psycopg2 fails to link `ssl`.
- `pytest -m integration`: **not run** on any branch. `gtf-ontoenv` carries a commit
  specifically about integration-test repairs, so this is the gap worth closing before the PRs
  go out.
- pre-commit (isort/black/flake8/mypy) passes on the merged tree **for staged files**. The
  whole-tree `uv run black --check` gap noted above (venv black 22.12.0 vs pinned 22.3.0) is
  **closed** by merge #7 (`37f59ded`): both `algebraic_validation` files were reformatted with
  22.12.0 in `52d75e6c`, so `uv run black --check` is clean tree-wide.
- After merge #7 (`37f59ded`, made `pyshifty` required in uv form), black/isort/flake8/mypy are
  clean on the merged source files and imports resolve; `uv lock --check` passes. Full
  `pytest tests/unit` on the uv toolchain has **not** been re-run since (same gap as the
  `gtf-uv` merge below).
- After the `gtf-uv` merge (`621d1f7c`), full `pytest tests/unit` has **not** been re-run.
  Smoke-verified only: `uv sync` with the `topquadrant` + `pyshifty` extras, import of
  `buildingmotif`/`ontoenv`/`oxrdflib`/`shifty`, `uv lock --check`, wheel build, flake8/isort
  clean, and `tests/unit/test_utils.py` green across all three engines (23 passed). Running the
  full unit suite on the uv toolchain is the next verification gap.
  - Install note (uv): `uv sync --all-extras` still fails to build `psycopg2` from source on
    macOS without Postgres headers (same root cause as the poetry `LDFLAGS` note above); it
    builds fine on the Linux CI runners. Use `uv sync --extra topquadrant --extra pyshifty`
    locally to skip the `postgres`/`all` extras that pull source `psycopg2`.
- After merge #9 (`4fe44201`, the `gtf-new-pyshifty`/origin reconciliation): `uv sync`,
  flake8/mypy/black/isort clean. `test_compiled_model.py`, `test_utils.py`,
  `test_algebraic_validation.py` pass in full (see the merge #9 branch note above for counts).
  Full `pytest tests/unit` and `test_brick_templates.py` have **not** been re-run since — same
  gap as the two entries above, now compounded. This is the next thing to close before any of
  these PRs go out.
- After merge #15 (`77be64e3`, the prefix-loss fix): see the branch note above for the
  per-toolchain verification (both `gtf-new-pyshifty`'s own poetry venv and this branch's uv
  venv). Full `pytest tests/unit` has **not** been re-run tree-wide since — same standing gap.
- **The standing "full unit suite not re-run" gap above is CLOSED as of merge #18** (2026-07-25).
  `uv run pytest tests/unit -n auto` on the merged `gtf-buildingmotif` tree: **535 passed,
  1 skipped**, 9m21s, on the uv toolchain with the `pyshifty` + `topquadrant` extras. This is
  the first full tree-wide run since merge #7, and it covers the accumulated gaps flagged under
  merges #7, #9 and #15 — all three named the same missing run. 518 of those tests are the
  pre-`gtf-api-cleanup` baseline; the other 17 are new.
  - Also clean tree-wide at that commit: flake8, `uv run mypy` (105 files — the config used to
    glob only 11, see the `gtf-api-cleanup` note), black, isort.
  - Zero BuildingMOTIF `DeprecationWarning`s in the run's warnings summary, which is the
    evidence that the `gtf-api-cleanup`/`gtf-api-ergonomics` call-site migrations are complete
    rather than merely started. The only remaining uses of deprecated APIs are the tests that
    exist to cover the deprecated paths.
- `pytest -m integration` remains **not run** in full on any branch — the only outstanding
  verification gap, and the one worth closing before the PRs go out. `gtf-ontoenv` carries a
  commit specifically about integration-test repairs. One integration test *was* run
  individually, below.

### `Existing-model-validation-example.ipynb` fails — pre-existing, not the API branches (2026-07-25)

Running `uv run --with pytest-xdist pytest -n auto` with **no path argument** collects
integration tests too — `pytest.ini`'s `addopts` only deselects `bacnet`. Every green run
recorded above was `pytest tests/unit`, so that combination had never been exercised.

`tests/integration/test_notebooks.py::test_notebook[notebooks/Existing-model-validation-example.ipynb]`
fails with a **600s cell timeout on cell 17** — not an exception.

**A/B, run directly, both sides fail on cell 17:**

| Tree | Cell 17 code | Result |
|---|---|---|
| `77be64e3` (before both API branches) | `t.evaluate(templ_bindings)` | FAILED, 901s |
| `gtf-buildingmotif` (current) | `t.substitute(templ_bindings).to_graph()` | FAILED, 873s |

So it is **pre-existing** and not caused by the API migration, despite that cell being one the
migration rewrote. The A/B used a throwaway worktree at `/Users/gabe/src/NREL/bmotif-ab`
(detached at `77be64e3`, own venv — note `pyshifty` is a *required* dep there, not an extra, so
`uv sync --extra topquadrant` is the right sync).

**Mechanism**, from `sample`-ing the stuck process rather than guessing:

```
OntoEnv::copy_closure -> get_union_graph -> PythonGraphIO::union_graph
  -> copy_graph -> graph_from_rdflib -> PyIter_Next -> unicode_new ...
```

The time goes into OntoEnv computing an import closure and marshalling every triple across the
Rust/Python boundary one term at a time. The call site is `library.py:202`, which copies the
whole closure graph and **discards it** (`_, closure_names = ...closure_copy(...)`), keeping
only the names. `git blame` credits that line to the `Library` constructors commit, but that is
just blame following moved code — `77be64e3` has the identical call, graph discarded and all. It
arrived with `gtf-ontoenv`, whose own notes list the perf phase as still pending.

**Worth fixing on `gtf-ontoenv`, not either API branch:** expose a names-only closure call so
this path stops materialising a union graph it throws away. **Done** — see the a8 migration
below.

> **Superseded (2026-07-28).** The closure-copy fix was real but it was **not** what made cell 17
> time out, and the notebook still failed after it. Profiling the cell rather than sampling the
> process: library loading (the OntoEnv path above) is ~170s of the run, while cell 17 alone is
> **1262s inside `as_templates()`**. The cause is the engine default, not OntoEnv — the notebook
> passes no `shacl_engine`, so it gets `pyshifty`, `validate()` returns an
> `AlgebraicValidationContext`, and `as_templates()` runs the template-guided repair search over
> all 88 failing entities instead of the cheap `GraphDiff` path the cell was written against.
>
> Of the 88 failures, 46 yield no sound proposal and cost ~0s; the other **42 cost ~30s each**,
> and 97% of that is pyshifty's native `RepairSession.gate()` at ~1.0s per call. The call count
> is `1 + candidate_limit` per base spec (16 `pyshifty-candidate` + 1 `synthesized` = the 17
> gates observed), and it is structural: `propose()` ranks *after* generating, so it cannot
> early-exit. No redundancy — 17 gate calls, 17 distinct deltas, 0 duplicates. There is no
> BuildingMOTIF-side hot spot; Python code is <0.5% of `propose()`.
>
> Fixed on `gtf-new-pyshifty` (merge #29) by capping the cell, not by changing the engine.
> Notebook goes from a 600s timeout to **passing in 225s**. The lever if this comes back is
> `RepairConfig(candidate_limit=...)` via `Model.validate(repair_config=...)`, which scales
> linearly: 16 -> 22.5s, 4 -> 7.6s, 1 -> 3.9s per witness.
>
> Open question left for the maintainer: `as_templates(limit_per_witness=1)` gates 17 candidates
> to keep 1, so a lower default `candidate_limit` on that path would be ~4x faster — at the cost
> of best-of-17 becoming best-of-5.

### ontoenv 0.6.0a5 -> 0.6.0a8 (merges #22 and #23, 2026-07-26)

Pin bumped on `gtf-ontoenv` (poetry) and re-resolved on `gtf-buildingmotif` (uv). Unit suite
**535 passed, 1 skipped** on a8 — unchanged from a5, no regressions. None of a8's breaking
changes touch the API BuildingMOTIF uses: we call `copy_graph` not `get_graph`, neither
`snapshot_as_dataset` nor `as_dataset`, and none of the removed top-level helpers.

**Trap for the next reader:** ontoenv's changelog `[Unreleased]` section is **ahead of the
published alphas**. `get_closure_view`, described there, does not exist in a8 — a8 spells the
read-only view `get_closure`. Do not read that section as a spec for this pin.

#### `closure_names` — the discarded-closure fix

Two call sites did `_, closure_names = closure_copy(...)`: materialise the whole imports
closure across the FFI boundary, then throw it away for a name list. Now
`OntologyEnvironment.closure_names`, wrapping `list_closure`. Brick 1.4 closure, 15 graphs,
~155k triples, three reps:

| call | reps | note |
|---|---|---|
| `list_closure` | 0.000s, 0.000s, 0.000s | names only |
| `copy_closure` | 4.271s, 3.879s, 5.322s | materialises every call |
| `get_closure` | 8.846s, 0.000s, 0.000s | eager permutation indexes, then free |

Same 15 names from all three. `get_closure` is the trap here: it *looks* right (read-only,
zero-copy) but builds all four permutation indexes eagerly at bind time — worth it for repeated
queries against a closure, pure overhead for one name lookup. A `closure_view` wrapper around it
was written and deleted once measured. `closure_copy` stays in use at
`ontology_environment.py:160`, whose caller may mutate the graph; a `ViewGraph` would raise.

#### `init_from_store` -> real lifecycle entry points

a8 deprecates the flag, which BuildingMOTIF passed on **every** construction — the unit suite
went 58 -> 527 warnings, one per `BuildingMOTIF()`. Now `OntoEnv.connect(path, graph_store=...)`
for persistent and `OntoEnv(graph_store=..., temporary=True)` + `refresh_from_store(full=True)`
for temporary. Back to **57 warnings**, zero from ontoenv.

Not `adopt`, despite being the method the warning names: `adopt` is a deliberate first-time scan
that always persists an index, so it fits neither branch — the temporary case has nowhere to
persist, and the persistent case wants reuse rather than re-adoption on every open.

### Persistent `ontology_cache_path` is broken — pre-existing, now half-fixed

Found while testing the above. **This mode has never worked**, and the two failures differ:

| Tree | Result |
|---|---|
| `77be64e3` + a5 (old code) | `ValueError: graph_store cannot be combined with recreate or create_or_use_cached` — fails at construction |
| current + a8 | constructs and works, but leaves `.ontoenv/catalog.pending`; the **next** open raises `CatalogRecoveryError` |

The old code passed `graph_store` *and* `create_or_use_cached=True` together, which a5 rejects
outright — so nobody can ever have used a persistent ontology cache. The lifecycle refactor
fixed that hard failure and exposed the next one.

**The remaining defect looks like ontoenv's, not ours** — narrowed by bisecting the conditions:

- plain `OntoEnv(path=...)`, no custom store: no marker, closes and reopens fine
- add BuildingMOTIF's `graph_store`: marker appears *during operation* and survives `close()`
- `env.flush()` before `close()` does not clear it

`BuildingMOTIF.close()` does call `ontology_environment.close()`, so this is not a missing
close on our side. `CatalogRecoveryError` is exported by ontoenv but undocumented and has no
docstring, so the intended recovery path is unknown. **Repro for upstream: custom `graph_store`
+ persistent path leaves `catalog.pending` after a clean close.**

Only the temporary path (`path=None`) is exercised by the test suite, which is why this stayed
invisible: `ontology_cache_path` defaults to None.

#### Root cause found and worked around (merges #24, #25, a9)

**a9 does not fix it** — reproduced identically on a8 and a9. Traced by wrapping every
`OntoEnv` method and watching the marker file:

1. `import_dependencies` flips `.ontoenv/catalog.pending` from absent to present and never
   clears it.
2. Immediately after, `copy_graph` raises `ValueError: Failed to resolve graph for URI` **eight
   times** — `brickschema 1.3`, qudt `unit` and `quantitykind`, `ashrae/bacnet/2020`,
   `Brick/ref`, `rec/brickpatches`, `rec/recimports`, `datashapes/dash`. These are the imports
   Brick declares that do not resolve; several 404 even online. BuildingMOTIF tolerates missing
   imports and swallows them, so the load "succeeds" with the catalog left marked.
3. `BatchScope::run` (`ontoenv/lib/src/api.rs`) removes the marker **only** on `(Ok, Ok)`; every
   error path returns without removing it, and its `Drop` impl does not either.

Confirmed by contrast: an ontology declaring **no** imports leaves no marker. So loading Brick —
the most ordinary operation in BuildingMOTIF — poisons a persistent cache on first use.

`OntologyEnvironment._connect_recovering` now clears a found marker and retries once, warning
with the path. **It is a workaround and is labelled as one**: it trades away the marker's real
value after a genuine crash mid-write, which is why it warns rather than doing it silently and
retries only once. Verified: load Brick, close, reopen (warns, succeeds, ontology intact),
close, third open clean.

**Superseded — this describes the a8/a9 code, not the current tree.** ontoenv 0.6.0 fixed the
defect and `_connect_recovering` now calls `OntoEnv.recover` instead of touching the marker; see
"ontoenv 0.6.0 published and pinned" below. The rest of this subsection is kept as the record of
how the defect was traced.

**Delete `_connect_recovering` once ontoenv is fixed.** Three things to change upstream, in
priority order:

1. A tolerable non-strict import failure should not leave an interrupted-mutation marker.
   ontoenv's own changelog calls non-strict best-effort — "the partial union is returned with
   `failed_imports` populated so the caller knows what's missing" — but `BatchScope::run` treats
   that same condition as an interrupted mutation.
2. There is **no recovery API**. `CatalogRecoveryError` is exported, has no docstring, and
   appears nowhere in `llms.txt`. A consumer that hits it can only delete a file ontoenv owns.
3. `copy_graph` raising per-URI `ValueError` for unresolved imports means callers cannot
   distinguish "this import is missing" from a real failure without string-matching, which is
   why BuildingMOTIF swallows the exceptions blindly.

#### ontoenv 0.6.0 tried from a local wheel (2026-07-26) — **not pinned**

Tested from `/Users/gabe/src/ontoenv-rs/target/wheels/ontoenv-0.6.0-cp311-abi3-macosx_11_0_arm64.whl`.
**0.6.0 is not on PyPI**, so the pin stays at `0.6.0a9`: pinning it would break `uv lock` for
anyone without that wheel. Install it over the lock with
`uv pip install --reinstall <wheel>` and then use **`uv run --no-sync`** — a plain `uv run`
re-syncs and silently reverts to a9, which is easy to mistake for the wheel not working.

Full unit suite on 0.6.0: **535 passed, 1 skipped, 57 warnings** — identical to a9. Drop-in.

All three upstream requests above were addressed in 0.6.0, with two caveats found by re-running
the same traces:

| Request | 0.6.0 | Detail |
|---|---|---|
| recovery API | **works** | `OntoEnv.recover(path, graph_store=store)` rebuilds the catalog, keeps the ontology, clears the marker |
| no marker for non-strict imports | **not this path** | `import_dependencies` still flips `catalog.pending` and never clears it |
| typed unresolved-import error | **partial** | 5 of 8 raise `UnresolvedImportError`; 3 still raise plain `ValueError` |

The three still raising `ValueError` are `datashapes.org/dash`,
`brickschema.org/schema/1.3/Brick`, and `w3id.org/rec/brickpatches` — plausibly second-level
imports never directly attempted, so not "known" unresolved targets. From a consumer's seat all
eight are the same condition, so BuildingMOTIF still cannot catch a single type and must keep
catching `ValueError` broadly, which is what the new exception was meant to end.

**Second 0.6.0 wheel (rebuilt 16:06 the same day) closes both caveats.** Re-ran the identical
traces:

| Caveat | Second wheel |
|---|---|
| `import_dependencies` leaked the marker | **fixed** — trace reads `pending False->False`; no marker after load or close, and `_connect_recovering` never fires |
| `UnresolvedImportError` only 5 of 8 | **fixed** — all 8, including `datashapes.org/dash`, `brickschema.org/schema/1.3/Brick`, `w3id.org/rec/brickpatches` |

Persistent cache then survives repeated use: no marker after close, opens #2 and #3 both fine
with the ontology intact. Full unit suite on this wheel: **535 passed, 1 skipped, 57 warnings**,
zero failures — same as a9.

So the defect is fixed at the source and BuildingMOTIF no longer has to delete files ontoenv
owns.

**Third 0.6.0 wheel (2026-07-27 08:41)** — re-verified, everything holds:

```
copy_graph exceptions:  {'UnresolvedImportError': 8}
marker after close:     False
ontoenv deprecations:   none
open #2 OK, ontologies 1
open #3 OK, ontologies 1
```

Full unit suite: **535 passed, 1 skipped, 57 warnings**, zero failures. Checked specifically for
new deprecations, because the 0.6 migration guide adds one — `OntoEnv(...,
create_or_use_cached=True)` now warns in favour of `OntoEnv.connect(path)`. We moved to
`connect` back on a8, so that transition is already behind us.

**Open question for later, not a defect.** 0.6 makes `open`/`connect` distinguish an *omitted*
setting from an explicit `True`/`False`, and writable connections persist explicit overrides.
BuildingMOTIF always passes `offline` and `strict` explicitly from its own constructor defaults,
so a persisted value can never be preserved — the new preserve-on-omit behaviour is unreachable
through us. Defensible (BuildingMOTIF's constructor owns the setting), but if a cache should
remember its own `strict`, `BuildingMOTIF.__init__` needs `None` as "unset" and to stop
forwarding the flag when the caller did not ask for it.

**Two follow-ups queued for when 0.6.0 publishes**, blocked only on the pin (0.6.0 is still not
on PyPI as of this entry):

- **delete `_connect_recovering` outright** rather than rewriting it to call `recover()`. On this
  build the normal path leaves nothing to recover from, so the honest move is removing the
  workaround and letting a genuine `CatalogRecoveryError` surface, with `OntoEnv.recover(path,
  graph_store=...)` as the documented answer when it does. Keep it only while the pin is a9,
  where the leak is real.
- catch `UnresolvedImportError` where BuildingMOTIF currently swallows `ValueError` around
  library loading, now that all eight unresolved imports raise it. This is the one that stops a
  real error from being silently absorbed with the expected ones.

Two `test_libraries` failures reported from the same run
(`UNIQUE constraint failed: library.name` on `guideline36_5` and `nrel-templates2`) are **not
yet explained**. They pass standalone (17 passed) and in the full unit run (536 collected, 535
passed, 1 skipped), so the trigger is something about co-running with integration. Note the
`_N` suffixes are pytest disambiguating duplicate parameters — `pytest_generate_tests`
parametrises on `str(lib.parent)` once per `.yml`, and `guideline36/` holds 10 — **not**
directories of those names, which do not exist.

#### ontoenv 0.6.0 published and pinned (merge #26, 2026-07-27)

0.6.0 landed on PyPI, so the wheel testing above became the pin. `gtf-ontoenv` `c3185156`
(poetry `^0.6.0`, lock re-resolved), merged here as `40c5116d` with the constraint re-expressed
as `ontoenv>=0.6.0,<0.7.0` for uv. **A range, not an exact pin**: exactness was for the alphas;
0.6.0 is a published release with a migration guide and its `[Unreleased]` section already
carries fixes we want.

The published build reproduces the third wheel exactly. Re-ran the same trace against PyPI
0.6.0:

| Check | Result |
|---|---|
| `.ontoenv/catalog.pending` after a Brick load | **absent** — the cache-poisoning defect is fixed upstream |
| unresolved imports raising `UnresolvedImportError` | **6 of 6** on the Brick closure, none bare `ValueError` |
| opens #2 and #3 on the same persistent cache | clean, 18 ontologies each |
| ontoenv deprecation warnings | none |

Both queued follow-ups are now done, one of them **not as queued**:

- **`_connect_recovering` was rewritten, not deleted.** The queued plan was to remove it and let
  a genuine `CatalogRecoveryError` surface, with `OntoEnv.recover(path, graph_store=...)` as the
  consumer's answer. That answer is unreachable for our consumers: recovering a custom store
  requires passing that store, and `BuildingMOTIFGraphStore` does not exist until a
  `BuildingMOTIF` has been constructed — which is the thing that just failed. So the method now
  calls `OntoEnv.recover` on `CatalogRecoveryError` instead of unlinking the marker, which 0.6's
  docs explicitly warn against doing by hand. What the queued note actually wanted is gone
  either way: BuildingMOTIF no longer deletes a file ontoenv owns, and no longer papers over a
  routine unresolved import, because reaching that handler now means a real interrupted write.
  It warns, because recovery rescans every stored graph; ontoenv clears the marker only after
  publishing the replacement index, so a failed recovery still raises.

  Verified by planting the marker on a populated cache: warns, rebuilds, all 18 ontologies
  intact, marker cleared, subsequent open clean.
- **`ShapeCollection.infer_templates` catches `UnresolvedImportError`** instead of every
  `Exception` when collecting per-dependency graphs. A storage error or malformed IRI now
  propagates rather than being logged as a missing dependency and skipped. The exception is
  re-exported from `buildingmotif.ontology_environment` (via `__all__`) so ontoenv stays behind
  that seam — `shape_collection` imports it from us, not from `ontoenv`. The same method's
  broader `except Exception` around `import_dependencies` was left alone: that one is a
  deliberate fall-back-to-local-graph path, not an expected-error filter.

The `closure_names` benchmark in its docstring was re-measured on 0.6.0 (Brick 1.4 closure, 15
graphs, 155,536 triples, three reps): `list_closure` 0.000s flat, `copy_closure` 4.601/4.081/
3.849s, `get_closure` 2.435/2.418/2.479s. Same shape as a9, conclusion unchanged.

Still open, and still not a defect: BuildingMOTIF always forwards `offline` and `strict`
explicitly, so 0.6's preserve-on-omit behaviour for saved settings is unreachable through us.
See the note under the third-wheel entry above.

**Unit suite on the merge result (`40c5116d`): 535 passed, 1 skipped, 57 warnings** in 8m54s
under `uv run --with pytest-xdist pytest tests/unit -n auto`. Identical to a9 and to all three
0.6.0 wheels — same counts, same warning total, no new deprecations.

## Push status — test/perf fixes pushed (2026-07-29)

Two new remote branches, plus `gtf-buildingmotif`. All fast-forwards, no force-push.

| Branch | Range pushed | Now |
|---|---|---|
| `gtf-test-isolation` | new branch, `c02d82f3` (1 commit) | 0/0 |
| `gtf-matcher-perf` | new branch, `1b5e0f6e` (1 commit) | 0/0 |
| `gtf-buildingmotif` | `e510b024..01f7f689` (11 commits) | 0/0 |

**`gtf-new-pyshifty` was deliberately NOT pushed** — it is 2 ahead, and pushing it adds those
commits to the already-open **PR #399** before the maintainer has reviewed the text. Its two
commits (`fea28c85`, `3f011108`) are only on `origin` via the merge into `gtf-buildingmotif`,
which does not put them in the PR. Push it when #399's comment is signed off.

The local branch had **diverged from its own remote twice during this session** — first behind
2 (the `progressive_creation.py` sweep), then behind 2 again mid-push (`gtf-buildingmotif-skill`,
WaTr vocabulary reference) when the first push was rejected. Both merged cleanly; neither
touches anything in #27–#29. Fetch before assuming this branch is current: something else is
pushing to it.

## Push status — ontoenv 0.6.0 work pushed (2026-07-27)

Both branches touched by merge #26 are on `origin`, as plain fast-forwards. No force-push, no
new remote branch.

| Branch | Range pushed | Now |
|---|---|---|
| `gtf-ontoenv` | `6aa8377b..c3185156` (5 commits) | 0/0 |
| `gtf-buildingmotif` | `9eebfc13..40c5116d` (10 commits) | 0/0 |

**The 2026-07-25 table below was already stale, by more than this session's work.** It recorded
`gtf-ontoenv` at `d0084dea` and `gtf-buildingmotif` at `3935bedc` as pushed; `origin` was
actually holding `6aa8377b` and `9eebfc13`. So four commits on `gtf-ontoenv` (a8, the lifecycle
refactor, a9, the marker workaround) and merges #22–#25 here had never left this machine — they
were written after that entry and the entry was never revised. Nothing was lost, but "already
in sync" in a dated table is a claim about that date only. Re-check with
`git rev-list --left-right --count` rather than trusting it.

Consequence worth knowing: pushing `gtf-ontoenv` moved **PR #396** by five commits, including
the pin bump. The PR now proposes ontoenv 0.6.0 rather than 0.6.0a8.

## Push status — all branches backed up (2026-07-25)

Recorded because the merge table's commit hashes are meaningless to anyone who cannot fetch
them. `origin` is `git@github.com:NREL/BuildingMOTIF.git` — the shared upstream, which now
redirects to `NatLabRockies/BuildingMOTIF` (the push output names that repo, and the PR links
above already use it).

**Everything is now on `origin`.** Every branch below tracks its remote and is 0/0.
*Superseded — see the 2026-07-27 entry above; two of these rows were out of date.*

| Branch | Tip | Pushed |
|---|---|---|
| `gtf-buildingmotif` | `3935bedc` | 2026-07-25: FF `77be64e3..bf7584b8` (32 commits, merges #16–#18), then force-pushed for the trailer strip, then FF through merges #19–#21 |
| `gtf-api-cleanup` | `34967435` | 2026-07-25, **new remote branch** |
| `gtf-api-ergonomics` | `243e9d03` | 2026-07-25, **new remote branch**; force-pushed for the trailer strip, then FF to `243e9d03` |
| `gtf-buildingmotif-skill` | `73e68144` | 2026-07-25, **new remote branch** |
| `gtf-ontoenv` | `d0084dea` | already on `origin`; local tracking ref was missing, now set |
| `gtf-new-pyshifty` | `6d7bfad2` | already in sync |
| `gtf-uv` | `ad254f00` | already in sync |

The only force-pushes were the trailer strip (next section); the rest were three new branches
and fast-forwards. **No branch was deleted** — the four with open or pending PRs are still needed to
land on `develop`.

`gtf-ontoenv` was *not* actually local-only, contrary to an earlier draft of this table:
`origin/gtf-ontoenv` already matched the local tip exactly. Only the local `branch.*.merge`
config was missing, which made `git status` silent about it and `@{upstream}` fail — a
tracking-config gap, not a backup gap. Worth knowing because the same silence would look
identical if the work really were unpushed.

### Still no PR

`gtf-api-cleanup`, `gtf-api-ergonomics` and `gtf-buildingmotif-skill` are pushed but have **no
PR opened**. They are backed up, not proposed. The two API branches additionally cannot open
against `develop` until #396/#398/#399 land — see the intro and their branch notes.

## Maintaining this file

Update it whenever a branch is merged in, a PR is opened or lands, or a conflict is resolved
here. Record the merge commit, the branch tip that was merged, and **any resolution that does
not exist on a feature branch** — those are invisible in the PRs and are lost when this branch
is eventually rebuilt on a newer `develop`.

Also update the **Push status** table on any push, and the **Verification status** list on any
full-suite run. Both go stale silently and are the two things a reader is most likely to trust
without re-checking: one claims where the work is backed up, the other claims it works.
