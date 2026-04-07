import logging

from buildingmotif.building_motif.building_motif import (  # type: ignore # noqa
    BuildingMOTIF,
    get_building_motif,
)

logging.getLogger("buildingmotif").addHandler(logging.NullHandler())
