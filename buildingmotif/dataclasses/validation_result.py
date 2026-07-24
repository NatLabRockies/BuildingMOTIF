"""Structural types describing what every validation result looks like.

:py:meth:`buildingmotif.dataclasses.model.Model.validate` returns a different
concrete class depending on which SHACL engine is configured -- the legacy
:py:class:`~buildingmotif.dataclasses.validation.ValidationContext` for
``pyshacl``/``topquadrant``, or
:py:class:`~buildingmotif.dataclasses.algebraic_validation.AlgebraicValidationContext`
for ``pyshifty``. The two were already written to expose the same surface; this
module makes that contract explicit so callers can be written (and type-checked)
against one type instead of branching on ``isinstance``.

These are :py:class:`typing.Protocol` definitions, so neither context class
inherits from them -- they satisfy them structurally. The protocols deliberately
describe only the *common* surface: engine-specific extras (``GraphDiff.resolve``
on the legacy side, ``witnesses``/``proposals`` on the algebraic side) are
reached by narrowing to the concrete class.
"""

from typing import (
    TYPE_CHECKING,
    AbstractSet,
    Collection,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Union,
    runtime_checkable,
)

from rdflib import Graph, URIRef

if TYPE_CHECKING:
    from buildingmotif.dataclasses.model import Model
    from buildingmotif.dataclasses.shape_collection import ShapeCollection
    from buildingmotif.dataclasses.template import Template


@runtime_checkable
class Reason(Protocol):
    """Anything that can explain itself in building terms.

    Implemented by
    :py:class:`~buildingmotif.dataclasses.validation.GraphDiff` (legacy) and
    :py:class:`~buildingmotif.dataclasses.algebraic_validation.AlgebraicReason`
    (pyshifty).
    """

    def reason(self) -> str:
        """A human-readable explanation of this failure."""
        ...


@runtime_checkable
class Failure(Reason, Protocol):
    """A single validation failure attached to a node in the model.

    Implemented by
    :py:class:`~buildingmotif.dataclasses.validation.GraphDiff` (legacy) and
    :py:class:`~buildingmotif.dataclasses.algebraic_validation.RepairWitness`
    (pyshifty).
    """

    @property
    def focus(self) -> Optional[URIRef]:
        """The node this failure is about, or ``None`` for a model-level failure."""
        ...


@runtime_checkable
class ValidationResult(Protocol):
    """The result of validating a model, independent of SHACL engine.

    Both :py:class:`~buildingmotif.dataclasses.validation.ValidationContext` and
    :py:class:`~buildingmotif.dataclasses.algebraic_validation.AlgebraicValidationContext`
    satisfy this. Write against it when you only need to know *whether* a model
    conforms and *what* is missing; narrow to the concrete class when you need
    engine-specific behavior such as soundness-gated repair proposals.
    """

    @property
    def valid(self) -> bool:
        """True iff the model conforms to the shape collections."""
        ...

    @property
    def conforms(self) -> bool:
        """Alias of :py:attr:`valid`, matching SHACL's own vocabulary."""
        ...

    @property
    def report(self) -> Graph:
        """The W3C SHACL validation report graph."""
        ...

    @property
    def report_string(self) -> str:
        """The validation report rendered as text."""
        ...

    @property
    def model(self) -> "Model":
        """The model that was validated."""
        ...

    @property
    def shape_collections(self) -> Sequence["ShapeCollection"]:
        """The shape collections the model was validated against."""
        ...

    @property
    def shapes_graph(self) -> Graph:
        """The (skolemized) shapes graph used for validation."""
        ...

    @property
    def diffset(self) -> Mapping[Optional[URIRef], AbstractSet[Failure]]:
        """Failures grouped by focus node; the ``None`` key holds model-level
        failures. Empty iff the model is valid."""
        ...

    def get_broken_entities(self) -> AbstractSet[Union[URIRef, str]]:
        """The set of failing focus nodes, with model-level failures reported as
        the string ``"Model"``."""
        ...

    def get_diffs_for_entity(self, entity: Optional[URIRef]) -> AbstractSet[Failure]:
        """The failures recorded against a single focus node."""
        ...

    def get_reasons_with_severity(
        self, severity: Union[URIRef, str]
    ) -> Mapping[Optional[URIRef], Collection[Reason]]:
        """Failures grouped by focus node, keeping only those at the given
        severity (``SH.Violation``/``"Violation"``, ``SH.Warning``, ``SH.Info``).

        :raises ValueError: if ``severity`` is not one of the three SHACL
            severities
        """
        ...

    def as_templates(self) -> List["Template"]:
        """Templates that, once filled in, reconcile the failures."""
        ...
