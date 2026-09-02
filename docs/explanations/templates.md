# Templates

Templates are reusable RDF graph fragments with named parameters. Bind values
with `substitute()` and call `to_graph()` once the required parameters are set.

## How to Define Templates


### YAML Format

The most common way of defining a Template is as a YAML document. Several Templates can be expressed in the same YAML file.
A YAML template has several components:
- the **name** of the template is the top-level key of the YAML document
- a template *must* have a **body** key, whose value is an RDF graph (see below for details on the graph)
- a template *may* have an **optional** key, whose value is a list of parameter names
- a template *may* have a **dependencies** key, whose value is a list of dependency dictionaries (see below for details on dependencies)

The **body** of a template is an RDF graph. Parameters are nodes/edges in the graph which exist in the `urn:___param___#` namespace (this can be bound to any prefix, but is commonly bound to `P` or `p`).
When a template is filled, its parameters are replaced with the provided bindings.
The parameters of a template are exactly those which appear in the RDF Graph body.

The other elements of a template's definition -- `optional`, `dependencies`, etc -- refer to the name of a parameter *without* the `urn:___param___#` prefix.
For example, a parameter would be defined in the body as `P:sensor` or `urn:___param___#sensor` (these are equivalent, provided there is a `@prefix P: <urn:___param___#>` line), but the other elements of the template would refer to this parameter simply as `sensor`

Here is an example of two YAML templates.

```yaml
vav-cooling-only:
  body: >
    @prefix p: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    p:name a brick:VAV ;
        brick:hasPoint p:ztemp, p:occ, p:co2, p:dat ;
        brick:hasPart p:dmp ;
        brick:feeds p:zone .
  optional: ['occ', 'co2']
  dependencies:
    - template: damper
      args: {"name": "dmp"}
    - template: https://brickschema.org/schema/Brick#HVAC_Zone
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "zone"}
    - template: https://brickschema.org/schema/Brick#Zone_Air_Temperature_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "ztemp"}
    - template: https://brickschema.org/schema/Brick#Occupancy_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "occ"}
    - template: https://brickschema.org/schema/Brick#CO2_Level_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "co2"}
    - template: https://brickschema.org/schema/Brick#Discharge_Air_Temperature_Sensor
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "dat"}

damper:
    body: >
      @prefix P: <urn:___param___#> .
      @prefix brick: <https://brickschema.org/schema/Brick#> .
      P:name a brick:Damper .
```

### SHACL Shapes

BuildingMOTIF can also infer a template from certain SHACL shape definitions.
This happens when a Library is loaded into BuildingMOTIF that contains an RDF graph; this can happen by loading the RDF graph directly (via `Library.from_ontology("path to graph")`)
or by loading in a directory that contains RDF graphs (via `Library.from_directory("directory with .ttl files")`).

Given an RDF graph, BuildingMOTIF will create a template for each instance of `sh:NodeShape` *provided* that it is also an instance of `owl:Class`.
In the following RDF graph, BuildingMOTIF would create a template for `vav_shape` but not `sensor_shape`:

```ttl
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix : <urn:shape1/> .

:vav_shape a sh:NodeShape, owl:Class ;
    sh:targetClass brick:VAV ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:node :sensor_shape ] ;
        sh:qualifiedMinCount 1 ;
    ] ;
.

:sensor_shape a sh:NodeShape ;
    sh:class brick:Temperature_Sensor ;
    sh:property [
        sh:path brick:hasUnit ;
        sh:hasValue unit:DEG_C ;
    ] ;
.
```

BuildingMOTIF will create a `name` parameter for the shape automatically. It will create a parameter for each Property Shape on the input Node Shape if
that Property Shape has one of `sh:class`, `sh:node` or `sh:datatype` inside; use of `sh:qualifiedValueShape` is permitted.
Only Property Shapes with a `sh:minCount` or `sh:qualifiedMinCount` greater than 0 will be included.
If the Property Shape contains a `sh:name` parameter, the string value of `sh:name` will be used as the name of the parameter; otherwise, BuildingMOTIF 
will invent a new name (`P:pX` where *X* is an incrementing integer).

The name of the template is the IRI of the SHACL Node Shape.

## Template Dependencies

Dependencies can be declared explicitly in YAML or inferred from SHACL shapes.

