# Using BuildingMOTIF with an AI coding agent

BuildingMOTIF ships an **agent skill** — a small, text-based bundle that teaches an AI
coding agent how to drive BuildingMOTIF's validate/repair/build APIs correctly, without
the agent having to rediscover the load order, gotchas, and workflow by trial and error.
It works with Claude Code, Codex, and in principle any other coding agent — see "Using it
with different agents" below for what that takes in practice.

## What's in the skill

The skill lives at [`.agents/skills/buildingmotif/`](https://github.com/NatLabRockies/BuildingMOTIF/tree/gtf-buildingmotif/.agents/skills/buildingmotif)
in the repository:

```
.agents/skills/buildingmotif/
├── SKILL.md                        # entry point: when to use this, workflow router, setup
└── references/
    ├── brick_vocabulary.md         # verify Brick class names before asserting `a brick:X`
    ├── building_models.md          # Model.create + TemplateBuilderContext + evidence
    ├── evidence.md                 # finding evidence in point lists / submittals / BACnet
    ├── ontology_imports.md         # OntoEnv, owl:imports resolution, offline/cache knobs
    ├── point_labels.md             # point lists, BMS labels, BACnet names -> Brick classes
    ├── repair.md                   # propose/apply repairs, gap -> evidence -> user -> apply
    ├── templates.md                # find/evaluate/fill templates
    ├── validation.md               # validate a model, read failures in building terms
    ├── writing_shapes.md           # SHACL shapes, `bmotif:` constraint vocabulary
    └── writing_templates.md        # YAML template bodies, dependencies, decompiling shapes
```

`SKILL.md`'s frontmatter (`name` + `description`) is what an agent uses to decide *when*
to load the skill — e.g. "the user mentioned Brick, SHACL validation, repair, pointlists,
or asked whether a model is sufficient for an application." The body is the router: it
sends the agent to the right reference file instead of dumping everything into context at
once, and it states the one rule that matters most — **never invent metadata**. A
soundness-gated repair is guaranteed not to introduce a new SHACL violation; it is not
guaranteed to be *true of the building*. The skill enforces gap → evidence → user → apply
as the only acceptable loop.

## Getting the skill files

There are two separate installs here, and it's worth being precise about which is which:

- **The skill's own files** — `SKILL.md` + `references/*.md`, a dozen markdown files
  totaling well under 1MB — have to come from the repository. They aren't published
  anywhere else yet (see "Packaging" below).
- **The `buildingmotif` Python package** the skill teaches an agent to `import` is a
  normal install and does **not** need a checkout at all — see `SKILL.md`'s
  "Installation" section (`uv add "buildingmotif @ git+https://github.com/NatLabRockies/BuildingMOTIF.git@gtf-buildingmotif"`,
  ahead of what's published on PyPI).

`SKILL.md`'s "not run from a checkout" line is about the second one, not the first — the
markdown files obviously have to exist on disk somewhere before an agent can read them.
What it rules out is writing `import buildingmotif` scripts that only work inside a
repository working tree; it says nothing about how the skill files themselves got there.

You don't need a full clone of this repository (tens of MB, most of it Brick/QUDT/223P
ontology files and history the skill doesn't need) just to get twelve markdown files. Two
ways to grab only `.agents/skills/buildingmotif/`:

**Sparse, blobless clone (recommended — plain `git`, and `git pull` keeps it updated):**

```bash
git clone --filter=blob:none --sparse --branch gtf-buildingmotif --depth 1 \
  https://github.com/NatLabRockies/BuildingMOTIF.git buildingmotif-skill-src
cd buildingmotif-skill-src
git sparse-checkout set .agents/skills/buildingmotif
```

`--filter=blob:none` skips downloading file contents up front; `--sparse` + the
`sparse-checkout set` call then materializes (and fetches blobs for) only the one
directory. In practice this pulls well under 1MB, not the full repository.

**Tarball, no `git` required:**

```bash
curl -L https://github.com/NatLabRockies/BuildingMOTIF/archive/refs/heads/gtf-buildingmotif.tar.gz \
  | tar -xz --strip-components=1 --include '*/.agents/skills/buildingmotif/*'
```

(GitHub's `--include` extraction filter is BSD-tar syntax, the macOS/`tar` default; on
GNU `tar` the equivalent is `--wildcards '*/.agents/skills/buildingmotif/*'`.) This still
downloads the full repository as a compressed tarball before filtering — a few MB, not
the full git history — so it's the fallback for environments without `git`, not the
default.

Either way, copy (or symlink) the resulting `.agents/skills/buildingmotif/` into wherever
your agent tool discovers skills — see "Using it with different agents" below.

### Packaging (not done yet)

Neither of the above is as good as a one-line `curl | tar` with no path-guessing and no
knowledge of which branch is current. The natural fix is to publish the skill directory as
its own downloadable artifact — a zip/tarball attached to a GitHub release (the same
pattern already used for Brick's `nightly` release assets), or a thin standalone repo kept
in sync via `git subtree split`. That doesn't exist yet; the instructions above are the
current best option, not the intended long-term one.

## Using it with different agents

`SKILL.md` — frontmatter naming/describing the skill, then a markdown body — is a plain
text convention, not tied to one tool:

- **Claude Code** discovers skills placed under a project's (or user's) `skills/`
  directory automatically, using the frontmatter `description` to decide when to load
  one, and invokes it explicitly with `/skill:buildingmotif ...`.
- **Codex, or any other coding agent**, whether or not it has native `SKILL.md`
  auto-discovery: point it at `SKILL.md` directly — e.g. reference it from the agent's own
  instructions file (`AGENTS.md` or equivalent), or just tell the agent in-session to read
  `.agents/skills/buildingmotif/SKILL.md` and follow it. The frontmatter/router format
  degrades gracefully to plain instructions even without special tooling support; the
  workflow router at the top of `SKILL.md` is what tells the agent which `references/*.md`
  file to open next, which matters more than how it got loaded in the first place.

Either way, the model/shape files you point the agent at are yours — the skill's own setup
(in-memory `BuildingMOTIF`, `pyshifty` as the default SHACL engine) is what the agent runs
first, per `SKILL.md`'s "Setup" section.

## Example usage

### Validate and repair a model

```
/skill:buildingmotif validate @bldg39.ttl against Brick. if it is not valid,
repair it so it passes validation.
```

The agent loads Brick, validates `bldg39.ttl`, and reports failures in building terms
(e.g. "38 pieces of equipment are missing `rec:locatedIn`", "a chiller has 3 points typed
incorrectly") rather than raw SHACL output. It then repairs one witness at a time —
relinking a mistyped point, adding a missing `hasPoint` relationship, retyping a
misclassified point — re-validating after each change, and stops once the model
conforms, reporting a summary of what changed (triples added/removed, before/after
violation counts) so it can be reviewed against the source evidence.

### Build a model from a point list

```
/skill:buildingmotif create a Brick model from the point list in bacnetdump.csv
```

The agent works out a parsing scheme for the point naming convention, then — rather than
guessing — asks clarifying questions with concrete, evidence-backed options when the
mapping is ambiguous. For example, given room-prefixed points that look like a VAV
terminal (`Zone Air Temp`, `CTL STPT`, `DMPR COMD`, `VLV COMD`), it might offer:

1. **VAV w/ reheat** (recommended) — `brick:Variable_Air_Volume_Box_With_Reheat`; the
   damper + reheat-valve command combination best matches this.
2. **VAV cooling-only** — `brick:Variable_Air_Volume_Box`, if the valve is a cooling coil
   rather than reheat.
3. **Generic terminal unit** — `brick:Terminal_Unit`, a conservative choice that commits
   to a terminal unit without asserting VAV/reheat specifics.
4. **Location only** — model the room as a `brick:Zone` and attach points to it, with no
   terminal-unit equipment asserted.

Once the mapping is resolved, it generates the Brick model plus a re-runnable build
script and class-verification scripts, so the mapping decisions are reproducible and
auditable rather than a one-off, opaque transformation.

## Why this works

A few properties of BuildingMOTIF's validate/repair loop make it a good fit for an
agentic workflow rather than a one-shot script:

- **Validation reports are structured, not just pass/fail.** With the `pyshifty` engine,
  a failing check comes with a `RepairWitness` — the reason it failed, in terms of the
  shape and the missing statement — and a `repair_tree` enumerating the possible edits
  that would fix it. That's a natural prompt for an agent: "here are N sound ways to fix
  this, pick the one that matches the evidence," not "here is an opaque violation, figure
  out something plausible."
- **The smallest fix is not always the correct one.** Enumerating multiple
  soundness-gated proposals (synthesize a new node, reuse an existing one, apply a
  template) and letting the agent choose based on context — the evidence in front of it —
  is exactly the judgment call a fixed algorithm can't make but an LLM, with the right
  evidence, can.
- **The workflow is iterative by construction.** Fixing one failure surfaces the next
  (adding a fan gives it its own point requirements), so BuildingMOTIF's own tutorials and
  notebooks already teach a validate → fix → re-validate loop. That loop is a natural fit
  for an agent that reflects on partial results between steps, which is why the skill
  insists on repairing one witness at a time instead of batching.

See `references/repair.md` and `references/validation.md` in the skill itself for the
APIs (`ctx.witnesses`, `witness.repair_tree.explain()`, `witness.proposals()`) behind
this.
