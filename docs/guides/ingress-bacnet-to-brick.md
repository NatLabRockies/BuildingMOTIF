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

# BACnet to Brick

```{margin}
```{important}
This tutorial assumes that `BuildingMOTIF` has already been installed in the local environment with the `bacnet-ingress` option **and** that the user has access to a BACnet network with descriptive names.
```

The purpose of this how-to document is to demonstrate the creation of a functional Brick model from a BACnet network. This will be accomplished by using BuildingMOTIF's "ingresses" to import a BACnet network as a basic Brick model, and then using BuildingMOTIF to augment the basic Brick model with more descriptive metadata.

## External Setup

Make sure you have network access to a BACnet network, and that you are aware on what IP address that BACnet network can be reached.
For this tutorial, we will use [`docker compose`](https://docs.docker.com/compose/) to run a virtual BACnet network which we can scan and generate a Brick model for; see the sub-section below.

```{margin}
```{note}
Another virtual BACnet network to try is the [virtual machine setup in the simulated digital twin repository](https://github.com/gtfierro/simulated-digital-twin/tree/main/virtual-machine).
```

### BACnet Network Setup

This cell sets up a virtual BACnet network that can be run locally to make the rest of the tutorial work as expected.
You do not need to run this if you are connecting to a real BACnet network.

<details>

```{code-cell} python3
import subprocess
import shlex
with open('virtual_bacnet.py', 'w') as f:
    f.write('''
import random
import sys

from bacpypes.app import BIPSimpleApplication
from bacpypes.consolelogging import ConfigArgumentParser
from bacpypes.core import run
from bacpypes.debugging import ModuleLogger, bacpypes_debugging
from bacpypes.local.device import LocalDeviceObject
from bacpypes.object import AnalogInputObject
from bacpypes.service.device import DeviceCommunicationControlServices
from bacpypes.service.object import ReadWritePropertyMultipleServices

_debug = 0
_log = ModuleLogger(globals())


@bacpypes_debugging
class VirtualBACnetApp(
    BIPSimpleApplication,
    ReadWritePropertyMultipleServices,
    DeviceCommunicationControlServices,
):
    pass


class VirtualDevice:
    def __init__(self, host: str = "0.0.0.0"):
        parser = ConfigArgumentParser(description=__doc__)
        args = parser.parse_args()
        self.device = LocalDeviceObject(ini=args.ini)
        self.application = VirtualBACnetApp(self.device, host)

        # setup points
        self.points = {
            "SupplyTempSensor": AnalogInputObject(
                objectName="VAV-1/SAT",
                objectIdentifier=("analogInput", 0),
                presentValue=random.randint(1, 100),
            ),
            "HeatingSetpoint": AnalogInputObject(
                objectName="VAV-1/HSP",
                objectIdentifier=("analogInput", 1),
                presentValue=random.randint(1, 100),
            ),
            "CoolingSetpoint": AnalogInputObject(
                objectName="VAV-1/CSP",
                objectIdentifier=("analogInput", 2),
                presentValue=random.randint(1, 100),
            ),
            "ZoneTempSensor": AnalogInputObject(
                objectName="VAV-1/Zone",
                objectIdentifier=("analogInput", 3),
                presentValue=random.randint(1, 100),
            ),
        }

        for p in self.points.values():
            self.application.add_object(p)

        run()


if __name__ == "__main__":
    VirtualDevice(sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0")
''')

with open('Dockerfile.bacnet', 'w') as f:
    f.write('''FROM ubuntu:latest as base

WORKDIR /opt

RUN apt update \
    && apt install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install BACpypes

COPY virtual_bacnet.py virtual_bacnet.py
COPY BACpypes.ini .''')

with open('BACpypes.ini', 'w') as f:
    f.write('''[BACpypes]
objectName: VirtualBACnet
#address: 172.17.0.1/24
objectIdentifier: 599
maxApduLengthAccepted: 1024
segmentationSupported: segmentedBoth
vendorIdentifier: 15''')


with open('docker-compose-bacnet.yml','w') as f:
    f.write('''version: "3.4"
services:
  device:
    build:
      dockerfile: Dockerfile.bacnet
    networks:
      bacnet:
        ipv4_address: 172.24.0.3
    command: "python3 virtual_bacnet.py"
networks:
  bacnet:
    ipam:
      driver: default
      config:
        - subnet: "172.24.0.0/16"
          gateway: "172.24.0.1"''')
docker_compose_start = shlex.split("docker compose -f docker-compose-bacnet.yml up -d")
subprocess.run(docker_compose_start)
```

