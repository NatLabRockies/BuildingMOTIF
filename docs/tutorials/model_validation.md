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

# Model Validation

```{margin}
```{important}
This tutorial assumes that `BuildingMOTIF` has already been installed in the local environment.
```

The purpose of this tutorial is to learn about model *validation* and how BuildingMOTIF can give useful feedback for fixing a model that has failed validation. 

```{note}
This tutorial has the following learning objectives:
1. validating the model against an ***ontology*** to ensure that the model is a valid Brick model
2. validating the model against a ***manifest***, which contains the metadata requirements for a specific model
3. validating the model against a ***use case*** for a specific application
```

```{margin}
```{note}
 `Shapes` are functions that validate part of an RDF model. A `Shape` is a set of constraints, requirements, and/or rules that apply to entities in an RDF graph. A shape may represent many things, including:
- the minimum points on an equipment required to execute a certain sequence of operations,
- the internal details of an equipment: what parts it contains, etc
```

Validating a model is the process of ensuring that the model is both *correct* (uses the ontologies correctly) and *semantically sufficient* (it contains sufficient metadata to execute the desired applications or enable the desired use cases). Validation is always done with respect to sets of `Shapes` using the Shapes Constraint Language (SHACL)[^1].

[^1]: https://www.w3.org/TR/shacl/

## Setup

We create an in-memory BuildingMOTIF instance, load the model from the previous tutorial, and load some libraries to create the manifest with.
The `constraints.ttl` library we load is a special library with some custom constraints defined that are helpful for writing manifests.

