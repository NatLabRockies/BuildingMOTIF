# configure logging output
import asyncio
import logging
import warnings
from functools import cached_property
from typing import Any, Dict, List, Optional, Tuple

try:
    import BAC0
except ImportError:
    logging.critical(
        "Install the 'bacnet-ingress' module, e.g. 'pip install buildingmotif[bacnet-ingress]'"
    )


from buildingmotif.ingresses.base import Record, RecordIngressHandler

# We do this little rigamarole to avoid BAC0 spitting out a million
# logging messages warning us that we changed the log level, which
# happens when we go through the normal BAC0 log level procedure
logger = logging.getLogger("BAC0_Root.BAC0.scripts.Base.Base")
logger.setLevel(logging.ERROR)


class BACnetNetwork(RecordIngressHandler):
    def __init__(
        self,
        ip: Optional[str] = None,
        *,
        discover_kwargs: Optional[Dict[str, Any]] = None,
        global_broadcast: bool = True,
        ping: bool = False,
        device_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Reads a BACnet network to discover the devices and objects therein

        :param ip: IP/mask for the host which is scanning the network,
                    defaults to None
        :type ip: Optional[str], optional
        :param discover_kwargs: Optional kwargs forwarded to BAC0._discover.
        :type discover_kwargs: Optional[Dict[str, Any]]
        :param global_broadcast: Whether to issue global broadcast Who-Is requests.
        :type global_broadcast: bool
        :param ping: Whether to ping devices during connect; defaults to False.
        :type ping: bool
        :param device_kwargs: Optional kwargs forwarded to BAC0.device.
        :type device_kwargs: Optional[Dict[str, Any]]
        """
        self.objects: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
        discover_kwargs = dict(discover_kwargs or {})
        discover_kwargs.setdefault("global_broadcast", global_broadcast)
        self._run_async(
            self._collect_objects(
                ip=ip,
                discover_kwargs=discover_kwargs,
                ping=ping,
                device_kwargs=device_kwargs or {},
            )
        )

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(coro)
            loop.run_until_complete(loop.shutdown_asyncgens())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    async def _collect_objects(
        self,
        *,
        ip: Optional[str],
        discover_kwargs: Dict[str, Any],
        ping: bool,
        device_kwargs: Dict[str, Any],
    ):
        device_kwargs.setdefault("poll", 0)

        async with BAC0.start(ip=ip, ping=ping) as bacnet:
            await bacnet._discover(**discover_kwargs)

            discovered = getattr(bacnet, "discoveredDevices", None)
            if not discovered:
                warnings.warn("BACnet ingress could not find any BACnet devices")
                return

            for (address, device_id) in discovered:
                device = await BAC0.device(address, device_id, bacnet, **device_kwargs)
                objects: List[Dict[str, Any]] = []

                for bobj in device.points:
                    obj = bobj.properties.asdict
                    self._clean_object(obj)
                    objects.append(obj)

                self.objects[(address, device_id)] = objects

    def _clean_object(self, obj: Dict[str, Any]):
        if "name" in obj:
            # remove trailing/leading whitespace from names
            obj["name"] = obj["name"].strip()

    @cached_property
    def records(self) -> List[Record]:
        """
        Returns a list of the BACnet devices and objects discovered in the
        BACnet network. The 'rtype' field of each Record is either "Device"
        for a BACnet Device or "Object" for a BACnet Object. The 'fields'
        field contains the key-value BACnet properties associated with that
        device or object.

        :return: list of BACnet devices and objects, each expressed as a Record
        :rtype: List[Record]
        """
        records = []
        # make devices
        for (address, device_id) in self.objects.keys():
            records.append(
                Record(
                    rtype="Device",
                    fields={"address": address, "device_id": device_id},
                )
            )
        for (address, device_id), objs in self.objects.items():
            for obj in objs:
                fields = obj.copy()
                del fields["device"]
                fields["device_id"] = device_id
                records.append(
                    Record(
                        rtype="Object",
                        fields=fields,
                    )
                )
        return records