</details>

## BuildingMOTIF Setup

Like the previous tutorial, we'll create an in-memory BuildingMOTIF instance and load some libraries.

```{code-cell} python3
import logging
from rdflib import Namespace
from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model, Library
from buildingmotif.namespaces import BRICK # import this to make writing URIs easier

# in-memory instance
bm = BuildingMOTIF("sqlite://", log_level=logging.ERROR)

# create the namespace for the building
BLDG = Namespace('urn:bldg/')

# create the building model
model = Model.create(BLDG, description="This is a test model for a simple building")

# load some libraries we will use later
brick = Library.from_ontology("https://github.com/BrickSchema/Brick/releases/download/nightly/Brick.ttl")
```

## Pulling in BACnet Metadata

We use the `buildingmotif.ingresses.bacnet.BACnetNetwork` ingress module to pull structured information from the BACnet network. The ingress module scrapes the BACnet network and produces a set of "records" which correspond to the individual BACnet Devices and Objects discovered in the network.

```{code-cell} python3
from buildingmotif.ingresses.bacnet import BACnetNetwork

bacnet = BACnetNetwork("172.24.0.1/32") # don't change this if you are using the docker compose setup
for rec in bacnet.records:
    print(rec)
```

Each of these records has an `rtype` field, which is used by the ingress implementation to differentiate between different kinds of records; here it differentiates between BACnet Devices and BACnet Objects, which have different expressions in Brick. The `fields` attribute cotnains arbitrary key-value pairs, again defined by the ingress implementation, which can be interpreted by another ingress module.

## BACnet to Brick: an Initial Model

We use the `buildingmotif.ingresses.brick.BACnetToBrickIngress` ingress module to turn the `Record`s from the `BACnetNetwork` ingress into a Brick model. This is as simple as choosing a namespace for the entities (this is usually just the same namespace used for the Model, i.e. `BLDG` above) and connecting our new ingress module instance to the existing BACnet network ingress module.


```{code-cell} python3
from buildingmotif.ingresses.brick import BACnetToBrickIngress

# create the Brick ingress module and connect to the existing bacnet module
brick2bacnet = BACnetToBrickIngress(bm, bacnet)
# creates the graph from the BACnet records
bacnet_network_graph = brick2bacnet.graph(BLDG)
# add the graph to our model
model.add_graph(bacnet_network_graph)
```

We can now take a look at the resulting graph:

```{code-cell} python3
print(model.graph.serialize())
```

We can now see the devices and their objects represented in the model. However, the metadata is not very descriptive. All of the BACnet objects have been inferred to be instances of `brick:Point`.
In the next step, we will use BuildingMOTIF to incorporate our other knowledge about the building to augment this Brick model with more descriptive metadata.

## Augmenting the Initial Model: Our Strategy

