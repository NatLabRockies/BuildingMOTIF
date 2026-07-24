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

# Model Creation

```{margin}
```{important}
This tutorial assumes that `BuildingMOTIF` has already been installed in the local environment.
```

The purpose of this tutorial is to learn about a few of the basic features of BuildingMOTIF by creating a Brick model similar to the Small Office Commercial Prototype Building model[^1]. It assumes that the reader has some familiarity with the Turtle syntax[^2] for Resource Description Framework (RDF) graphs[^3].

```{note}
This tutorial has the following learning objectives:
1. creating a BuildingMOTIF model *instance* and `Model`
2. loading `Libraries` into a BuildingMOTIF instance
3. adding to a model by *evaluating* `Templates`
```

[^1]: https://www.energycodes.gov/prototype-building-models#Commercial
[^2]: https://www.w3.org/TR/turtle/
[^3]: https://www.w3.org/RDF/

## Creating a Model

BuildingMOTIF needs a database to store models, libraries, templates, ontologies, and other data. This database can be *in-memory* (which will be deleted when the process ends) or *persistent*. For simplicity, we will start with an in-memory database where `bm` represents a BuildingMOTIF instance.

```{code-cell}
from buildingmotif import BuildingMOTIF
bm = BuildingMOTIF("sqlite://") # in-memory instance
```

Any missing tables are created for you, whether the database is in-memory or on disk, so there is nothing else to set up.

```{margin}
```{note}
If your schema is managed out of band -- for example by the Alembic migrations in the repository's `migrations/` directory -- pass `create_tables=False` so BuildingMOTIF never touches it.
```

### Persisting your work

For a *persistent* database, pass a file or Postgres URI instead. BuildingMOTIF spans two stores: RDF triples are written through to the graph store immediately, but the rows that point at them live in SQL and are only durable once the session is committed. Using the instance as a context manager handles that for you -- it commits when the block ends normally, rolls back if an exception escapes, and closes the instance either way:

```python
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model

with BuildingMOTIF("sqlite:///my_building.db") as bm:
    model = Model.create("urn:bldg/")
    model.add_graph(my_graph)
# committed and closed here
```

Without the context manager you are responsible for calling `bm.session.commit()` yourself before the process ends, otherwise the triples you wrote will be on disk with no model referencing them.

```{margin}
```{note}
A `Model` is an RDF graph representing part or all of a building.
```

Now that we have a BuildingMOTIF instance, we can create a `Model`. Creating a model requires importing the `Model` class, creating an RDF namespace to hold all of the entities in the model, and telling BuildingMOTIF to create a new model with that namespace. The namespace is a URL used to uniquely identify the model.

```{code-cell}
from rdflib import Namespace, RDF
from buildingmotif.dataclasses import Model

# create the namespace
BLDG = Namespace('urn:bldg/')

# Create the model! This will raise an exception if the namespace is not syntactically valid.
model = Model.create(BLDG, description="This is a test model for a simple building") 
```

We can print out the contents of the model by accessing the `.graph` property of the model object. Printing this out reveals that BuildingMOTIF has added a couple annotations to the model for us, but there is otherwise no metadata about the building itself:

```{code-cell}
print(model.graph.serialize())
```

The `model.graph` object is just the RDFLib Graph[^4] that stores the model. You can interact with the graph by adding triples with `model.graph.add((subject, predicate, object))` but as we will soon see, BuildingMOTIF can automate some of that!

[^4]: https://rdflib.readthedocs.io/

## Loading Libraries

```{margin}
```{note}
`Libraries` are collections of Templates and Shapes.
```

Before we can add semantic metadata to the model, we need to import some `Libraries`. We import libraries by calling `Library.load` in BuildingMOTIF. Libraries can be loaded from directories containing `.yml` and `.ttl` files (for Templates and Shapes, respectively), or from ontology files directly. The code below contains an example of importing the `brick` library, which is simply the Brick ontology. This allows BuildingMOTIF to take advantage of the classes and relationships defined by Brick when validating the model. Loading in these definitions also allows other libraries to refer to Brick definitions. You can also ask a library for the names of the templates it defines, which we'll limit to the first ten below.

