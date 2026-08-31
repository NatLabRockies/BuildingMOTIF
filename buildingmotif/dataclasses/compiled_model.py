from dataclasses import dataclass
from functools import cached_property
from itertools import product
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd
import rdflib
import rdflib.query
from rdflib import URIRef

from buildingmotif.dataclasses.model import Model
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.dataclasses.validation import ValidationContext
from buildingmotif.dataclasses.validation_result import ValidationResult
from buildingmotif.namespaces import SH, A
from buildingmotif.shacl import (
    DEFAULT_SHACL_ENGINE,
    _shifty_shapes_input,
    get_shacl_backend,
    normalize_shacl_engine,
    require_shifty,
)
from buildingmotif.utils import copy_graph

if TYPE_CHECKING:
    from buildingmotif.dataclasses.algebraic_validation import RepairConfig
    from buildingmotif.dataclasses.library import Library
    from buildingmotif.dataclasses.manifest import Manifest


@dataclass
class CompiledModel:
    """
    This class represents a model that has been compiled against a set of ShapeCollections.
    """

    model: Model
    shape_collections: List[ShapeCollection]
    _compiled_graph: rdflib.Graph

    def __init__(
        self,
        model: Model,
        shape_collections: List[ShapeCollection],
        compiled_graph: rdflib.Graph,
        shacl_engine: Optional[str] = None,
        manifest: Optional["Manifest"] = None,
    ):
        """
        :param shacl_engine: the engine this model was compiled with. None
            (the default) inherits the active BuildingMOTIF's engine. The
            string ``"default"`` is still accepted for that, but None is the
            sentinel the rest of the codebase uses -- ``Model.compile`` and
            ``Model.validate`` both already take ``Optional[str]``.
        :type shacl_engine: Optional[str]
        :param manifest: the manifest ``shape_collections`` came from, when it
            came from one. :py:meth:`validate` then takes the shapes graph
            straight from its members, since a manifest already lists
            everything they import. It is held rather than resolved here
            because the graph is only needed to validate, not to compile.
        :type manifest: Optional[Manifest]
        """
        self.model = model
        self.shape_collections = shape_collections
        self.manifest = manifest
        self.shacl_engine = (
            self.model._bm.shacl_engine
            # "default" is the legacy spelling of "inherit from the singleton"
            if (shacl_engine is None or shacl_engine == "default")
            else normalize_shacl_engine(shacl_engine)
        )
        # inference is performed by the SHACL backend in Model.compile; the
        # graph handed to us here is already compiled
        self._compiled_graph = compiled_graph

    @cached_property
    def graph(self) -> rdflib.Graph:
        g = copy_graph(self._compiled_graph)
        for shape_collection in self.shape_collections:
            g += shape_collection.graph
        return g

    def add_graph(self, graph: rdflib.Graph) -> None:
        """Add the given graph to this compiled model snapshot.

        :param graph: the graph to add to the compiled model
        :type graph: rdflib.Graph
        """
        self._compiled_graph += graph
        self.__dict__.pop("graph", None)

    def validate_model_against_shapes(
        self,
        shapes_to_test: List[rdflib.URIRef],
        target_class: rdflib.URIRef,
    ) -> Dict[rdflib.URIRef, ValidationResult]:
        """Validates the model against a list of shapes and generates a
        validation report for each.

        Uses the same engine as :py:meth:`validate`, and therefore returns the
        same kind of context: an
        :class:`~buildingmotif.dataclasses.algebraic_validation.AlgebraicValidationContext`
        under ``pyshifty``, a
        :class:`~buildingmotif.dataclasses.validation.ValidationContext`
        otherwise. It used to build a ``ValidationContext`` unconditionally, so
        one CompiledModel handed back different context types from its two
        validation methods.

        :param shapes_to_test: list of shape URIs to validate the model against
        :type shapes_to_test: List[URIRef]
        :param target_class: the class upon which to run the selected shapes
        :type target_class: URIRef
        :return: a dictionary relating each tested shape to its validation result
        :rtype: Dict[URIRef, ValidationResult]
        """
        model_graph = copy_graph(self._compiled_graph)

        results: Dict[rdflib.URIRef, ValidationResult] = {}

        targets = model_graph.query(
            f"""
            PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            SELECT ?target
            WHERE {{
                ?target rdf:type/rdfs:subClassOf* <{target_class}>

            }}
        """
        )
        # skolemize the shape graph so we have consistent identifiers across
        # validation through the interpretation of the validation report
        ontology_graph = self.graph.skolemize()
        backend = get_shacl_backend(self.shacl_engine)

        for shape_uri in shapes_to_test:
            temp_model_graph = copy_graph(model_graph)
            for (s,) in targets:
                temp_model_graph.add((URIRef(s), A, shape_uri))

            if self.shacl_engine == DEFAULT_SHACL_ENGINE:
                from buildingmotif.dataclasses.algebraic_validation import (
                    AlgebraicValidationContext,
                )

                results[shape_uri] = AlgebraicValidationContext.from_compiled(
                    self.shape_collections,
                    ontology_graph,
                    temp_model_graph,
                    self.model,
                )
                continue

            valid, report_g, report_str = backend.validate(
                temp_model_graph, ontology_graph
            )
            results[shape_uri] = ValidationContext(
                self.shape_collections,
                ontology_graph,
                valid,
                report_g,
                report_str,
                self.model,
            )

        return results

    def validate(
        self,
        error_on_missing_imports: bool = True,
        shacl_engine: Optional[str] = None,
        repair_libraries: Optional[List["Library"]] = None,
        repair_config: Optional["RepairConfig"] = None,
    ) -> ValidationResult:
        """Validates this model against the given list of ShapeCollections.
        If no list is provided, the model will be validated against the model's "manifest".
        If a list of shape collections is provided, the manifest will *not* be automatically
        included in the set of shape collections.

        Loads all of the ShapeCollections into a single graph.

        :param error_on_missing_imports: if True, raises an error if any of the dependency
            ontologies are missing (i.e. they need to be loaded into BuildingMOTIF), defaults
            to True
        :type error_on_missing_imports: bool, optional
        :param shacl_engine: the SHACL engine to validate with. None (the
            default) uses the engine this model was compiled with; pass ``"pyshacl"``,
            ``"topquadrant"``, or ``"shifty"`` to override. The ``"shifty"`` engine
            returns an
            :class:`~buildingmotif.dataclasses.algebraic_validation.AlgebraicValidationContext`
            instead of the legacy ``ValidationContext``. Defaults to None.
        :type shacl_engine: Optional[str]
        :param repair_libraries: libraries whose templates seed template-guided,
            soundness-gated repair. Only the ``"shifty"`` engine uses these; other
            engines ignore them. Defaults to no template guidance.
        :type repair_libraries: Optional[List[Library]]
        :param repair_config: search budgets for template-guided repair (only used by
            the ``pyshifty`` engine); defaults to
            :class:`~buildingmotif.dataclasses.algebraic_validation.RepairConfig`
        :type repair_config: Optional[RepairConfig]
        :return: An object containing useful properties/methods to deal with the
            validation results. Both engines' return values satisfy
            :class:`~buildingmotif.dataclasses.validation_result.ValidationResult`,
            so code that only reads failures need not care which one it got.
        :rtype: ValidationResult
        """
        import warnings

        shacl_engine = normalize_shacl_engine(shacl_engine or self.shacl_engine)
        if (
            repair_libraries is not None or repair_config is not None
        ) and shacl_engine != DEFAULT_SHACL_ENGINE:
            warnings.warn(
                "repair_libraries and repair_config are only used by the 'pyshifty' "
                "engine and will be ignored.",
                stacklevel=3,
            )
        backend = get_shacl_backend(shacl_engine)

        # A manifest's members already include everything they import --
        # add() followed the imports when they were added -- so the shapes
        # graph is their union, with no import resolution at validation time.
        resolved_shapes = (
            self.manifest.shapes_graph(error_on_missing=error_on_missing_imports)
            if self.manifest is not None
            else None
        )

        # The pyshifty engine exposes a native algebraic + symbolic-repair API.
        # Auto-route it to the AlgebraicValidationContext, which computes repairs
        # by abduction over the algebra and gates every one for soundness, rather
        # than re-parsing a flattened W3C report. Other engines keep the legacy
        # GraphDiff-based ValidationContext.
        if shacl_engine == DEFAULT_SHACL_ENGINE:
            from buildingmotif.dataclasses.algebraic_validation import (
                AlgebraicValidationContext,
            )

            graphs = backend.validation_graphs(
                self._compiled_graph,
                self.shape_collections,
                error_on_missing_imports=error_on_missing_imports,
                resolved_shapes=resolved_shapes,
            )
            return AlgebraicValidationContext.from_compiled(
                self.shape_collections,
                graphs.shape_graph
                if graphs.shape_graph is not None
                else rdflib.Graph(),
                graphs.data_graph,
                self.model,
                libraries=repair_libraries,
                repair_config=repair_config,
            )

        (valid, report_g, report_str), context_graph = backend.validate_compiled_model(
            self._compiled_graph,
            self.shape_collections,
            error_on_missing_imports=error_on_missing_imports,
            resolved_shapes=resolved_shapes,
        )
        return ValidationContext(
            self.shape_collections,
            context_graph,
            valid,
            report_g,
            report_str,
            self.model,
        )

    def defining_shape_collection(
        self, shape: rdflib.URIRef
    ) -> Optional[ShapeCollection]:
        """
        Given a shape, return the ShapeCollection that defines it. The search is limited to the
        ShapeCollections that were used to compile this model.

        :param shape: the shape to search for
        :type shape: rdflib.URIRef
        :return: the ShapeCollection that defines the shape, or None if the shape is not defined
        :rtype: Optional[ShapeCollection]
        """
        for sc in self.shape_collections:
            if (shape, A, SH.NodeShape) in sc.graph:
                return sc
        return None

    def shape_map(
        self,
        shape: Optional[rdflib.URIRef] = None,
        *,
        name_path: str = "sh:name",
        value_paths: Optional[Dict[str, str]] = None,
    ):
        """Extract the values this model supplies for a shape's slots.

        A *shape map* is a binding table: one entry per selected
        ``(shape, focus)`` pair, mapping each obligation the shape states to the
        values the model actually supplied for it. It treats a shape as an
        **extraction schema** -- "give me every VAV and its air flow sensor" --
        rather than as a pass/fail test, which is what makes it the natural
        backing for :meth:`shape_to_df` and :meth:`shape_to_table`.

        Unlike a SPARQL projection of the same shape, each entry also reports
        whether that focus *conformed*, how many values were expected against
        how many were found, and which near-miss values were rejected. A focus
        that is missing a required value still appears, with the deficit
        described, instead of dropping out of the result.

        :param shape: the shape to extract against, or ``None`` for every shape
            in the model's shape collections
        :type shape: Optional[rdflib.URIRef]
        :param name_path: property path giving each slot its author-facing name,
            evaluated against the shapes graph. The default reads ``sh:name``,
            which is the name BuildingMOTIF shapes already carry.

            A *prefixed* path is resolved against the prefixes declared in the
            document shifty parses, and an unresolvable one raises
            ``ValueError: undeclared prefix``. ``sh:`` and BuildingMOTIF's other
            well-known prefixes are always declared (:func:`_shifty_shapes_input`
            re-binds them, since the storage layer does not persist a source
            file's prefixes). For anything else, write the path with a full IRI
            in angle brackets -- ``"<http://example.org/label>"``.
        :type name_path: str
        :param value_paths: optional ``{label: property path}`` map used to
            annotate each *bound value* from the model graph -- e.g.
            ``{"label": "rdfs:label"}`` to carry a human-readable name alongside
            each matched node.
        :type value_paths: Optional[Dict[str, str]]
        :return: the native ``shifty.ShapeMap``
        :raises ValueError: if ``shape`` is given but no shape collection
            defines it

        .. note::
            Inference is **not** re-run: a :class:`CompiledModel` already holds
            the inferred closure, so the shape map reads the graph as compiled.
        """
        shifty = require_shifty()

        if shape is not None and self.defining_shape_collection(shape) is None:
            raise ValueError(
                f"Shape {shape} is not defined in any of the shape collections"
            )

        shape_graph = rdflib.Graph()
        for sc in self.shape_collections:
            shape_graph += sc.graph

        return shifty.shape_map(
            self.graph,
            _shifty_shapes_input(shape_graph),
            name_path=name_path,
            value_paths=value_paths,
            shape_names=[str(shape)] if shape is not None else None,
            # "info" rather than "violation": a shape map is an extraction, so a
            # slot that merely warns should still report the values it bound.
            minimum_severity="info",
            infer=False,
        )

    def shape_to_table(self, shape: rdflib.URIRef, table: str, conn):
        """
        Turn the shape into a table of the values the model supplies for it, storing the results in a table.

        :param shape: the shape to query
        :type shape: rdflib.URIRef
        :param table: the name of the table to store the results in
        :type table: str
        :param conn: the connection to the database
        :type conn: sqlalchemy.engine.base.Connection
        """
        metadata = self.shape_to_df(shape)
        metadata.to_sql(table, conn, if_exists="replace", index=False)

    def shape_to_df(
        self, shape: rdflib.URIRef, include_nonconforming: bool = False
    ) -> pd.DataFrame:
        """
        Turn the shape into a dataframe of the values the model supplies for it.

        One row per focus node; a ``target`` column naming that focus, plus one
        column per named slot (``sh:name``) on the shape. A focus binding
        several values for one slot expands to one row per combination.

        Backed by :meth:`shape_map`, so a slot's column is populated from the
        values SHACL itself matched against that slot -- including through
        ``sh:or``, ``sh:node`` and qualified value shapes -- rather than from a
        hand-compiled approximation of the shape in SPARQL.

        :param shape: the shape to query
        :type shape: rdflib.URIRef
        :param include_nonconforming: also return the focus nodes the shape
            *selected* but which do not satisfy it, with their unfilled slots
            left null. Defaults to False, which returns only conforming focus
            nodes -- the rows a SPARQL projection of the shape would return.

            A shape map reports every selected focus, conforming or not, which
            is the more useful answer when the question is "what is missing?"
            rather than "what is configured?". It is opt-in because the two
            answers differ: a partially-configured entity appears here and does
            not appear in a query's results.
        :type include_nonconforming: bool
        :return: the values the model supplies for the shape
        :rtype: pd.DataFrame
        :raises ValueError: if no shape collection defines ``shape``
        """
        shape_map = self.shape_map(shape)
        slot_index = self._slot_index(shape)

        # Column set comes from the shape, not from the rows: a shape that
        # selects no focus nodes still has to report its columns (an empty
        # frame with the right columns is a usable answer; a frame with no
        # columns is not).
        columns = ["target"] + sorted(set(slot_index.values()))

        rows: List[Dict[str, object]] = []
        for mapping in shape_map:
            if not include_nonconforming and not mapping.conforms:
                continue
            named: Dict[str, Any] = {}
            for binding in mapping.values():
                # prefer the name the engine resolved; fall back to the
                # shapes graph, which is still needed to name columns for a
                # shape that selected no focus nodes (see _slot_index)
                name = binding.name or slot_index.get(self._slot_key(binding))
                if name is not None:
                    named[name] = binding
            # one row per combination of the values bound to each slot, so a
            # focus with two air flow sensors yields two rows
            slots = [named.get(name) for name in columns[1:]]
            value_lists = [
                [term.to_rdflib() for term in binding.values]
                if binding is not None and binding.values
                else [None]
                for binding in slots
            ]
            focus = mapping.focus.to_rdflib()
            for combination in product(*value_lists) if value_lists else [()]:
                row: Dict[str, object] = {"target": focus}
                row.update(dict(zip(columns[1:], combination)))
                rows.append(row)

        metadata = pd.DataFrame(rows, columns=columns, dtype="string")
        # convert the rdflib terms to Python types
        return metadata.map(lambda x: x.toPython() if hasattr(x, "toPython") else x)

    def _slot_index(self, shape: rdflib.URIRef) -> Dict[tuple, str]:
        """Map each of a shape's slots to its author-facing ``sh:name``.

        Keyed by ``(path IRI, qualifier class IRI or None)`` -- the same pair a
        shape map's :class:`Key` carries -- so a binding can be matched back to
        the property shape it came from.

        pyshifty 0.4.2 resolves a slot's ``sh:name`` on every binding, but a
        shape that selects no focus nodes yields no bindings at all. A shape
        map has no independent slot vocabulary (``shape_names()`` gives shape
        IRIs, ``to_dict()`` gives an empty list per shape), so the column set
        must come from the shapes graph. This also remains a conservative
        fallback should an engine fail to resolve a name.
        """
        defining_sc = self.defining_shape_collection(shape)
        if defining_sc is None:
            raise ValueError(
                f"Shape {shape} is not defined in any of the shape collections"
            )
        # The shape is interpolated rather than passed via initBindings: the
        # Oxigraph store rejects a substitution for a variable that is not in
        # the SELECT projection ("does not contain variable ?shape").
        rows = defining_sc.graph.query(
            f"""
            PREFIX sh: <http://www.w3.org/ns/shacl#>
            SELECT DISTINCT ?name ?path ?class WHERE {{
                <{shape}> sh:property ?pshape .
                ?pshape sh:name ?name ; sh:path ?path .
                OPTIONAL {{ ?pshape sh:qualifiedValueShape/sh:class ?class }}
                OPTIONAL {{ ?pshape sh:class ?class }}
            }}
            """
        )
        index: Dict[tuple, str] = {}
        for name, path, cls in rows:  # type: ignore[misc]
            index[(str(path), str(cls) if cls is not None else None)] = str(name)
        return index

    @staticmethod
    def _slot_key(binding) -> tuple:
        """The ``(path, qualifier class)`` pair identifying a binding's slot."""
        path = getattr(binding.path, "iri", None)
        qualifier = getattr(binding.qualifier, "iri", None)
        return (str(path) if path else None, str(qualifier) if qualifier else None)
