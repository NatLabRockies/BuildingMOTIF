# 223P (`s223:`) vocabulary and modeling patterns

ASHRAE 223P models a building as an explicit **topology**: equipment connected to equipment
through typed connection points and connections, with properties and sensors attached at
specific points in that graph. This is a different shape than Brick's `hasPoint`/
`hasLocation` idiom (`brick_vocabulary.md`) — 223P wants you to say *how* things are
physically connected, not just *that* a piece of equipment has a point. Reach for this file
when the user's model or shapes target the `s223:` namespace (`http://data.ashrae.org/standard223#`),
mention 223P/s223 by name, or need HVAC system topology (ducts, pipes, connection points)
rather than a flat point list.

Current compiled ontology: <https://open223.info/223p.ttl>

Everything below is verified against the ontology's own `rdfs:comment` definitions and the
worked templates in `libraries/ashrae/223p/nrel-templates/` on disk — quoted, not guessed.

## Loading 223P

223P is **not a builtin library** — unlike `brick/Brick.ttl`, there is no packaged
`223p/223p.ttl` resource inside `buildingmotif/libraries/`. As an installed-package user
you need your own copy of the ontology; download the current version from
<https://open223.info/223p.ttl>, then load it exactly like Brick:

```python
from buildingmotif.dataclasses import Library
from buildingmotif.namespaces import S223, bind_prefixes  # S223 is already defined for you

s223 = Library.from_ontology("path/to/223p.ttl", run_shacl_inference=False)
s223_graph = s223.get_shape_collection().graph
```

Same load-order rule as Brick: load 223P **before** anything whose templates/shapes depend
on its classes.

**Reusable templates** (duct, damper, fan, AHU, zone/space, sensor, …) are a separate
concern from the ontology itself — 223P's own `.ttl` gives you shapes and class
definitions, not a template library. This repo's `libraries/ashrae/223p/nrel-templates/`
has a hand-written set (see below), but like `guideline36`/`chiller-plant` it is **repo-only,
not shipped in the package** — same fallback options as any other sample library (clone the
repo, a `git:` entry in `libraries.yml`, or write your own inline templates following the
patterns below). See `SKILL.md`'s "Where libraries live" section.

## Core concepts, verified from the ontology

| Term | Definition (from `223p.ttl`'s `rdfs:comment`) |
|---|---|
| `s223:Equipment` | "a mechanical device designed to accomplish a specific task, or a complex device that contains component pieces of Equipment." Unlike `System`, Equipment has `ConnectionPoint`s and participates in medium flow. |
| `s223:System` | "a logical grouping (collection) of Equipment for some functional or system reason... A System does **not** participate in Connections." |
| `s223:Connectable` (abstract) | "Equipment, DomainSpace, or Junction that can be connected via ConnectionPoints and Connections." |
| `s223:ConnectionPoint` (abstract) | "the abstract representation of the flange, wire terminal, or other physical feature where a connection is made." Concrete subclasses: `InletConnectionPoint`, `OutletConnectionPoint`, `BidirectionalConnectionPoint`. |
| `s223:Connection` | "a physical thing (e.g., pipe, duct, or wire) used to convey some Medium... between two connectable things." Has two or more `ConnectionPoint`s. |
| `s223:Junction` | used when a branching/intersection point within a Connection needs to be individually addressable (e.g. as a sensor's observation location). |
| `s223:PhysicalSpace` | architectural concept — "a room, a collection of rooms... or any physical space." |
| `s223:DomainSpace` | logical, per-domain member of a `Zone` (HVAC, Lighting, …); must be enclosed by a `PhysicalSpace`. |
| `s223:Zone` | "a logical grouping (collection) of domain spaces... to identify a domain of control." |

**Never instantiate an abstract class directly** — `ConnectionPoint` and `Connectable` are
both `s223:abstract true`. Assert `s223:InletConnectionPoint`/`OutletConnectionPoint`/
`BidirectionalConnectionPoint`, never bare `a s223:ConnectionPoint`.

**`Equipment` vs `System` is a common trap.** If something has ConnectionPoints and
participates in the physical flow of a medium, it's `Equipment` (even a composite one, via
`s223:contains`). If it's a logical grouping with no physical connections of its own — "the
chilled water system" as a label over a set of equipment — it's a `System`.

## The connection pattern

Three relations do the topology work, verified from their own `rdfs:comment`s:

- **`s223:hasConnectionPoint`** (inverse `isConnectionPointOf`) — binds a `Connectable`
  (Equipment/DomainSpace/Junction) to its `ConnectionPoint`s.
- **`s223:cnx`** — a *symmetric* property "used to associate adjacent entities in a
  connection path (comprised of Equipment-ConnectionPoint-Connection-ConnectionPoint-Equipment
  sequences)." This is the relation that actually wires a `Connection` (a `Duct`, `Pipe`,
  etc.) to the `ConnectionPoint`s on either end of it.
