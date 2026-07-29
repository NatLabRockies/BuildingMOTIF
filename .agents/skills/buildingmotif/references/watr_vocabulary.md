# WaTr (`watr:`) vocabulary and water-treatment modeling patterns

WaTr is the NAWI water metadata ontology for describing water-treatment equipment,
treatment processes, media and constituents, telemetry context, and treatment-train
topology. It is an **extension of ASHRAE 223**, not a separate topology model: WaTr adds
water-domain terms while reusing `s223:` equipment, connections, connection points,
properties, roles, external references, and composition.

Use this file when the user's graph targets the WaTr namespace, models a treatment train,
or needs water-specific equipment/process/media terms. Read `223p_vocabulary.md` alongside
it for the underlying topology and property patterns.

Authoritative resources:

- Landing page, current download, documentation, and browser:
  <https://watermetadata.org>
- Current compiled ontology: <https://watermetadata.org/water.ttl>
- Source, examples, and BuildingMOTIF template libraries:
  <https://github.com/DataDrivenCPS/water-ontology>

The ontology is actively developed. Verify terms against the downloaded `water.ttl`
instead of copying a local name from an old model or guessing from prose.

## Contents

- [Namespaces and imports](#namespaces-and-imports)
- [Loading WaTr with BuildingMOTIF](#loading-watr-with-buildingmotif)
- [The three layers of a WaTr model](#the-three-layers-of-a-watr-model)
- [Topology and composition come from 223](#topology-and-composition-come-from-223)
- [Water media, constituents, and chemicals](#water-media-constituents-and-chemicals)
- [Sensors, properties, and water-quality measurements](#sensors-properties-and-water-quality-measurements)
- [Discover and verify terms before asserting](#discover-and-verify-terms-before-asserting)
- [Validation and reporting](#validation-and-reporting)
- [Gotchas](#gotchas)

## Namespaces and imports

The canonical namespace and ontology IRI are different:

```turtle
@prefix watr: <urn:nawi-water-ontology#> .

<urn:nawi-water-ontology> a owl:Ontology .
```

Do not substitute an HTTP URL for the `watr:` namespace. The HTTP URL is the download
location; WaTr resources themselves use `urn:nawi-water-ontology#`.

The current compiled ontology imports:

- ASHRAE 223 1.0 model/all — topology, equipment, properties, media, roles
- QUDT quantity kinds and units
- SHACL

Consequently, a WaTr model normally uses all of these prefixes:

```turtle
@prefix watr: <urn:nawi-water-ontology#> .
@prefix s223: <http://data.ashrae.org/standard223#> .
@prefix qudt: <http://qudt.org/schema/qudt/> .
@prefix quantitykind: <http://qudt.org/vocab/quantitykind/> .
@prefix unit: <http://qudt.org/vocab/unit/> .
```

## Loading WaTr with BuildingMOTIF

WaTr is not packaged in `buildingmotif/libraries/`. Download `water.ttl` from the site
and load that file:

```python
from rdflib import Namespace
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library

WATR = Namespace("urn:nawi-water-ontology#")

bm = BuildingMOTIF("sqlite://")
watr = Library.from_ontology(
    "path/to/water.ttl",
    run_shacl_inference=False,
)
watr_graph = watr.get_shape_collection().graph
```

With BuildingMOTIF's default `ontology_fetch_imports=True`, OntoEnv resolves WaTr's 223
and QUDT imports. For an offline workflow, first populate an ontology cache or local search
directory with WaTr and its import closure; see `ontology_imports.md`.

Load WaTr **before** a template library whose templates depend on WaTr class templates.
The water-ontology repository's `libraries/templates/` and
`libraries/nrel-223p-templates/` are useful examples, but they are external, repo-only
sample libraries—not BuildingMOTIF builtins and not part of `water.ttl`.

## The three layers of a WaTr model

Keep three concerns distinct:

| Concern | Vocabulary and pattern |
|---|---|
| What physical thing is present? | `watr:` equipment type, such as `watr:ReverseOsmosisMembrane`, `watr:Pump`, or `watr:Tank` |
| What treatment does it perform? | `watr:hasProcess` to a controlled `watr:Process-*` term |
| How does material flow through it? | 223 topology: `s223:hasConnectionPoint`, concrete connection-point types, `s223:hasMedium`, and connections using `s223:cnx` |

Do not infer one layer from another in the data you assert. A reverse-osmosis membrane
class carries a SHACL requirement for the reverse-osmosis process, but the instance still
needs the explicit `watr:hasProcess` triple to conform.

### Equipment and unit processes

`watr:UnitProcess` is a subclass of `s223:Equipment`. Every instance must have at least
one `watr:hasProcess` value that conforms to `watr:Process`. More specific WaTr equipment
classes add tighter process or topology requirements. Examples in the current ontology
include:

- `watr:Filter` → a filtration process
- `watr:ReverseOsmosisMembrane` → reverse osmosis
- `watr:ChlorinationUnit` → chlorination
- `watr:RapidSandFilter` → rapid-sand filtration
- `watr:Thickener` → thickening
- `watr:Tank` → inlet and outlet fluid connection points
- `watr:SeparationTank` → at least two outlet connection points

Type an asset with the most specific verified class supported by evidence:

```turtle
:ro1 a watr:ReverseOsmosisMembrane ;
    watr:hasProcess watr:Process-ReverseOsmosis ;
    s223:hasConnectionPoint :ro1-in, :ro1-permeate, :ro1-concentrate .
```

`watr:UnitProcess` is suitable when the evidence establishes that something performs
treatment but does not support a more specific equipment design. Do not use a specific
membrane, reactor, or filter class merely because its associated process name matches.

### Treatment process types

Process terms use the `Process-` local-name convention and form an `rdfs:subClassOf`
hierarchy rooted at `watr:Process`. The top-level families are:

- `watr:Process-BiologicalProcess`
- `watr:Process-ChemicalProcess`
- `watr:Process-PhysicalProcess`

More specific terms can have multiple parents. For example, biofiltration is both
biological treatment and filtration. Associate the controlled term directly with the
equipment:

```turtle
:uv1 a watr:UnitProcess ;
    watr:hasProcess watr:Process-UVDisinfection .
```

Do not create an arbitrary instance such as `:my_reverse_osmosis_process` unless the
application genuinely needs to identify a distinct process occurrence. The ontology and
its examples normally use the named `watr:Process-*` resource directly.

Do not derive a process IRI mechanically from an equipment name. Search the ontology:
`watr:UltravioletLightUnit` pairs with `watr:Process-UVDisinfection`, for example, not a
guessed `Process-UltravioletLight`.

## Topology and composition come from 223

Use the complete 223 patterns from `223p_vocabulary.md`. The minimum equipment-port
pattern is:

```turtle
:tank1 a watr:Tank ;
    s223:hasConnectionPoint :tank1-in, :tank1-out .

:tank1-in a s223:InletConnectionPoint ;
    s223:hasMedium s223:Fluid-Water .

:tank1-out a s223:OutletConnectionPoint ;
    s223:hasMedium s223:Fluid-Water .
```

Use a connection such as `s223:Pipe` between equipment ports and connect it with
`s223:cnx`. Use `s223:contains` for composite equipment and `s223:mapsTo` to relate an
internal component's exposed port to the containing equipment's port.

```turtle
:ro-skid a watr:UnitProcess ;
    watr:hasProcess watr:Process-ReverseOsmosis ;
    s223:contains :ro-membrane ;
    s223:hasConnectionPoint :skid-in, :skid-permeate .

:ro-membrane a watr:ReverseOsmosisMembrane ;
    watr:hasProcess watr:Process-ReverseOsmosis ;
    s223:hasConnectionPoint :membrane-in, :membrane-permeate .

:membrane-in s223:mapsTo :skid-in .
:membrane-permeate s223:mapsTo :skid-permeate .
```

Do not replace these relations with imagined WaTr-specific equivalents. The current WaTr
ontology defines `watr:hasProcess` and data-quality relations, but deliberately delegates
topology, containment, roles, properties, and media relations to `s223:`.

## Water media, constituents, and chemicals

Use `s223:hasMedium` on connection points and connections. Choose the most specific
available medium class supported by evidence:

- 223 provides broad terms such as `s223:Fluid-Water` and `s223:Mix-Fluid`.
- WaTr adds `watr:Water-Brackish`, `watr:Water-Brine`,
  `watr:Water-Freshwater`, `watr:Water-Seawater`, `watr:Fluid-Sludge`, and
  `watr:Sludge-MixedLiquor`.

WaTr media resources are class-like controlled terms and are self-typed in the ontology,
following the 223 enumeration pattern. Use the term as the `hasMedium` value:

```turtle
:feed-in a s223:InletConnectionPoint ;
    s223:hasMedium watr:Water-Brackish ;
    s223:hasRole watr:Role-Feed .

:sludge-out a s223:OutletConnectionPoint ;
    s223:hasMedium watr:Fluid-Sludge .
```

Composition uses `s223:composedOf` with quantifiable properties whose
`s223:ofConstituent` identifies the substance. WaTr includes constituent families such as
organics, salts, solids, suspended solids, ammonia, nitrate, nitrite, bacteria, metals,
and dissolved oxygen, plus treatment chemicals such as coagulants, flocculants,
disinfectants, and pH adjusters.

```turtle
:brine-15-percent
    a watr:Class, sh:NodeShape, :brine-15-percent ;
    rdfs:subClassOf watr:Water-Brine ;
    s223:composedOf [
        a s223:QuantifiableProperty ;
        s223:hasValue 15 ;
        s223:ofConstituent watr:Salt-NaCl ;
        qudt:hasQuantityKind quantitykind:MassFraction ;
        qudt:hasUnit unit:PERCENT
    ] .
```

Only mint a project-specific medium class when its composition is a reusable part of the
model. For a measured concentration at one location, model a property with
`s223:ofMedium` and `s223:ofSubstance` instead.

## Sensors, properties, and water-quality measurements

WaTr sensor classes extend 223 sensor classes—examples include
`watr:ConductivitySensor`, `watr:OxygenDemandSensor`, `watr:pHSensor`, and
`watr:TotalOrganicCompoundConcentrationSensor`. The measurement pattern remains 223:

1. The sensor `s223:observes` one observable property.
2. The sensor has an `s223:hasObservationLocation`.
3. The property carries QUDT quantity kind and unit.
4. Add `s223:ofMedium` and/or `s223:ofSubstance` when they are needed to distinguish what
   the number describes.

```turtle
:toc-sensor a watr:TotalOrganicCompoundConcentrationSensor ;
    s223:observes :toc ;
    s223:hasObservationLocation :sample-port .

:toc a s223:QuantifiableObservableProperty ;
    s223:ofMedium s223:Fluid-Water ;
    s223:ofSubstance watr:Constituent-Organics ;
    qudt:hasQuantityKind quantitykind:MassConcentration ;
    qudt:hasUnit unit:MilliGM-PER-L .
```

Use QUDT's `qudt:hasQuantityKind` and `qudt:hasUnit`; do not use similarly named
`s223:` properties. Check terms against the imported QUDT version and follow the
deprecation check in `223p_vocabulary.md`.

### Data quality and aggregation

WaTr adds relations to contextualize `s223:QuantifiableProperty` nodes:

`watr:hasAccuracy`, `hasPrecision`, `hasBias`, `hasResponseTime`,
`hasNumericResolution`, `hasNumericRange`, `hasVariableRange`,
`hasMeasurementRange`, `hasTemporalResolution`, `hasTemporalRange`,
`hasCalibrationCurve`, `hasDropRate`, `hasProcessedData`, and `hasAggregation`.

Most of these point to another `s223:QuantifiableProperty`, not directly to a bare
literal. Put the value and unit on that property:

```turtle
:flow-sensor a watr:FlowSensor ;
    s223:observes :flow ;
    watr:hasMeasurementRange :flow-range .

:flow a s223:QuantifiableObservableProperty ;
    qudt:hasQuantityKind quantitykind:VolumeFlowRate ;
    qudt:hasUnit unit:L-PER-SEC .

:flow-range a s223:QuantifiableProperty ;
    s223:hasValue 100 ;
    qudt:hasQuantityKind quantitykind:VolumeFlowRate ;
    qudt:hasUnit unit:L-PER-SEC .
```

`watr:hasAggregation` has maximum count one and points to an aggregation term such as
`watr:Aggregation-Max`. For a percentile, mint an instance of
`watr:Aggregation-Percentile` (for example, `:Percentile-95`) rather than treating the
numeric percentile as a bare aggregation value.

## Discover and verify terms before asserting

WaTr classes are generally marked `a watr:Class`; many are also `sh:NodeShape`. They are
not consistently declared `owl:Class`, so an OWL-only lookup will miss valid terms.

```python
from rdflib import Namespace
from rdflib.namespace import OWL, RDF, RDFS, SH, SKOS

WATR = Namespace("urn:nawi-water-ontology#")

def watr_term(local_name: str):
    term = WATR[local_name]
    exists = (
        (term, RDF.type, WATR.Class) in watr_graph
        or (term, RDF.type, SH.NodeShape) in watr_graph
        or (term, RDF.type, RDF.Property) in watr_graph
    )
    if not exists:
        return None
    deprecated = next(watr_graph.objects(term, OWL.deprecated), None)
    if deprecated is not None and deprecated.toPython():
        print(f"WARNING: {local_name} is deprecated")
    return term

def search_watr(*words: str, limit: int = 100):
    wanted = [word.lower().replace("_", " ") for word in words]
    candidates = set(watr_graph.subjects(RDF.type, WATR.Class))
    candidates |= set(watr_graph.subjects(RDF.type, SH.NodeShape))
    candidates |= set(watr_graph.subjects(RDF.type, RDF.Property))
    hits = []
    for term in candidates:
        if not str(term).startswith(str(WATR)):
            continue
        local = str(term).split("#")[-1]
        fields = [local.replace("_", " ").replace("-", " ")]
        fields += [str(v) for v in watr_graph.objects(term, RDFS.label)]
        fields += [str(v) for v in watr_graph.objects(term, RDFS.comment)]
        fields += [str(v) for v in watr_graph.objects(term, SKOS.definition)]
        haystack = " ".join(fields).lower()
        if all(word in haystack for word in wanted):
            hits.append(local)
    return sorted(set(hits))[:limit]

print(watr_term("ReverseOsmosisMembrane"))
print(search_watr("reverse", "osmosis"))
print(search_watr("nitrate"))
```

Walk the hierarchy to find specific equipment or process terms:

```python
def watr_descendants(local_name: str, limit: int = 200):
    root = WATR[local_name]
    query = """
    SELECT DISTINCT ?term WHERE {
      ?term rdfs:subClassOf+ ?root .
      FILTER(STRSTARTS(STR(?term), STR(watr:)))
    }
    ORDER BY ?term
    """
    rows = watr_graph.query(
        query,
        initNs={"rdfs": RDFS, "watr": WATR},
        initBindings={"root": root},
    )
    return [str(row.term).split("#")[-1] for row in rows][:limit]

print(watr_descendants("UnitProcess"))
print(watr_descendants("Process"))
print(watr_descendants("Constituent-Particles"))
```

Inspect a candidate's SHACL constraints before using it; specific equipment often requires
a particular process, number/direction of ports, medium family, or role:

```python
def describe_watr_shape(local_name: str):
    term = WATR[local_name]
    print("parents:", list(watr_graph.objects(term, RDFS.subClassOf)))
    for shape in watr_graph.objects(term, SH.property):
        print({
            "path": next(watr_graph.objects(shape, SH.path), None),
            "class": next(watr_graph.objects(shape, SH["class"]), None),
            "hasValue": next(watr_graph.objects(shape, SH.hasValue), None),
            "min": (
                next(watr_graph.objects(shape, SH.minCount), None)
                or next(watr_graph.objects(shape, SH.qualifiedMinCount), None)
            ),
            "max": (
                next(watr_graph.objects(shape, SH.maxCount), None)
                or next(watr_graph.objects(shape, SH.qualifiedMaxCount), None)
            ),
        })

describe_watr_shape("Tank")
describe_watr_shape("ReverseOsmosisMembrane")
```

## Validation and reporting

Validate the data graph against the WaTr shape collection using the normal iterative
BuildingMOTIF workflow in `validation.md`. Imports must be resolved so that inherited 223
constraints are present:

```python
ctx = model.validate([watr.get_shape_collection()])

print("valid:", ctx.valid)
for witness in ctx.diffset:
    print(witness.reason())
```

Translate failures into water-treatment language:

- "`tank1` needs an inlet carrying a fluid medium"
- "`ro1` is typed as a reverse-osmosis membrane but has no reverse-osmosis process"
- "`clarifier1` needs two outlet connection points"

Keep the underlying SHACL result available, but do not report only `qualifiedMinCount` or
`sh:path` jargon.

## Gotchas

- **WaTr is `urn:nawi-water-ontology#`, not `https://watermetadata.org/...`.**
- **WaTr extends 223.** Use `s223:` for topology, composition, roles, properties, and
  observations; do not invent parallel `watr:` predicates.
- **A piece of equipment and its treatment process are different facts.** Assert both
  the equipment type and the required `watr:hasProcess` value.
- **Specific WaTr classes carry active SHACL constraints.** Typing something as
  `watr:Tank`, `SeparationTank`, `PlugFlowReactor`, or `SequencingBatchReactor` commits
  the model to required connection points and media.
- **Processes and controlled media/constituent/role terms use class-like self-typing.**
  Use the named term as the relation value; do not assume every vocabulary item behaves
  like an ordinary `owl:Class`.
- **Use concrete 223 connection-point subclasses.** Never instantiate the abstract
  `s223:ConnectionPoint`.
- **The website ontology is moving.** Search the current graph and inspect its shapes
  before mapping a P&ID label or accepting a repair proposal.
- **Ontology and templates are separate artifacts.** `water.ttl` supplies vocabulary and
  shapes. The source repository's YAML libraries supply reusable BuildingMOTIF templates.
