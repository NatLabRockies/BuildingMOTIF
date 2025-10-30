import logging

from buildingmotif.ingresses.base import Record  # noqa
from buildingmotif.ingresses.csvingress import CSVIngress  # noqa
from buildingmotif.ingresses.naming_convention import NamingConventionIngress  # noqa
from buildingmotif.ingresses.semantic_graph_synthesis import (  # noqa
    SemanticGraphSynthesizerIngress,
)
from buildingmotif.ingresses.template import (  # noqa
    TemplateIngress,
    TemplateIngressWithChooser,
)

try:
    from buildingmotif.ingresses.brick import (  # noqa
        BACnetNetwork,
        BACnetToBrickIngress,
    )
except ImportError as e:
    logging.warning(f"Could not import BACnet ingresses: {e}")