There is [existing documentation](https://docs.brickschema.org/lifecycle/creation.html) on techniques for inferring Brick metadata from point labels. Below, we will show how a simple Python-based point type inference module can be implemented by extending BuildingMOTIF's existing ingress module implementation. Then, we will use BuildingMOTIF's templates to incorporate the inferred points into a bigger model.

## Point Type Inference

For completeness, here are the names of the 4 points in the BACnet network scanned above (these will be different if you are not using the provided `docker compose` setup):

- `VAV-1/SAT`
- `VAV-1/HSP`
- `VAV-1/CSP`
- `VAV-1/Zone`

Squinting at these point names, we might see how we can divide each name into sections: `{equip name} / {point type}`. Let's write Python code to pull out the Brick metadata we can from these labels.

```python3
from rdflib import Graph, URIRef
from buildingmotif.namespaces import RDF, BRICK
def parse_label(label: str, output: Graph):
    """Parses the label and puts the resulting triples in the provided graph."""
    parts = label.split('/')
    equip_name, point_type = parts

    if point_type == 'SAT':
        brick_class = BRICK.Supply_Air_Temperature_Sensor
    elif point_type == 'HSP':
        brick_class = BRICK.Zone_Air_Heating_Temperature_Setpoint
    elif point_type == 'CSP':
        brick_class = BRICK.Zone_Air_Cooling_Temperature_Setpoint
    elif point_type == 'Zone':
        brick_class = BRICK.Zone_Air_Temperature_Sensor
    else:
        raise Exception(f"Unknown point type! {point_type}")

    output.add((BLDG[label], RDF.type, brick_class))
    output.add((BLDG[equip_name], BRICK.hasPoint, BLDG[label]))
    output.add((BLDG[equip_name], RDF.type, BRICK.Equipment)) # not sure what type this is yet, choose 'Equipment' for now
```

We can wrap this function in an ingress module so it is easy to reuse later. This just requires a little bit of moving some code around

```{code-cell} python3
from rdflib import Graph, URIRef
from buildingmotif.namespaces import RDF, BRICK
from buildingmotif.ingresses.base import GraphIngressHandler

class MyPointParser(GraphIngressHandler):
    def __init__(self, bm: BuildingMOTIF, upstream: GraphIngressHandler):
        self.bm = bm
        self.upstream = upstream # this will point to our BACnetToBrickIngress handler

    def parse_label(self, label: str, entity: URIRef, output: Graph):
        """Parses the label and puts the resulting triples in the provided graph.
        Adds the type to the indicated entity"""
        parts = label.split('/')
        equip_name, point_type = parts

        if point_type == 'SAT':
            brick_class = BRICK.Supply_Air_Temperature_Sensor
        elif point_type == 'HSP':
            brick_class = BRICK.Zone_Air_Heating_Temperature_Setpoint
        elif point_type == 'CSP':
            brick_class = BRICK.Zone_Air_Cooling_Temperature_Setpoint
        elif point_type == 'Zone':
            brick_class = BRICK.Zone_Air_Temperature_Sensor
        else:
            raise Exception(f"Unknown point type! {point_type}")

        output.add((entity, RDF.type, brick_class))
        output.add((BLDG[equip_name], BRICK.hasPoint, entity))
        output.add((BLDG[equip_name], RDF.type, BRICK.Equipment)) # not sure what type this is yet, choose 'Equipment' for now

    def graph(self, ns: Namespace) -> Graph:
        """the method we override to implement a GraphIngressHandler"""
        output_graph = Graph()
        bacnet_graph = self.upstream.graph(ns)
        point_labels = bacnet_graph.query("""
            SELECT ?entity ?label WHERE {
                ?entity <https://brickschema.org/schema/ref#hasExternalReference> ?ref .
                ?ref <http://data.ashrae.org/bacnet/2020#object-name> ?label
            }""")
        for entity, label in point_labels:
            # infer type for each
            self.parse_label(label, entity, output_graph)

        return output_graph
```

Now we can invoke our ingress module:

```{code-cell} python3
# create the Brick ingress module and connect to the existing bacnet module
point_ingress = MyPointParser(bm, brick2bacnet)
# creates the graph from the BACnet records
augmented_graph = point_ingress.graph(BLDG)
# add the graph to our model
model.add_graph(augmented_graph)
```

and display the resulting model

```{code-cell} python3
print(model.graph.serialize())
```

We can now see that the points in our model have more descriptive Brick types. We have also added the relationship between the points and the equipment.

It is important to note that this particular ingress we have dveloped is specific to the idiosyncratic naming within this particular BACnet network.
In the future, BuildingMOTIF will incorporate more sophisticated inference mechanisms; for now, consider the above as an example of how to interact with the BACnet ingress.

<details>
Here we teardown the BACnet network we created

```{code-cell} python3
docker_compose_stop = shlex.split("docker compose -f docker-compose-bacnet.yml down")
subprocess.run(docker_compose_stop)
```
</details>
