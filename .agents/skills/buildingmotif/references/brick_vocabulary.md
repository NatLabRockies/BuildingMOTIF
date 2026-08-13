# Brick vocabulary discovery

## Contents

- [Confirm a candidate class](#confirm-a-candidate-class)
- [Search Brick classes by words](#search-brick-classes-by-words)
- [List point classes by family](#list-point-classes-by-family)
- [Find subclasses](#find-subclasses-of-a-broad-class)
- [Inspect a class shape](#inspect-a-class-shape)
- [Use templates as a vocabulary index](#templates-are-another-vocabulary-index)
- [Output](#output-to-produce-for-the-user)

For a quick namespace-preserving probe, run `scripts/inspect_ontology.py` from the skill
directory against `brick/Brick.ttl`. A local name such as `AHU` can match both a Brick class
and a BrickTag individual; retain and evaluate the complete returned IRI.

When building or repairing a model, do not guess Brick class names. The recurring task is
to translate building language (`DMPR COMD`, `Run Status`, `Duct Static Pressure SP`) into
actual Brick IRIs before asserting `a brick:X` or binding a template parameter.

This is the first step for any source-to-model workflow: point lists, BACnet object names,
equipment schedules, submittals, and existing metadata all need their source vocabulary
mapped to verified Brick classes before you emit triples.

Load Brick once and query the graph. Use the canonical packaged ontology and disable SHACL
inference so BuildingMOTIF also exposes Brick class templates:

```python
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library
from buildingmotif.namespaces import BRICK, RDF, RDFS, OWL, SH, SKOS

bm = BuildingMOTIF("sqlite://")   # tables are created automatically

# Builtin Brick. `run_shacl_inference=False` is the recipe that creates class templates.
brick = Library.from_ontology("brick/Brick.ttl", run_shacl_inference=False)
brick_graph = brick.get_shape_collection().graph
```

## Confirm a candidate class

Before adding a type triple, test the candidate — and check deprecation in the same pass.
Brick marks retired classes with `owl:deprecated true` and points at the replacement with
`brick:isReplacedBy`, plus a human-readable `brick:deprecationMitigationMessage` (199
`brick:`-namespaced classes carry these in the packaged ontology, 198 of them with a
replacement — e.g. `brick:Auditorium` is deprecated `brick:isReplacedBy rec:Auditorium`,
"Brick location classes are being phased out in favor of RealEstateCore classes"; the
reverse also happens — older `rec:` ICT classes deprecated in favor of newer `brick:`
equivalents. **Check every candidate, don't assume a direction.**

```python
def brick_class(local_name: str):
    cls = BRICK[local_name]
    is_class = (
        (cls, RDF.type, OWL.Class) in brick_graph
        or (cls, RDF.type, SH.NodeShape) in brick_graph
    )
    if not is_class:
        return None
    deprecated = next(brick_graph.objects(cls, OWL.deprecated), None)
    if deprecated is not None and deprecated.toPython():
        replacement = next(brick_graph.objects(cls, BRICK.isReplacedBy), None)
        message = next(brick_graph.objects(cls, BRICK.deprecationMitigationMessage), None)
        print(f"WARNING: {local_name} is deprecated. {message}")
        return replacement or cls  # prefer the replacement over asserting the deprecated class
    return cls

for name in [
    "Run_Status",
    "Run_Status_Sensor",
    "Duct_Air_Static_Pressure_Setpoint",
]:
    print(name, bool(brick_class(name)))
```

**Always prefer the non-deprecated class.** If `brick_class(...)` finds a match but it's
deprecated, don't assert it just because the name matched what the user said — follow
`isReplacedBy` to the current class and use that instead, and mention the substitution when
you report the mapping (see "Output to produce for the user" below).

If this returns `False`, do not assert that class. Search for the real one instead. This
is how you catch errors like assuming `brick:Run_Status_Sensor` exists when Brick has
`brick:Run_Status`.

For bulk mapping work, fail fast over the whole table:

```python
source_to_brick = {
    "RoomTmp": "Room_Temperature_Sensor",
    "Fan_Status": "Run_Status",
    "SaTmp": "Supply_Air_Temperature_Sensor",
}

missing = {
    token: local
    for token, local in source_to_brick.items()
    if brick_class(local) is None
}
if missing:
    raise ValueError(f"Unknown Brick classes: {missing}")
```

## Search Brick classes by words

Use word search over local names, labels, comments, and definitions. This is usually
faster than trying several guessed class names.

```python
def search_brick_classes(*words: str, limit: int = 50):
    wanted = [w.lower().replace("_", " ") for w in words]
    nodes = set(brick_graph.subjects(RDF.type, OWL.Class))
    nodes |= set(brick_graph.subjects(RDF.type, SH.NodeShape))
    hits = []
    for cls in nodes:
        if not str(cls).startswith(str(BRICK)):
            continue
        local = str(cls).split("#")[-1]
        fields = [local.replace("_", " ")]
        fields += [str(o) for o in brick_graph.objects(cls, RDFS.label)]
        fields += [str(o) for o in brick_graph.objects(cls, RDFS.comment)]
        fields += [str(o) for o in brick_graph.objects(cls, SKOS.definition)]
        haystack = " ".join(fields).lower()
        if all(w in haystack for w in wanted):
            hits.append(local)
    return sorted(hits)[:limit]

print(search_brick_classes("duct", "static", "pressure", "setpoint"))
print(search_brick_classes("steam"))
print(search_brick_classes("damper", "command"))
```

Search broadly, then verify the exact candidate with `brick_class(...)`.

Use several searches before settling on a class. Brick names often include the medium or
context (`Duct_Air_Static_Pressure_Setpoint`, `Zone_Air_Temperature_Sensor`), and some
plain-English guesses are wrong (`Packaged_Heat_Pump`, not always `Heat_Pump`;
`Steam_Usage_Sensor`, not `Steam_Flow_Sensor`).

## List point classes by family

For point-list work, the useful slice is usually all subclasses/local names containing
`Sensor`, `Setpoint`, `Command`, or `Status`:

```python
for kind in ["Sensor", "Setpoint", "Command", "Status"]:
    names = search_brick_classes(kind, limit=500)
    print(f"\n{kind} ({len(names)})")
    for name in names[:80]:
        print(" ", name)
```

Use this to build the project-specific abbreviation table. Prefer the most specific class
supported by evidence: `Zone_Air_Temperature_Sensor` beats `Temperature_Sensor` when the
label/units/context say it is zone air temperature.

## Find subclasses of a broad class

When a shape asks for a broad class, search its subclasses and choose the most specific
one the evidence supports:

```python
def subclasses_of(local_name: str, limit: int = 100):
    root = BRICK[local_name]
    q = """
    SELECT DISTINCT ?cls WHERE {
      ?cls rdfs:subClassOf+ ?root .
      FILTER(STRSTARTS(STR(?cls), STR(brick:)))
    }
    ORDER BY ?cls
    """
    rows = [
        str(row.cls).split("#")[-1]
        for row in brick_graph.query(
            q,
            initNs={"brick": BRICK, "rdfs": RDFS},
            initBindings={"root": root},
        )
    ]
    return rows[:limit]

print(subclasses_of("Temperature_Sensor", limit=40))
print(subclasses_of("Setpoint", limit=40))
```

The important part is `rdfs:subClassOf+`: it walks the class hierarchy instead of relying
on local-name search alone.

## Inspect a class shape

When validation says a class needs or forbids a property, inspect the class's SHACL
property shapes directly:

```python
def describe_shape(local_name: str):
    cls = BRICK[local_name]
    for ps in brick_graph.objects(cls, SH.property):
        path = next(brick_graph.objects(ps, SH.path), None)
        klass = next(brick_graph.objects(ps, SH["class"]), None)
        node = next(brick_graph.objects(ps, SH.node), None)
        qvs = next(brick_graph.objects(ps, SH.qualifiedValueShape), None)
        min_count = next(brick_graph.objects(ps, SH.minCount), None)
        max_count = next(brick_graph.objects(ps, SH.maxCount), None)
        qmin = next(brick_graph.objects(ps, SH.qualifiedMinCount), None)
        qmax = next(brick_graph.objects(ps, SH.qualifiedMaxCount), None)
        print({
            "path": path,
            "class": klass,
            "node": node,
            "qualifiedValueShape": qvs,
            "min": min_count or qmin,
            "max": max_count or qmax,
        })

describe_shape("Lighting_System")
```

If a validation failure names `rec:locatedIn`, assert `rec:locatedIn` directly unless you
are intentionally running inference. SHACL path checks do not automatically follow
`owl:equivalentProperty` from `brick:hasLocation`.

## Templates are another vocabulary index

Brick class templates are created from classes when Brick is loaded with
`run_shacl_inference=False`:

```python
templates = {str(t.name).split("#")[-1]: t for t in brick.get_templates()}
for name in sorted(n for n in templates if "Temperature" in n and "Sensor" in n)[:50]:
    print(name, sorted(templates[name].parameters))
```

If a downstream library raises `TemplateNotFound` for a Brick class, the usual fix is to
load Brick first with the canonical `brick/Brick.ttl` recipe. Do not edit the library
until you have verified the class exists and Brick was loaded correctly.

## Output to produce for the user

For source mapping work, report the vocabulary decisions explicitly:

- verified class mappings, e.g. "`RoomTmp` -> `brick:Room_Temperature_Sensor`";
- rejected guesses, e.g. "`brick:Run_Status_Sensor` does not exist; using
  `brick:Run_Status`";
- unresolved tokens that need evidence or user confirmation.

Do not hide unknown source tokens behind generic classes unless the user explicitly wants a
coarse model. Unknowns are usually where the building-specific meaning lives.
