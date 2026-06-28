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