```{margin}
```{warning}
Currently, libraries in `../../buildingmotif/libraries/` are *included* and libraries in `../../libraries/` are *excluded* from the [BuildingMOTIF Python package](https://pypi.org/project/buildingmotif/) (available by cloning, downloading, or forking the repository). See https://github.com/NREL/BuildingMOTIF/issues/133. 
```

```{code-cell}
# load a library
from buildingmotif.dataclasses import Library
brick = Library.load(ontology_graph="../../libraries/brick/Brick-subset.ttl")

# print the first 10 templates
print("The Brick library contains the following templates:")
for template in brick.get_templates()[:10]:
    print(f"  - {template.name}")
```

## Adding to a Model Manually

Because `Model`s are wrappers around RDF graphs, it is possible to manipulate those RDF graphs directly.
BuildingMOTIF supports adding *individual triples* to models as well as *adding whole graphs* to models.

The RDF graph underlying a `Model` is accessible via the `.graph` attribute. This is an instance of [`RDFlib.Graph`](https://rdflib.readthedocs.io/en/stable/intro_to_graphs.html).

### Adding Individual RDF Triples to a Model

To add an RDF triple to a model, use the `Model.graph.add()` method:

```{code-cell}
# import this to make writing URIs easier
from buildingmotif.namespaces import BRICK, RDF

model.graph.add((BLDG["zone-temp"], RDF.type, BRICK.Zone_Air_Temperature_Sensor))
```

### Importing RDF Graphs Into a Model

```{margin}
```{important}
You should not load ontologies, schemas, rules, etc. into a Model. These belong in **Libraries**!
```

It is also possible to import RDF graphs into a `Model`.

If you already have an in-memory `RDFlib.Graph` object available (e.g. through an [Graph Ingress](../explanations/ingresses) or loading in a Turtle file), just use `Model.add_graph`:

```{code-cell}
import rdflib
my_graph = rdflib.Graph()
# parse files:
# my_graph.parse("my_external_file.ttl")
# or parse raw strings:
my_graph.parse(data='''
@prefix bldg: <urn:ex/> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
bldg:Core_ZN-PSC_AC a brick:Air_Handler_Unit .
''')
model.add_graph(my_graph)
```

You can also use the `Model.graph.parse` method directly:

```{code-cell}
model.graph.parse(data='''
@prefix bldg: <urn:ex/> .
@prefix brick: <https://brickschema.org/schema/Brick#> .
bldg:Core_ZN-PSC_AC a brick:Air_Handler_Unit .
''')
```

## Adding to a Model with Templates

### Exploring a Template

```{margin}
```{note}
`Templates` are functions that generate parts of an RDF model.
```

`Templates` make it easy to add metadata to a model without having to touch any RDF at all by generating parts of an RDF graph. This graph may represent a simple device like a fan, a complex entity like a chilled water system, or other parts of a building. The *body* of a template contains the basic structure of the graph representing that entity. Typically, a template defines several *parameters* that represent user-provided input necessary to create that entity in the model.

Let's start with the template for an air handling unit (AHU) from the `brick` library, which we can fetch out of the library by referring to it by name. Then, let's ask the template for the parameters it defines. 

```{code-cell}
# import this to make writing URIs easier
from buildingmotif.namespaces import BRICK

# get template
ahu_template = brick.get_template_by_name(BRICK.AHU)

# print template parameters
print("The template has the following parameters:")
for param in ahu_template.parameters:
    print(f"  {param}")
```

All templates have a mandatory `name` parameter. We can also print out the body of the template to see how those parameters will be used. Any URI that starts with a `p:` is a parameter.

```{code-cell}
print(ahu_template.body.serialize())
```

### Evaluating a Template

```{margin}
```{note}
For now, provide all of the parameters to the Template when evaluating. BuildingMOTIF does support partial evaluation of Templates but this is not necessary to understand or use when starting out.
```

Now that we know what the template looks like and what parameters it needs, we can *evaluate* the Template. *Evaluation* is the process of turning a template into a graph that can be added to a model. We accomplish this with the `evaluate` function, which takes a dictionary of *bindings* as an argument. Bindings relate a parameter in the template to a value (typically a URI in your building's namespace). Put another way, the *keys* of the dictionary are the names of the parameters and the *values* of the dictionary are what will replace that parameter in the template's body.

Let's create an AHU named *Core_ZN-PSZ_AC*, which represents the core zone's packaged single zone air conditioner in the Small Office model, and take a look at the result of evaluating the template.

```{margin}
```{note}
When creating a real Brick model, you would use BMS point names, equipment schedules, etc. to determine the correct names of these entities. Other tutorials will cover how to use BuildingMOTIF with these kinds of metadata sources.
```

```{code-cell}
ahu_name = "Core_ZN-PSC_AC"
ahu_binding_dict = {"name": BLDG[ahu_name]}
ahu_graph = ahu_template.substitute(ahu_binding_dict).to_graph()

# ahu_graph is just an instance of rdflib.Graph
print(ahu_graph.serialize())
```

### Adding Evaluated Templates to the Model

```{margin}
```{note}
If using a persistent (disk-backed) instance of BuildingMOTIF instead of an in-memory instance, run your work inside a `with BuildingMOTIF(...)` block (see "Persisting your work" above) or call `bm.session.commit()` yourself after calling `add_graph`.
```

Now that we have an RDF graph representing an AHU, let's add it to the model using the `add_graph` function. 

```{code-cell}
model.add_graph(ahu_graph)
print(model.graph.serialize())
```

Next, we'll add some of the AHU's components (a fan, a damper, and a cooling coil) to the model using Templates. Then we'll connect the components to the AHU using RDFLib's `graph.add((subject, predicate, object))` method.

```{code-cell}
# templates
oa_ra_damper_template = brick.get_template_by_name(BRICK.Outside_Damper)
damper_template = brick.get_template_by_name(BRICK.Damper)
fan_template = brick.get_template_by_name(BRICK.Supply_Fan)
clg_coil_template = brick.get_template_by_name(BRICK.Cooling_Coil)

# add fan
fan_name = f"{ahu_name}-Fan"
fan_binding_dict = {"name": BLDG[fan_name]}
fan_graph = fan_template.substitute(fan_binding_dict).to_graph()
model.add_graph(fan_graph)

# add outdoor air/return air damper
oa_ra_damper_name = f"{ahu_name}-OutsideDamper"
oa_ra_damper_binding_dict = {"name": BLDG[oa_ra_damper_name]}
oa_ra_damper_graph = oa_ra_damper_template.substitute(oa_ra_damper_binding_dict).to_graph()
model.add_graph(oa_ra_damper_graph)

# add other damper
damper_name = f"{ahu_name}-Damper"
damper_binding_dict = {"name": BLDG[damper_name]}
damper_graph = damper_template.substitute(damper_binding_dict).to_graph()
model.add_graph(damper_graph)

# add clg coil
clg_coil_name = f"{ahu_name}-Clg_Coil"
clg_coil_binding_dict = {"name": BLDG[clg_coil_name]}
clg_coil_graph = clg_coil_template.substitute(clg_coil_binding_dict).to_graph()
model.add_graph(clg_coil_graph)

# connect zone-temp, fan, dampers, and clg coil to AHU
model.graph.add((BLDG[ahu_name], BRICK.hasPoint, BLDG["zone-temp"]))
model.graph.add((BLDG[ahu_name], BRICK.hasPart, BLDG[oa_ra_damper_name]))
model.graph.add((BLDG[ahu_name], BRICK.hasPart, BLDG[damper_name]))
model.graph.add((BLDG[ahu_name], BRICK.hasPart, BLDG[fan_name]))
model.graph.add((BLDG[ahu_name], BRICK.hasPart, BLDG[clg_coil_name]))

# you can add triples directly too
model.graph.add((BLDG[oa_ra_damper_name], BRICK.hasPoint, BLDG[oa_ra_damper_name + "Position"]))
model.graph.add((BLDG[oa_ra_damper_name + "Position"], RDF.type, BRICK.Damper_Position_Command))

# print model to confirm components were added and connected
print(model.graph.serialize())
```

```{attention}
If you want some additional practice, try writing some Python code that adds a Brick `Heating_Coil` to the model and connects it to the AHU.
```

```{hint}
:class: dropdown

```python
# get template
htg_coil_template = brick.get_template_by_name(BRICK.Heating_Coil)

# add htg coil
htg_coil_name = f"{ahu_name}-Htg_Coil"
htg_coil_binding = {"name": BLDG[htg_coil_name]}
htg_coil_graph = htg_coil_template.substitute(htg_coil_binding).to_graph()
model.add_graph(htg_coil_graph)

# connect htg coil to AHU
model.graph.add((BLDG[ahu_name], BRICK.hasPart, BLDG[htg_coil_name]))

# print model to confirm component was added and connected
print(model.graph.serialize())
```

Finally, let's save the model to use in the next tutorial.

```{code-cell}
#save model
model.graph.serialize(destination="tutorial1_model.ttl")
```
