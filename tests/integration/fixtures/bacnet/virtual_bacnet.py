import logging
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
        logging.basicConfig(level=logging.INFO)

        _log.info("Starting Virtual BACnet device")
        _log.debug("Parsed arguments: %s", args)
        if not getattr(args, "ini", None):
            raise ValueError("BACpypes configuration file (--ini) is required")
        _log.info("Using configuration ini: %s", args.ini)

        self.device = LocalDeviceObject(ini=args.ini)
        _log.info(
            "Created LocalDeviceObject name=%s identifier=%s",
            self.device.objectName,
            getattr(self.device, "objectIdentifier", None),
        )
        self.application = VirtualBACnetApp(self.device, host)
        # ensure protocol services advertised match application capabilities
        # try:
        #    self.device.protocolServicesSupported = (
        #        self.application.get_services_supported()
        #    )
        # except AttributeError:
        #    _log.warning("Unable to set protocolServicesSupported on LocalDeviceObject")
        # else:
        #    _log.debug(
        #        "protocolServicesSupported: %s",
        #        self.device.protocolServicesSupported,
        #    )

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

        for name, point in self.points.items():
            self.application.add_object(point)
            _log.info(
                "Registered BACnet object %s identifier=%s value=%s",
                name,
                point.objectIdentifier,
                getattr(point, "presentValue", None),
            )

        _log.info("Virtual device listening on host %s", host)
        run()


if __name__ == "__main__":
    VirtualDevice(sys.argv[1] if len(sys.argv) > 1 else "0.0.0.0")
