# Manifests

A model's **manifest** is the set of libraries that model claims to satisfy. It is what
`model.validate()` and `model.compile()` check against when you give them nothing else,
which makes it the standing answer to "what is this model supposed to be?".

```python
model.manifest.add(brick, g36)           # Library objects, names, or iterables
model.manifest.remove(g36)
model.manifest.library_names             # ['https://brickschema.org/schema/1.4/Brick']
model.validate()                         # against exactly those libraries
```

## Why a set of libraries, and not a graph of shapes

Manifests used to be a shape collection you appended to:

```python
model.get_manifest().graph += my_shapes.graph      # no longer supported
```

Shapes arrived by being *copied in*, and that one fact caused the rest:

- **It could grow but not shrink.** Once a shape's triples were in the manifest graph,
  removing "the G36 requirements" meant finding and deleting the right triples. There was
  no name to subtract.
- **It could not say where anything came from.** Two shapes with the same URI, one from a
  library and one hand-written, were indistinguishable after the copy.
- **It went stale.** Re-loading a library with corrected shapes left the manifest holding
  the old copy.
- **It could only be inspected by reading triples.** "What is this model validated
  against?" had no cheap answer.

Naming libraries fixes all four at once. A manifest is now stored as an RDF graph
containing an `owl:Ontology` declaration and one `owl:imports` per member, and nothing
else:

```turtle
<urn:bldg/manifest> a owl:Ontology ;
    owl:imports <https://brickschema.org/schema/1.4/Brick> ;
    owl:imports <urn:my/site-requirements> .
```

`model.manifest.graph` hands you a copy of that graph to serialize or diff. Editing the
copy does nothing — the way to change a manifest is `add`/`remove`.

## Shapes get in by being a library

There is no back door for loose shapes, which is the point: a shape without a library has
no name for the manifest to hold. Writing the shapes into a graph with an `owl:Ontology`
declaration and loading it is the whole ceremony:

```python
shapes = rdflib.Graph().parse(data="""
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
<urn:my/site-requirements> a owl:Ontology .
<urn:my/site-requirements#ahu> a sh:NodeShape ; sh:targetClass brick:AHU .
""")
model.manifest.add(Library.from_ontology(shapes))
```

The library's name is the URI of that declaration, and that URI is what appears in the
manifest graph. A library loaded from a *directory* is named after the directory, which is
not a URI; those are carried in the graph under `urn:buildingmotif/library/<name>` and
mapped back when read, so they can be manifest members without inventing a URL for them.

## Adding a library you have not loaded

`add` takes names, not just `Library` objects, and resolves a name it does not recognize:

1. a library already in the database, then
2. an ontology the ontology environment already has cached — loaded as a library, no
   network, then
3. for an `http(s)` name, a fetch, if the active `BuildingMOTIF` permits fetching.

So `model.manifest.add("https://brickschema.org/schema/1.4/Brick")` works on a machine
that has never seen Brick. A name that resolves nowhere raises
`ManifestLibraryNotFound` **at `add` time** rather than at validation time, which is where
a typo would otherwise surface. To record an import deliberately before its library
exists, pass `resolve=False`; `model.validate(error_on_missing_imports=False)` then skips
what it cannot resolve instead of raising.

## What validation actually sees

`model.manifest.shape_collections()` is the list `validate()` and `compile()` use: the
shape collection of each member library, in name order. The manifest's own graph is *not*
in that list — it holds imports, not shapes. Each member's own `owl:imports` are resolved
as they always were, through OntoEnv, at validation time.

Passing shape collections explicitly still bypasses the manifest entirely:
`model.validate([sc1, sc2])` checks against exactly those. To validate against the
manifest *plus* extras, spread it in:

```python
model.validate([*model.manifest.shape_collections(), extra.get_shape_collection()])
```