- **`s223:mapsTo`** — "associate a ConnectionPoint of a Connectable to a corresponding
  ConnectionPoint of the one containing it" (the equipment-*containment* pattern, via
  `s223:contains`): when equipment A contains sub-equipment B, and B's connection point is
  what A exposes externally, A's own connection point `mapsTo` B's internal one.

There's also a plain **`s223:connected`** (symmetric, no direction) and directional
**`s223:connectedTo`**/`connectedFrom` for cases where you want topology without an
explicit `Connection` instance — but the `cnx`-through-a-`Connection` pattern below is what
this repo's templates use throughout, so default to that.

Worked example (from `libraries/ashrae/223p/nrel-templates/devices.yml` and
`systems.yml`) — a damper feeding into a duct:

```turtle
@prefix s223: <http://data.ashrae.org/standard223#> .

:damper1 a s223:Damper ;
  s223:hasConnectionPoint :damper1-in, :damper1-out ;
  s223:hasProperty :damper1-command .

:damper1-out a s223:OutletConnectionPoint ; s223:hasMedium s223:Fluid-Air .
:downstream-in a s223:InletConnectionPoint ; s223:hasMedium s223:Fluid-Air .

:duct1 a s223:Duct ;
  s223:hasMedium s223:Fluid-Air ;
  s223:cnx :damper1-out, :downstream-in .
```

Note what's *not* here: the duct doesn't point at the damper or the downstream equipment
directly — it `cnx`'s their `ConnectionPoint`s, and each equipment separately declares that
`ConnectionPoint` via `hasConnectionPoint`. This is the graph shape validation expects.

**Composite equipment** (an AHU containing a fan, coils, filters — `s223:contains`) chains
its internal pieces together with the same `cnx`-through-`Connection` pattern internally,
then exposes its own external connection points with `mapsTo`:

```turtle
:ahu1 a s223:AirHandlingUnit ;
  s223:contains :ahu1-fan, :ahu1-coil ;
  s223:hasConnectionPoint :ahu1-supply .

:ahu1-coil-out s223:mapsTo :ahu1-supply .   # the AHU's own outlet IS the coil's outlet
```

## Properties and sensors

- **`s223:hasProperty`** — "associates any 223 Concept with a Property." Properties are
  typed by *what kind of value* they carry and *who can change them*, not by what physical
  quantity they represent — that's QUDT's job:
  - `s223:QuantifiableObservableProperty` — numeric, read-only (a temperature reading).
  - `s223:QuantifiableActuatableProperty` — numeric, settable (a setpoint or command).
  - `s223:EnumeratedObservableProperty` / `EnumeratedActuatableProperty` — same
    read-only/settable split, for non-numeric (enumerated) values (an alarm state, a
    start/stop command).
- Attach the physical quantity **on the Property node itself**, with QUDT:
  ```turtle
  :damper1-command a s223:QuantifiableActuatableProperty ;
    qudt:hasQuantityKind quantitykind:DimensionlessRatio ;
    qudt:hasUnit unit:PERCENT .
  ```
