# Point labels and class mapping

## Contents

- [Workflow](#workflow)
- [Starter Brick mappings](#starter-brick-mapping-patterns)
- [BuildingMOTIF label parser](#buildingmotif-label-parser)
- [Synthesize graph triples](#synthesizing-graph-triples-from-token-records)
- [Non-BMS inputs](#non-bms-inputs)
- [Reporting](#reporting)

Point-list builds are usually not blocked by graph mechanics; they are blocked by the
mapping from source metadata to the requested ontology. BMS point labels are a common
Brick source, but the same workflow applies to WaTr SCADA tags, CSV columns, BACnet object
names, schedules, and submittal tables: extract identifiers, map source vocabulary to
verified target terms, build the graph, then validate.

Do not assume the input is always a BMS naming convention. Start by identifying the source
shape:

- **label-like**: one compact string encodes building/equipment/point meaning
  (`:Building_02:FCU503_ChwVlvPos`, `VAV-1/SAT`);
- **table-like**: separate columns already say `equipment`, `description`, `units`,
  `io_type`, `object_name`;
- **document-like**: prose, schedules, or submittal rows need extraction before mapping.

Use `buildingmotif.label_parsing` for label-like sources. For table-like sources, a
hand-written row mapper is usually clearer than forcing columns back into a synthetic
label. For document-like sources, extract a table/record set first, then apply the same
mapping loop.

## Workflow

1. Identify the source pattern: equipment identifier, optional location/system pieces,
   point suffix, I/O type, units, and description columns.
2. Identify the target vocabulary before mapping: Brick, 223P, or WaTr-on-223P.
3. Build a small source-token mapping table from the distinct suffixes or columns. Verify
   target terms with `brick_vocabulary.md`, or with `watr_vocabulary.md` and
   `223p_vocabulary.md`; do not trust guessed names.
4. Parse all rows and group failures by the unparsed suffix or unknown token.
5. Build equipment with templates where they fit, and add typed point leaves directly
   when the point list only gives point identity/type/owner.
6. Validate, then refine the mapping and graph structure.

Keep the mapping table as a visible artifact in the durable BuildingMOTIF build script. In
the same script, print the distinct source tokens and unmapped counts, query candidate
ontology terms, validate a representative mapping, and then apply the verified table to
all rows. This makes exploration reproducible and keeps a candidate discovered during an
interactive query from silently becoming an assertion. The mapping table is
evidence-bearing domain logic, not boilerplate.

## Starter Brick mapping patterns

Treat these as examples, not universal truth. Confirm with units, I/O type, and nearby
columns before applying them.

| Source token examples | Likely Brick class pattern |
|---|---|
| `ZN-T`, `ZNT`, `Zone Air Temp`, `RoomTmp`, `SPACE_TMP` | `brick:Zone_Air_Temperature_Sensor` or `brick:Room_Temperature_Sensor` |
| `SAT`, `SA-T`, `SaTmp` | `brick:Supply_Air_Temperature_Sensor` |
| `RAT`, `RA-T` | `brick:Return_Air_Temperature_Sensor` |
| `DAT`, `DA-T` | `brick:Discharge_Air_Temperature_Sensor` |
| `HSP`, `HTG STPT`, `Heating Spt` | heating temperature setpoint class |
| `CSP`, `CLG STPT`, `Cooling Spt` | cooling temperature setpoint class |
| `STPT`, `SP`, `Spt` | a `Setpoint`; make it temperature/pressure/etc. from context |
| `COMD`, `CMD`, `Command` | a `Command`; compose with the controlled quantity/equipment |
| `STS`, `Status`, `Run Status` | often `brick:Run_Status`, not necessarily a `Sensor` |
| `DMPR COMD`, `Damper Cmd` | damper position or open/close command, depending on units/type |
| `VLV COMD`, `VlvOut`, `VlvPos` | valve command or position sensor; distinguish AO/BO from AI |
| `OAFMS`, `Flow`, `Air Flow` | air flow sensor/setpoint; use location/system words |

Use a conservative fallback for unknown suffixes: leave them unmapped and report the
distinct tokens. Do not silently map `CCO`, `HRWS`, or site-specific tags from intuition.

## BuildingMOTIF label parser

Use `buildingmotif.label_parsing` when labels follow a repeated naming convention. The
parser combinators turn strings into typed `TokenResult`s; `NamingConventionIngress` turns
successful parses into `Record(rtype="token", fields={"label": ..., "tokens": [...]})`
records that a graph-building step can consume.

The local sources are:

- `docs/explanations/point-label-parsing.md`
- `notebooks/BMS_Point_Naming_Convention.ipynb`
- `buildingmotif/label_parsing/*`
- `buildingmotif/ingresses/naming_convention.py`
- `docs/guides/ingress-bacnet-to-brick.md`

The `BMS_Point_Naming_Convention.ipynb` notebook shows the intended loop:

1. define equipment and point abbreviation dictionaries;
2. encode the naming convention with `sequence`, `string`, `regex`, `constant`, `maybe`;
3. run `NamingConventionIngress(CSVIngress(...), custom_parser)`;
4. inspect `record.fields` token records;
5. call `dump_failed_labels()` and extend the suffix map by the biggest unparsed groups.

The docs mention "Semantic Graph Synthesis" as a future layer. In the current code, there
is no universal synthesis API. The practical path is:

`source records -> parser or row mapper -> token records -> custom GraphIngressHandler or TemplateIngress -> model -> validate`

```python
from buildingmotif.ingresses import CSVIngress, NamingConventionIngress
from buildingmotif.label_parsing.combinators import (
    COMMON_EQUIP_ABBREVIATIONS_BRICK,
    abbreviations,
    constant,
    maybe,
    regex,
    sequence,
    string,
)
from buildingmotif.label_parsing.parser import parse
from buildingmotif.label_parsing.tokens import Constant, Delimiter, Identifier
from buildingmotif.namespaces import BRICK

equip_abbreviations = abbreviations(COMMON_EQUIP_ABBREVIATIONS_BRICK)
point_abbreviations = abbreviations({
    "RoomTmp": BRICK.Room_Temperature_Sensor,
    "Room_RH": BRICK.Relative_Humidity_Sensor,
    "SaTmp": BRICK.Supply_Air_Temperature_Sensor,
    "OccCmd": BRICK.Occupancy_Command,
    "EffOcc": BRICK.Occupancy_Status,
    "ChwVlvPos": BRICK.Position_Sensor,
    "HwVlvPos": BRICK.Position_Sensor,
    "UnoccHtgSpt": BRICK.Unoccupied_Air_Temperature_Heating_Setpoint,
    "OccClgSpt": BRICK.Occupied_Air_Temperature_Cooling_Setpoint,
})

def custom_parser(target):
    return sequence(
        string(":", Delimiter),
        constant(Constant(BRICK.Building)),
        regex(r"[^_]+", Identifier),
        string("_", Delimiter),
        constant(Constant(BRICK.Air_Handling_Unit)),
        regex(r"[0-9a-zA-Z]+", Identifier),
        string(":", Delimiter),
        equip_abbreviations,
        regex(r"[0-9a-zA-Z]+", Identifier),
        string("_", Delimiter),
        maybe(sequence(regex(r"[A-Z]+[0-9]+", Identifier), string("_", Delimiter))),
        point_abbreviations,
    )(target)

source = CSVIngress(data="""label
:BuildingName_02:FCU503_ChwVlvPos
:BuildingName_02:FCU510_EffOcc
""")
ing = NamingConventionIngress(source, custom_parser)
for rec in ing.records:
    print(rec.fields)
ing.dump_failed_labels()

print(parse(custom_parser, ":BuildingName_02:FCU563_BO4_HighSpdFanOut").errors)
```

Use `dump_failed_labels()` early. It groups failures by the unparsed tail, which is exactly
what you need to extend the suffix map.

`results_to_tokens` pairs each `Constant` class token with the next `Identifier`. A final
point class token with no following identifier gets the full source label as its
identifier. This is why notebook output looks like:

```python
{
    "label": ":BuildingName_02:FCU503_ChwVlvPos",
    "tokens": [
        {"identifier": "BuildingName", "type": "https://brickschema.org/schema/Brick#Building"},
        {"identifier": "02", "type": "https://brickschema.org/schema/Brick#Air_Handling_Unit"},
        {"identifier": "503", "type": "https://brickschema.org/schema/Brick#Fan_Coil_Unit"},
        {"identifier": ":BuildingName_02:FCU503_ChwVlvPos", "type": "https://brickschema.org/schema/Brick#Position_Sensor"},
    ],
}
```

That token format is convenient but lossy: it does not preserve relationship semantics by
itself. Your graph builder must decide which token is the building, which is upstream
equipment, which is the owning equipment, and which is the point.

## Synthesizing graph triples from token records

There is no single universal semantic graph synthesis API because the right graph depends
on the source convention. A point-list build usually needs a small graph builder that:

- creates or reuses the equipment node;
- creates the point node from the real source label or point ID;
- asserts the verified Brick point class;
- links equipment to point with `brick:hasPoint`;
- adds `rdfs:label` and source-reference triples when available.

For bulk point-list builds, direct triples for point leaves are normal. Templates are still
valuable for equipment types and repeated equipment structure, but a CSV row that only says
"VAV-101_ZN-T is a zone temperature point on VAV-101" does not need a custom template just
to assert the point type and `hasPoint` edge.

```python
from rdflib import Graph, Literal, Namespace
from buildingmotif.namespaces import BRICK, RDF, RDFS

BLDG = Namespace("urn:bldg/")

def node_id(raw: str) -> str:
    return (
        raw.strip()
        .replace(" ", "_")
        .replace("/", "_")
        .replace(":", "_")
        .replace("-", "_")
    )

def add_point(g: Graph, equip_id: str, point_label: str, point_class):
    equip = BLDG[node_id(equip_id)]
    point = BLDG[node_id(point_label)]
    g.add((equip, RDF.type, BRICK.Equipment))  # replace with the verified equipment class
    g.add((point, RDF.type, point_class))
    g.add((point, RDFS.label, Literal(point_label)))
    g.add((equip, BRICK.hasPoint, point))
    return point
```

The equipment type should come from the parser or another evidence column when possible
(`VAV`, `AHU`, `FCU`, etc.). Use `brick:Equipment` only as a temporary placeholder and
expect validation to ask for a more specific class.

### Custom `GraphIngressHandler` for token records

When using `NamingConventionIngress`, attach a graph ingress that consumes its token
records. This mirrors BuildingMOTIF's ingress architecture and keeps parsing separate from
graph semantics:

```python
from rdflib import Graph, Literal, Namespace, URIRef
from buildingmotif.ingresses.base import GraphIngressHandler
from buildingmotif.namespaces import BRICK, RDF, RDFS

class TokenRecordToBrick(GraphIngressHandler):
    def __init__(self, upstream):
        self.upstream = upstream

    def graph(self, ns: Namespace) -> Graph:
        g = Graph()
        for rec in self.upstream.records:
            tokens = rec.fields["tokens"]

            # Convention-specific: for :Building_02:FCU503_Point, the last
            # equipment token owns the final point token.
            point_token = tokens[-1]
            equip_token = tokens[-2]

            equip = ns[equip_token["identifier"]]
            point = ns[node_id(point_token["identifier"])]
            equip_class = URIRef(equip_token["type"])
            point_class = URIRef(point_token["type"])

            g.add((equip, RDF.type, equip_class))
            g.add((point, RDF.type, point_class))
            g.add((point, RDFS.label, Literal(point_token["identifier"])))
            g.add((equip, BRICK.hasPoint, point))
        return g
```

This example intentionally leaves the convention-specific choice visible. In another
naming convention, the owner may be the first equipment token, a chain of equipment may
need `brick:feeds` or `brick:hasPart`, or the building/AHU token may represent location or
system membership rather than point ownership.

### Template ingress for structured records

If the parsed or tabular records line up with template parameters, use
`TemplateIngress`/`TemplateIngressWithChooser` instead of writing graph triples:

```python
from buildingmotif.ingresses import TemplateIngress

# record_ingress.records must produce fields that map to template parameters,
# or provide a mapper.
ingress = TemplateIngress(template, mapper=None, upstream=record_ingress)
graph = ingress.graph(BLDG)
```

This is best for equipment or assemblies with a reusable template body. For heterogeneous
rows, `TemplateIngressWithChooser` can choose a template from `rec.rtype` or parsed class
tokens. If all the row says is "this point belongs to this equipment and has this type",
direct point triples are clearer.

## Non-BMS inputs

If the user gives schedules, submittals, or existing metadata instead of BMS point labels,
do not force the label parser. Use the same steps:

- enumerate distinct source terms and columns;
- map them to verified Brick classes;
- preserve source identifiers;
- build graph fragments in small batches;
- validate after each batch.

Parser combinators are best when one compact grammar captures most rows. Hand-written
mapping code is better when the source is already structured or when each row has explicit
columns like `equipment`, `point_type`, `units`, and `io_type`.

For table-like sources, normalize rows into the same internal fields you would have gotten
from a parser:

```python
def classify_row(row):
    token = row["point_type"].strip()
    point_class = SOURCE_TO_BRICK[token]  # values verified via brick_vocabulary.md
    return {
        "equipment": row["equipment"],
        "equipment_class": EQUIP_TO_BRICK.get(row.get("equip_type"), BRICK.Equipment),
        "point_label": row["point_id"] or row["object_name"],
        "point_class": point_class,
        "units": row.get("units"),
        "io_type": row.get("io_type"),
    }
```

Then feed those records to the same `add_point` helper or graph ingress. This keeps the
workflow uniform without pretending every source is a BMS label.

## Reporting

Report mapping decisions in building terms:

- "Mapped `RoomTmp` to `brick:Room_Temperature_Sensor` for 73 FCU rows."
- "Left `HighSpdFanOut` unresolved; it appears in 11 labels and needs command/status
  disambiguation."
- "Verified `brick:Run_Status` exists; `brick:Run_Status_Sensor` does not."

Ask the user when the source does not distinguish sensor vs setpoint, command vs status,
or physical point vs software point.