```{margin}
```{warning}
Currently, libraries in `../../buildingmotif/libraries/` are *included* and libraries in `../../libraries/` are *excluded* from the [BuildingMOTIF Python package](https://pypi.org/project/buildingmotif/) (available by cloning, downloading, or forking the repository). See https://github.com/NREL/BuildingMOTIF/issues/133. 
```

```{code-cell}
from rdflib import Namespace
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model, Library
from buildingmotif.namespaces import BRICK # import this to make writing URIs easier

# in-memory instance
bm = BuildingMOTIF("sqlite://")

# create the namespace for the building
BLDG = Namespace('urn:bldg/')

# create the building model
model = Model.create(BLDG, description="This is a test model for a simple building")

# load tutorial 1 model
model.graph.parse("tutorial1_model.ttl", format="ttl")

# load libraries included with the python package
constraints = Library.load(ontology_graph="../../buildingmotif/libraries/constraints/constraints.ttl")

# load libraries excluded from the python package (available from the repository)
brick = Library.load(ontology_graph="../../libraries/brick/Brick.ttl")
g36 = Library.load(directory="../../libraries/ashrae/guideline36")
```

## Model Validation - Ontology

BuildingMOTIF organizes Shapes into `Shape Collections`. The shape collection associated with a library (if there is one) can be retrieved with the `get_shape_collection` method. Below, we use Brick's shape collection to ensure that the model is using Brick correctly:

```{code-cell}
# pass a list of shape collections to .validate()
validation_result = model.validate([brick.get_shape_collection()])
print(f"Model is valid? {validation_result.valid}")
```

Success! The model is valid according to the Brick ontology.

## Model Validation - Manifest

### Writing a Manifest

```{margin}
```{note}
A `manifest` is an RDF graph with a set of `Shapes` inside, which place constraints and requirements on what metadata must be contained within a metadata model. 
```

For now, we will write a `manifest` file directly; in the future, BuildingMOTIF will contain features that make manifests easier to write.
Here is the header of a manifest file. This should also suffice for most of your own manifests.

```ttl
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix constraint: <https://nrel.gov/BuildingMOTIF/constraints#> .
@prefix : <urn:my_site_constraints/> .

: a owl:Ontology ;
    owl:imports <https://brickschema.org/schema/1.4/Brick>,
                <https://nrel.gov/BuildingMOTIF/constraints>,
                <urn:ashrae/g36> .
```

We will now add a constraint stating that the model should contain exactly 1 Brick AHU.

```ttl
:ahu-count a sh:NodeShape ;
    sh:message "need 1 AHU" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:AHU .
```

This basic structure can be changed to require different numbers of different Brick classes. Just don't forget to change the name of the shape (`:ahu-count`, above) when you copy-paste!

```{attention}
As an exercise, try writing shapes that require the model to contain the following.
- (1) Brick Supply_Fan
- (1) Brick Damper
- (1) Brick Cooling_Coil
- (1) Brick Heating_Coil
```

```{hint}
:class: dropdown

```ttl
:fan-count a sh:NodeShape ;
    sh:message "need 1 supply fan" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Supply_Fan .

:damper-count a sh:NodeShape ;
    sh:message "need 1 damper" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Damper .

:clg-coil-count a sh:NodeShape ;
    sh:message "need 1 cooling coil" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Cooling_Coil .

:htg-coil-count a sh:NodeShape ;
    sh:message "need 1 heating coil" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Heating_Coil .
```

<!-- We can now add a shape that requires *all* AHUs in the model to match the `sz-vav-ahu` system specification we find above:

```ttl
:sz-vav-ahu-control-sequences a sh:NodeShape ;
    sh:message "AHUs must match the single-zone VAV AHU shape" ;
    sh:targetClass brick:AHU ;
    sh:node <urn:ashrae/g36/4.8/sz-vav-ahu/sz-vav-ahu> .
``` -->

Put all of the above in a new file called `tutorial1_manifest.ttl`. We'll also add a shape called `sz-vav-ahu-control-sequences`, which is a use case shape to validate the model against in the next section.

The following block of code puts all of the above in the `tutorial1_manifest.ttl` file for you:

```{code-cell}
with open("tutorial1_manifest.ttl", "w") as f:
    f.write("""
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix constraint: <https://nrel.gov/BuildingMOTIF/constraints#> .
@prefix : <urn:my_site_constraints/> .

: a owl:Ontology ;
    owl:imports <https://brickschema.org/schema/1.4/Brick>,
                <https://nrel.gov/BuildingMOTIF/constraints>,
                <urn:ashrae/g36> .

:ahu-count a sh:NodeShape ;
    sh:message "need 1 AHU" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:AHU .

:fan-count a sh:NodeShape ;
    sh:message "need 1 supply fan" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Supply_Fan .

:damper-count a sh:NodeShape ;
    sh:message "need 1 damper" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Damper .

:clg-coil-count a sh:NodeShape ;
    sh:message "need 1 cooling coil" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Cooling_Coil .

:htg-coil-count a sh:NodeShape ;
    sh:message "need 1 heating coil" ;
    sh:targetNode : ;
    constraint:exactCount 1 ;
    constraint:class brick:Heating_Coil .

""")
```

### Adding the Manifest to the Model

We associate the manifest with our model so that BuildingMOTIF knows that we want validate the model against these specific shapes.
We can always update this manifest, or validate our model against other shapes; however, validating a model against its manifest is
the most common use case, so this is treated specially in BuildingMOTIF.


```{code-cell}
# load manifest into BuildingMOTIF as its own library!
manifest = Library.load(ontology_graph="tutorial1_manifest.ttl")
# set it as the manifest for the model
model.update_manifest(manifest.get_shape_collection())
```

### Validating the Model

We can now ask BuildingMOTIF to validate the model against the manifest and ask BuildingMOTIF for some details if it fails.
By default, BuildingMOTIF will include all shape collections imported by the manifest (`owl:imports`). BuildingMOTIF will
complain if the manifest requires ontologies that have not yet been loaded into BuildingMOTIF; this is why we are careful
to load in the Brick and Guideline36 libraries at the top of this tutorial.


```{code-cell}
validation_result = model.validate()
print(f"Model is valid? {validation_result.valid}")

# print reasons
for entity, errors in validation_result.diffset.items():
    print(entity)
    for err in errors:
        print(f" - {err.reason()}")
```

```{admonition} Tip on supplying extra shape collections
:class: dropdown

We can also provide a list of shape collections directly to `Model.validate`; BuildingMOTIF
will use these shape collections to validate the model *instead of* the manifest.

```python
# gather shape collections into a list for ease of use
shape_collections = [
    brick.get_shape_collection(),
    constraints.get_shape_collection(),
    manifest.get_shape_collection(),
    g36.get_shape_collection(),
]

# pass a list of shape collections to .validate()
validation_result = model.validate(shape_collections)
print(f"Model is valid? {validation_result.valid}")

# print reasons
for entity, errors in validation_result.diffset.items():
    print(entity)
    for err in errors:
        print(f" - {err.reason()}")
```

### Fixing the Model

One of the reasons the model is failing is we don't have a heating coil required by the manifest, which we forgot to add in the previous tutorial. It's also failing the use case validation, which we'll cover in the next section. To fix the manifest validation, use the equipment templates in the Brick library to create a heating coil, add it to the model, and connect it to the AHU using RDFLib's `graph.add()` method.

```{code-cell}
# ahu name
ahu_name = "Core_ZN-PSC_AC"

# get template
htg_coil_template = brick.get_template_by_name(BRICK.Heating_Coil)

# add htg coil
htg_coil_name = f"{ahu_name}-Htg_Coil"
htg_coil_binding = {"name": BLDG[htg_coil_name]}
htg_coil_graph = htg_coil_template.evaluate(htg_coil_binding)
model.add_graph(htg_coil_graph)

# connect htg coil
model.graph.add((BLDG[ahu_name], BRICK.hasPart, BLDG[htg_coil_name]))

# print model to confirm component was added and connected
print(model.graph.serialize())
```

We can see that the heating coil was added to the model and connected to the AHU so let's check if the manifest validation failure was fixed.

```{code-cell}
validation_result = model.validate()
print(f"Model is valid? {validation_result.valid}")

# print reasons
for entity, errors in validation_result.diffset.items():
    print(entity)
    for err in errors:
        print(f" - {err.reason()}")
```

Success! Our model is now valid.

## Model Validation - Use Case 

### Finding Use Case Shapes

We can use a couple methods to search the libraries for shapes we might want to use. Let's start by asking the `g36` library for any system specifications it knows about. This library represents *ASHRAE Guideline 36 High-Performance Sequences of Operation for HVAC Systems*[^2]. A system specification will specify all of the metadata required for an entity to run control sequences associated with that system type.

[^2]: https://www.ashrae.org/technical-resources/ashrae-standards-and-guidelines

```{code-cell}
from buildingmotif.namespaces import BMOTIF
shapes = g36.get_shape_collection()
for shape in shapes.get_shapes_of_definition_type(BMOTIF["System_Specification"]):
    print(shape)
```

The model represents the Small Office Commercial Prototype Building model, which has single zone packaged AHUs, so we're interested in validating it against Section 4.8 of Guideline 36 for single zone variable air volume (VAV) AHUs. 

Let's update our manifest to include the requirement that AHUs must match the "single zone AHU" shape from G36:

```{code-cell}
model.get_manifest().graph.parse(data="""
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix : <urn:my_site_constraints/> .
:sz-vav-ahu-control-sequences a sh:NodeShape ;
    sh:message "AHUs must match the single-zone VAV AHU shape" ;
    sh:targetClass brick:AHU ;
    sh:node <urn:ashrae/g36/4.8/sz-vav-ahu/sz-vav-ahu> .
""")
```


### Validating the Model

<!-- We can now borrow the same code from before and re-run it to re-validate the model:

```{code-cell}
# load manifest into BuildingMOTIF as its own library!
manifest = Library.load(ontology_graph="tutorial1_manifest.ttl")

# gather these into a list for ease of use
shape_collections = [
    brick.get_shape_collection(),
    constraints.get_shape_collection(),
    manifest.get_shape_collection(),
    g36.get_shape_collection(),
]

# pass a list of shape collections to .validate()
validation_result = model.validate(shape_collections)
print(f"Model is valid? {validation_result.valid}")
``` -->
Now we can run validation to see if our AHU is ready to run the "single zone AHU" control sequence:

```{code-cell}
validation_result = model.validate()
print(f"Model is valid? {validation_result.valid}")
```

The AHU fails validation because it doesn't match the `sz-vav-ahu-control-sequences` requirements.
Take a look at the first bit of output, which is the official SHACL validation report text format. This can be difficult to interpret without a background in SHACL, so BuildingMOTIF provides a more easily understood version of the same information.

```{code-cell}
# SHACL validation report
print(validation_result.report_string)

# separator
print("-"*79)
```

Here is BuildingMOTIF's interpretation of that report.

```{code-cell}
# BuildingMOTIF output
print("Model is invalid for these reasons:")
for entity, errors in validation_result.diffset.items():
    print(entity)
    for err in errors:
        print(f" - {err.reason()}")
```

The model is failing because the AHU doesn't have the required points. We could find those templates manually, evaluate them, and add the resulting graphs to the model. However, this can be a bit
tedious. To address this issue, BuildingMOTIF can find those templates automatically for us. We'll cover this feature in the next tutorial so let's save the model.

```{code-cell}
#save model
model.graph.serialize(destination="tutorial2_model.ttl")
```
