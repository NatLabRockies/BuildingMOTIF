# Libraries

This directory contains sample libraries for use with BuildingMOTIF. The libraries themselves are the leaf directories of this file structure.

Templates (which help generate models) are contained in `.yml` files; shapes (which help validate models) are contained in `.ttl` files.

## Template Structure

**TODO: A fuller template tutorial**

Templates are expressed as documents in `.yml` files. The name of the template is at the top level of the YAML file.
Each template has a
- a set of `dependencies`: list of other template names and mappings between those template's parameters and this template's parameters.
  Each dependency has three required keys:
  - `template`: the name of the template the outer template is dependent on
  - `args`: the association of dependency parameters to this template's parameters
  - `library`: the name of the library from which the template is drawn (defaults to current library)
- `body`: a Turtle-encoded graph which defines the content of the template. The `urn:__param__#` namespace is used to name the parameters

The following is an example of a template:

```yaml
my-vav-template:
  body: >
    @prefix P: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    P:name a brick:VAV ;
      brick:feeds P:zone ;
      brick:hasPoint P:sen .
  dependencies:
   - template: temp-sensor
     args: {"name": "sen"}
   - template: https://brickschema.org/schema/Brick#HVAC_Zone
     library: https://brickschema.org/schema/1.3/Brick
     args: {"name": "zone"}

temp-sensor:
  body: >
    @prefix P: <urn:___param___#> .
    @prefix brick: <https://brickschema.org/schema/Brick#> .
    bmparam:name a brick:Temperature_Sensor ;
        ref:hasExternalRepresentation [
           ref:hasTimeseriesId P:id ;
        ] ;
    .
```

BuildingMOTIF will handle template *evaluation*, which produces a graph from the template `body` using bindings provided by program using BuildingMOTIF.


## Packaged Libraries

```
libraries/
├── ashrae
│   └── guideline36
│       ├── 4.1-vav-cooling-only.yml
│       ├── 4.2-vav-with-reheat.yml
│       └── 4.3-fan-powered.yml
└── brick
    └── Brick.ttl
 ```

### ASHRAE / Guideline 36

This library contains templates for equipment adhering to the point list requirements as defined by ASHRAE Guideline 36.

### Brick

This library contains a subset of the Brick v1.3 distribution, allowing the use of Brick types as "templates" for building models.
This also contains a set of shapes that verify that a model conforms to the Brick v1.3 requirements.

### Chiller Plant

This is a set of templates for simple chiller plants with some basic points.
