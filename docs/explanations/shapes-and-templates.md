---
jupytext:
  cell_metadata_filter: -all
  formats: md:myst
  text_representation:
    extension: .md
    format_name: myst
kernelspec:
  display_name: Python 3
  language: python
  name: python3
---

# Shapes and Templates

Shapes and Templates interact in interesting ways in BuildingMOTIF.
In this document, we explain the utility and function of these interactions.

Recall that a **Shape** (SHACL shape) is a set of conditions and constraints over RDF graphs, and
a **Template** is a function that generates an RDF graph.

## Converting Shapes to Templates

### When Loading a Library

BuildingMOTIF can automatically convert shapes to templates when loading a Library.
Evaluating the resulting template will generate a graph that validates against the shape.

When BuildingMOTIF loads a Library, it makes an attempt to find any shapes defined within it.
The way this happens depends on how the library is loaded:
- *Loading library from directory or git repository*: BuildingMOTIF searches for any RDF files in the directory (recursively) and loads them into a Shape Collection; loads any instances of `sh:NodeShape` in the union of these RDF files
- *Loading library from ontology file*: loads all instances of `sh:NodeShape` in the provided graphc

```{important}
BuildingMOTIF *only* loads shapes which are instances of *both* `sh:NodeShape` **and** `owl:Class`. The assumption is that `owl:Class`-ified shapes could be "instantiated".
```

Each shape is "decompiled" into components from which a Template can be constructed.
The implementation of this decompilation is in the [`get_template_parts_from_shape`](/reference/apidoc/_autosummary/buildingmotif.utils.html#buildingmotif.utils.get_template_parts_from_shape) method.
BuildingMOTIF currently recognizes the following SHACL properties:
- `sh:property`
- `sh:qualifiedValueShape`
- `sh:node`
- `sh:class`
- `sh:targetClass`
- `sh:datatype`
- `sh:minCount` / `sh:qualifiedMinCount`
- `sh:maxCount` / `sh:qualifiedMaxCount`

BuildingMOTIF currently uses the name of the SHACL shape as the name of the generated Template.
All other parameters (i.e., nodes corresponding to `sh:property`) are given invented names *unless*
 there is a `sh:name` attribute on the property shape.

This feature can be disabled by setting `infer_templates=False` when calling `Library.from_ontology`/`Library.from_directory`

### From Shape Collections

It is also possible to convert the shapes defined in a Shape Collection to templates.
This is done by calling the `infer_templates` method on the Shape Collection.
If `infer_templates` is True when loading a library, then BuildingMOTIF will automatically call `infer_templates` on the Shape Collection
within that Library.

Being able to call `infer_templates` on a Shape Collection is useful when you have
a graph of shapes that you programmatically created or loaded without packaging them
in a Library.

```{code-cell} python3
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, ShapeCollection

# in-memory instance
bm = BuildingMOTIF("sqlite://")

my_shapes_source = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix ex: <http://example.org/> .

ex:SimpleShape a sh:NodeShape, owl:Class ;
    sh:property [
        sh:path ex:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Sensor ] ;
        sh:qualifiedMinCount 1 ;
    ] .
"""

# create a ShapeCollection to hold the shapes
my_shapes = ShapeCollection.create()
my_shapes.graph.parse(data=my_shapes_source, format="ttl")

# create a Library to hold the generated templates
lib = Library.create("my-library")
my_shapes.infer_templates(lib)

print(lib.get_templates())
```

### Example

Consider the following shape which has been loaded into BuildingMOTIF as part of a Library:

```ttl
# myshapes.ttl
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix : <urn:example/> .

: a owl:Ontology .

:vav a sh:NodeShape, owl:Class ;
    sh:targetClass brick:Terminal_Unit ;
    sh:property [
        sh:path brick:hasPart ;
        sh:qualifiedValueShape [ sh:node :heating-coil ] ;
        sh:name "hc" ;
        sh:qualifiedMinCount 1 ;
    ] ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Supply_Air_Flow_Sensor ] ;
        sh:qualifiedMinCount 1 ;
    ] ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Supply_Air_Temperature_Sensor ] ;
        sh:name "sat" ;
        sh:qualifiedMinCount 1 ;
    ] ;
.

:heating-coil a sh:NodeShape, owl:Class ;
    sh:targetClass brick:Heating_Coil ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Position_Command ] ;
        sh:name "damper_pos" ; # will be used as the parameter name
        sh:qualifiedMinCount 1 ;
    ] ;
.
```

<details>

This code creates `myshapes.ttl` for you in the current directory.

```{code-cell} python3
with open("myshapes.ttl", "w") as f:
    f.write("""
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix : <urn:example/> .

: a owl:Ontology .

:vav a sh:NodeShape, owl:Class ;
    sh:targetClass brick:Terminal_Unit ;
    sh:property [
        sh:path brick:hasPart ;
        sh:qualifiedValueShape [ sh:node :heating-coil ] ;
        sh:name "hc" ;
        sh:qualifiedMinCount 1 ;
    ] ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Supply_Air_Flow_Sensor ] ;
        sh:qualifiedMinCount 1 ;
    ] ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Supply_Air_Temperature_Sensor ] ;
        sh:name "sat" ;
        sh:qualifiedMinCount 1 ;
    ] ;
.

:heating-coil a sh:NodeShape, owl:Class ;
    sh:targetClass brick:Heating_Coil ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:class brick:Position_Command ] ;
        sh:name "damper_pos" ; # will be used as the parameter name
        sh:qualifiedMinCount 1 ;
    ] ;
.
""")
```

</details>

If this was in a file `myshapes.ttl`, we would load it into BuildingMOTIF as follows:

```{code-cell} python3
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library

# in-memory instance
bm = BuildingMOTIF("sqlite://")

# load library
brick = Library.from_ontology("https://github.com/BrickSchema/Brick/releases/download/nightly/Brick.ttl")
lib = Library.from_ontology("myshapes.ttl")
```

Once the library has been loaded, all of the shapes have been turned into templates.
We can load the template by name (using its *full URI* from the shape) as if it were
defined explicitly:

```{code-cell} python3
# reading the template out by name
template = lib.get_template_by_name("urn:example/vav")

# dump the body of the template
print(template.body.serialize())
```

As with other templates, we often want to *inline* all dependencies to get a sense of what metadata will be added to the graph.

```{code-cell} python3
# reading the template out by name
template = lib.get_template_by_name("urn:example/vav").inline_dependencies()

# dump the body of the template
print(template.body.serialize())
```

Observe that the generated template uses the `sh:name` property of each property shape to inform the paramter name. If this is not provided (e.g. for the `brick:Supply_Air_Flow_Sensor` property shape), then a generated parameter will be used.