**Remember to load libraries containing dependencies before loading in libraries containing the dependents**.
For example, it is generally recommended to import your base ontologies (Brick, ASHRAE 223P, etc) before any application libraries, as the application libraries will depend on concepts defined in the ontologies.

### Explicit Template Dependencies

A template dependency is a dictionary with the following keys:
- `template` (required): the name of the template
- `library` (optional): the name of the Library from which to load the template
- `args` (required): a dictionary mapping a dependency's parameter names to this template's parameter names. A value bound to the local parameter is also bound to the matching dependency parameter.

When depending on another template, it is not necessary to bind all of the parameters.
This affects how [inlining](template-inline) works.

The template in the example below has two dependencies. The first dependency is on another template called `damper` in the same Library as `vav-cooling-only`. The `name` parameter
of the `damper` template will be bound to the value of the `dmp` parameter in the `vav-cooling-only` template.
The second dependency is on the HVAC Zone template in the Brick ontology (this template is inferred automatically from the `brick:HVAC_Zone` Node Shape when the Brick library is loaded).
The `name` parameter of the HVAC zone template will be bound to the `zone` parameter in the `vav-cooling-only` template.

```yaml
vav-cooling-only:
  body: >
    @prefix p: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    p:name a brick:VAV ;
        brick:hasPoint p:ztemp, p:occ, p:co2, p:dat ;
        brick:hasPart p:dmp ;
        brick:feeds p:zone .
  optional: ['occ', 'co2']
  dependencies:
    - template: damper
      args: {"name": "dmp"}
    - template: https://brickschema.org/schema/Brick#HVAC_Zone
      library: https://brickschema.org/schema/1.3/Brick
      args: {"name": "zone"}
```


### Implicit Template Dependencies

BuildingMOTIF will add dependencies to a template inferred from a Node Shape in each of the following cases.
- if a Property Shape on the Node Shape refers to a Node Shape through `sh:class` (the Node Shape dependency will probably also be an `owl:Class`)
- if a Property Shape on the Node Shape refers to a Node Shape through `sh:node`
- if the Node Shape refers to another Node Shape through `sh:node`

The template inferred from the `vav_shape` Node Shape below will have 2 dependencies.
The first dependency is on the `:Air_Flow_Sensor` template, also defined in this library.
The invented parameter name for the first property shape (probably `p1`) will be bound to the `name` parameter of the inferred `:Air_Flow_Sensor` template.
The second dependency is on the `brick:Air_Temperature_Sensor` template which is defined in the Brick ontology.
The `temp_sensor` parameter of the `vav_shape` template will be bound to the `name` parameter of the inferred `brick:Air_Temperature_Sensor` template.

BuildingMOTIF will search all of the graphs in `owl:imports` for definitions of Node Shapes if they are not defined in the current library.
Because `:Air_Flow_Sensor` is defined in the same graph as `vav_shape`, BuildingMOTIF can find its definition easily.
Because `brick:Air_Temperature_Sensor` is not defined in the graph below, BuildingMOTIF searches the imported graph `https://brickschema.org/schema/1.3/Brick` for
the definition.


```ttl
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix unit: <http://qudt.org/vocab/unit/> .
@prefix : <urn:shape/> .

: a owl:Ontology ;
    owl:imports <https://brickschema.org/schema/1.3/Brick> .

:vav_shape a sh:NodeShape, owl:Class ;
    sh:targetClass brick:VAV ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:qualifiedValueShape [ sh:node :Air_Flow_Sensor ] ;
        sh:qualifiedMinCount 1 ;
    ] ;
    sh:property [
        sh:path brick:hasPoint ;
        sh:name "temp_sensor" ;
        sh:qualifiedValueShape [ sh:node brick:Air_Temperature_Sensor ] ;
        sh:qualifiedMinCount 1 ;
    ] ;
.

:Air_Flow_Sensor a sh:NodeShape, owl:Class ;
    sh:class brick:Air_Flow_Sensor ;
    sh:property [
        sh:path brick:hasUnit ;
        sh:hasValue unit:DEG_C ;
        sh:minCount 1 ;
    ]
.
```


(template-inline)=
## Template Inlining

Coming soon...

(template-eval)=
## Template Evaluation

Coming soon...
