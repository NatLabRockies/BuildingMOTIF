from rdflib import Graph, Literal, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library
from buildingmotif.ingresses.bacnet import BACnetNetwork
from buildingmotif.ingresses.base import GraphIngressHandler


def _clean_uri(n) -> str:
    if isinstance(n, str):
        return n.replace(" ", "_")
    return str(n)


class BACnetToBrickIngress(GraphIngressHandler):
    """Turns a BACnetNetwork RecordIngressHandler into a Brick model"""

    BNS = Namespace("urn:brick_bacnet_scan/")

    def __init__(self, bm: BuildingMOTIF, upstream: BACnetNetwork):
        """Create a new ignress handler for turning a BACnet network scrape
        into a Brick model

        :param bm: BuildingMOTIF instance
        :type bm: BuildingMOTIF
        :param upstream: the BACnetNetwork ingress handler to ingest from
        :type upstream: BACnetNetwork
        """
        super().__init__(bm)
        self.upstream = upstream
        self.bacnet_lib = Library.load(directory="bacnet")
        self.device_template = self.bacnet_lib.get_template_by_name("brick-device")
        self.object_template = self.bacnet_lib.get_template_by_name("brick-point")

    def graph(self, ns: Namespace) -> Graph:
        """Generates a Brick graph from the BACnet network with all entities
        placed in the given namespace.

        :param ns: Namespace for all inferred entities
        :type ns: Namespace
        :return: RDF graph containing a Brick model of the BACnet network
        :rtype: Graph
        """
        g = Graph()
        # ensure 'ns' is a Namespace or URI forming won't work
        if not isinstance(ns, Namespace):
            ns = Namespace(ns)
        records = self.upstream.records
        assert records is not None
        for record in records:
            if record.rtype == "Device":
                dev = record.fields
                device_id = dev["device_id"]
                name = _clean_uri(device_id) or _clean_uri(dev["address"])
                g += self.device_template.substitute(
                    {
                        "name": ns[name],
                        "instance-number": Literal(device_id),
                        "address": Literal(dev["address"]),
                    }
                ).to_graph()
            elif record.rtype == "Object":
                point = record.fields
                device_id = point["device_id"]
                g += self.object_template.substitute(
                    {
                        "name": ns[f"{_clean_uri(point['name'])}-{point['address']}"],
                        "identifier": Literal(f"{point['type']},{point['address']}"),
                        "obj-name": Literal(point["name"]),
                        "device": ns[_clean_uri(device_id)],
                    }
                ).to_graph()

        return g
