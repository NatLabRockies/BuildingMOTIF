# BuildingMOTIF

[![codecov](https://codecov.io/gh/NatLabRockies/BuildingMOTIF/branch/main/graph/badge.svg?token=HAFSYH45NX)](https://codecov.io/gh/NatLabRockies/BuildingMOTIF)
[![Documentation Status](https://readthedocs.org/projects/buildingmotif/badge/?version=latest)](https://buildingmotif.readthedocs.io/en/latest/?badge=latest)
![PyPI](https://img.shields.io/pypi/v/buildingmotif)
![PyPI - Downloads](https://img.shields.io/pypi/dm/buildingmotif)

> *Enabling the enabling technology of semantic interoperability.*

Semantic Interoperability in buildings through standardized semantic metadata is crucial in unlocking the value of the abundant and diverse networked data in buildings, avoiding subsequent data incompatibility/interoperability issues, and paving the way for advanced building technologies like Fault Detection and Diagnostics (FDD), real-time energy optimization, other energy management information systems ([EMIS](https://www.energy.gov/eere/femp/what-are-energy-management-information-systems)), improved HVAC controls, and grid-integrated energy efficient building ([GEB](https://www.energy.gov/eere/buildings/grid-interactive-efficient-buildings)) technologies, all of which are needed to fully de-carbonize buildings.

Utilizing the capabilities of [Semantic Web](https://www.w3.org/standards/semanticweb/), it is possible to standardize building metadata in structured, expressive, and machine-readable way, but at the same time it is very important to make it easier to implement for field practitioners without advanced knowledge in computer science. ***Building Metadata OnTology Interoperability Framework (BuildingMOTIF)*** bridges that gap between theory and practice, by offering a toolset for building metadata creation, storage, visualization, and validation. It is offered in the form of a SDK with easy-to-use APIs, which abstract the underlying complexities of [RDF](https://www.w3.org/RDF/) graphs, database management, [SHACL](https://www.w3.org/TR/shacl/) validation, and interoperability between different metadata schemas/ontologies. It also supports connectors for easier integration with existing metadata sources (e.g., Building Automation System data, design models, existing metadata models, etc.) which are available at different phases of the building life-cycle.

The objectives of the ***BuildingMOTIF*** toolset are to (1) lower costs, reduce installation time, and improve delivered quality of building controls and services for building owners and occupants, (2) enable a simpler and more easily verifiable procurement process for products and services for building managers, and (3) open new business opportunities for service providers, by removing knowledge barriers for parties implementing building controls and services.

Currently, ***BuildingMOTIF*** is planned to support [Brick](https://brickschema.org/) Schema, [Project Haystack](https://project-haystack.org/), and the upcoming [ASHRAE 223P](https://www.ashrae.org/about/news/2018/ashrae-s-bacnet-committee-project-haystack-and-brick-schema-collaborating-to-provide-unified-data-semantic-modeling-solution) standard, and to offer both UI and underlying SDK with tutorials and reference documentation to be useful for different levels of expertise of users for maximum adoption.

# Documentation

[Documentation](https://buildingmotif.readthedocs.io/) is organized into sections for *References*, *Tutorials*, *Guides*, and *Explanations* following the framework Diataxis[^1].

[^1]: https://diataxis.fr/

# Using BuildingMOTIF with an AI coding agent

BuildingMOTIF ships an agent skill at [`.agents/skills/buildingmotif/`](https://github.com/NatLabRockies/BuildingMOTIF/tree/gtf-buildingmotif/.agents/skills/buildingmotif)
that teaches a `SKILL.md`-compatible coding agent — Claude Code, Codex, or others — how to
validate, repair, and build models with BuildingMOTIF, using it as an installed package
(no repository checkout needed for that part). Getting the skill's own dozen markdown
files onto disk currently does mean pulling them from this repository, but not via a full
clone — see [`guides/agent-skill.md`](guides/agent-skill.md) for a sparse/blobless `git
clone` (or a no-`git` tarball option), how to point different agents at the skill, and
example prompts.