- **`s223:Sensor`** "observes an ObservableProperty... which may be quantifiable... or
  Enumerable." Wire a sensor to what it measures and where with `s223:observes` (binds the
  sensor to the `Property`) and `s223:hasObservationLocation` (binds it to the
  `Connectable`/`Connection`/`ConnectionPoint` it's physically measuring at):
  ```turtle
  :damper1-command-sensor a s223:Sensor ;
    s223:observes :damper1-command ;
    s223:hasObservationLocation :damper1 .
  ```
  A multi-property device (temperature + humidity) is modeled as **containing** one
  single-property `Sensor` per property (`s223:contains`), not one sensor observing two
  properties — the one-property-per-sensor rule is load-bearing, not a simplification.
- Calculated (not observed) properties use `s223:Function` with `s223:hasInput`/
  `s223:hasOutput` pointing at `Property` nodes, and are plain `QuantifiableProperty`/
  `EnumerableProperty` — **not** the `Observable`/`Actuatable` subtypes, since nothing
  senses or actuates them directly.

## Enumerated values: roles, domains, media

`s223:hasRole`, `s223:hasDomain`, and `s223:hasMedium` all point at **individuals**, not
classes — don't `a`-type against these, check/assert them as values:

- **`s223:hasRole`** — role of an Equipment/Connection/ConnectionPoint/System, e.g.
  `s223:Role-Heating`, `Role-Cooling`, `Role-Return`, `Role-Supply`, `Role-Economizer`,
  `Role-Controller`. Full set: `EnumerationKind-Role` in the ontology.
- **`s223:hasDomain`** — domain of a `Zone`/`DomainSpace`, e.g. `s223:Domain-HVAC`,
  `Domain-Lighting`, `Domain-Electrical`, `Domain-Plumbing`. Full set:
  `EnumerationKind-Domain`.
- **`s223:hasMedium`** — what's flowing through a `Connection`, e.g. `s223:Fluid-Air`,
  `s223:Fluid-Water`, `s223:Fluid-Refrigerant`, or more specific water types like
  `s223:Water-ChilledWater`, `Water-HotWater`, `Water-Steam`.

## Discover and verify before asserting

Same discipline as `brick_vocabulary.md`: don't guess a class or enumerated-value IRI, look
it up. 223P classes are `a s223:Class, sh:NodeShape` (not `owl:Class`) — adjust the query
accordingly:

```python
from buildingmotif.namespaces import OWL, RDF, RDFS, S223

def s223_class(local_name: str):
    cls = S223[local_name]
    if (cls, RDF.type, S223.Class) not in s223_graph:
        return None
    deprecated = next(s223_graph.objects(cls, OWL.deprecated), None)
    if deprecated is not None and deprecated.toPython():
        print(f"WARNING: {local_name} is deprecated in this 223P version.")
    return cls

def describe_s223(local_name: str):
    node = S223[local_name]
    for comment in s223_graph.objects(node, RDFS.comment):
        print(str(comment)[:500])

def subclasses_of_s223(local_name: str, limit: int = 100):
    root = S223[local_name]
    q = "SELECT DISTINCT ?cls WHERE { ?cls rdfs:subClassOf+ ?root } ORDER BY ?cls"
    rows = s223_graph.query(q, initNs={"rdfs": RDFS}, initBindings={"root": root})
    return [str(r.cls).split("#")[-1] for r in rows][:limit]

describe_s223("Damper")
print(subclasses_of_s223("HeatExchanger"))
```

List the enumerated instances the same way — they're individuals, not a class hierarchy,
so the simplest robust check is local-name prefix over every node in the graph:

```python
def s223_enum_values(prefix: str):
    return sorted(
        str(s).split("#")[-1] for s in s223_graph.all_nodes()
        if str(s).startswith(str(S223)) and str(s).split("#")[-1].startswith(prefix)
    )

print(s223_enum_values("Role-"))    # Role-Heating, Role-Cooling, Role-Return, ...
print(s223_enum_values("Domain-"))  # Domain-HVAC, Domain-Lighting, ...
print(s223_enum_values("Fluid-"))   # Fluid-Air, Fluid-Water, ...
```

## Prefer non-deprecated terms — including QUDT units

The `223p.ttl` snapshot checked into this repo has no `s223:`-namespaced class marked
`owl:deprecated true` — but `s223_class(...)` above already checks for it on every lookup
(some future 223P revision may deprecate a class the same way Brick does; the check is
cheap insurance either way, and now you get it for free).

**Where deprecation actually bites in 223P today is QUDT**, not `s223:` classes — every
`QuantifiableObservableProperty`/`QuantifiableActuatableProperty` you write carries a
`qudt:hasQuantityKind`/`qudt:hasUnit` pair, and QUDT has its own deprecated
`quantitykind:`/`unit:` terms (`qudt:deprecated true` + `dcterms:isReplacedBy` pointing at
the replacement). `223p.ttl` even ships two SHACL rules
(`DeprecatedPropertyConstraint`, `DeprecationConstraint`) that flag deprecated-QUDT-term
usage automatically — **but at `sh:severity sh:Info`**, so it won't show up in
`ctx.get_reasons_with_severity(SH.Violation)` and won't fail `ctx.valid`. Check the
quantity kind/unit yourself before picking one:

```python
from rdflib.namespace import DCTERMS
from buildingmotif.namespaces import QUDT, QUDTQK

def qudt_check(term):  # term: a QUDTQK.X quantity kind or a unit IRI
    deprecated = next(s223_graph.objects(term, QUDT.deprecated), None)
    if deprecated is not None and deprecated.toPython():
        replacement = next(s223_graph.objects(term, DCTERMS.isReplacedBy), None)
        print(f"WARNING: {term} is a deprecated QUDT term. Use {replacement} instead.")
        return replacement or term
    return term

qudt_check(QUDTQK.SurgeImpedanceOfTheMedium)  # example: check before using
```

(This assumes the QUDT terms are resolved into the same graph you're querying — true after
loading `223p.ttl`, since it vendors the QUDT definitions it uses; for a unit/quantity kind
that only exists in a separately-fetched QUDT ontology, resolve imports first per
`ontology_imports.md`.)

## Gotchas

- **Unconnected `ConnectionPoint`s fail validation.** A model where a `ConnectionPoint`
  exists but has neither an outgoing `cnx` nor is the target of some equipment's
  `hasConnectionPoint` will not conform — every connection point needs to terminate
  *somewhere*. If a real connection point genuinely leaves the scope of what you're
  modeling (e.g. a duct exiting the building), terminate it deliberately rather than
  leaving it dangling:
  ```python
  from rdflib import URIRef
  from buildingmotif.namespaces import RDF, S223
  plug = URIRef("urn:plug/1")
  g.add((loose_connection_point, S223.cnx, plug))
  g.add((plug, RDF.type, S223.Connectable))
  ```
- **`ConnectionPoint`/`Connectable` are abstract** — see above. Validation failures naming
  these directly mean you asserted the abstract class instead of a concrete subclass.
- **Role/Domain/Medium are values, not types.** A shape requirement phrased as "must have a
  heating role" is `sh:hasValue s223:Role-Heating` on `s223:hasRole`, not a class check.
- **`System` never gets `hasConnectionPoint`.** If validation wants a `ConnectionPoint` on
  something you modeled as a `System`, that's a sign it should be `Equipment` (or a
  composite `Equipment` that `contains` the pieces), not a `System`.

## Output to produce for the user

Same as `brick_vocabulary.md`: report verified class/role/domain/medium mappings, name any
guesses you rejected because the IRI didn't check out, and flag unresolved source tokens
rather than forcing them into a coarse class. For topology specifically, also report the
connection *path* you modeled (equipment → connection point → connection → connection point
→ equipment) so the user can confirm it matches the physical system, not just that the
model validates.
