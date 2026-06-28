from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Dict, List, Optional

import pandas as pd
import rdflib
import rdflib.query
from rdflib import URIRef

from buildingmotif.dataclasses.model import Model
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.dataclasses.validation import ValidationContext
from buildingmotif.namespaces import SH, A
from buildingmotif.shacl import (
    DEFAULT_SHACL_ENGINE,
    get_shacl_backend,
    normalize_shacl_engine,
)
from buildingmotif.utils import copy_graph

if TYPE_CHECKING:
    from buildingmotif.dataclasses.library import Library


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
        shacl_engine: str = "default",
    ):
        self.model = model
        self.shape_collections = shape_collections
        self.shacl_engine = (
            self.model._bm.shacl_engine
            if (shacl_engine == "default" or not shacl_engine)
            else normalize_shacl_engine(shacl_engine)
        )
        self._compiled_graph = compiled_graph

    @cached_property
    def graph(self) -> rdflib.Graph:
        g = copy_graph(self._compiled_graph)
        for shape_collection in self.shape_collections:
            g += shape_collection.graph
        return g

    def validate_model_against_shapes(
        self,
        shapes_to_test: List[rdflib.URIRef],
        target_class: rdflib.URIRef,
    ) -> Dict[rdflib.URIRef, "ValidationContext"]:
        """Validates the model against a list of shapes and generates a
        validation report for each.

        :param shapes_to_test: list of shape URIs to validate the model against
        :type shapes_to_test: List[URIRef]
        :param target_class: the class upon which to run the selected shapes
        :type target_class: URIRef
        :return: a dictionary that relates each shape to test URIRef to a
                 ValidationContext
        :rtype: Dict[URIRef, ValidationContext]
        """
        model_graph = copy_graph(self._compiled_graph)

        results = {}

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
    ) -> "ValidationContext":
        """Validates this model against the given list of ShapeCollections.
        If no list is provided, the model will be validated against the model's "manifest".
        If a list of shape collections is provided, the manifest will *not* be automatically
        included in the set of shape collections.

        Loads all of the ShapeCollections into a single graph.

        :param error_on_missing_imports: if True, raises an error if any of the dependency
            ontologies are missing (i.e. they need to be loaded into BuildingMOTIF), defaults
            to True
        :type error_on_missing_imports: bool, optional
        :return: An object containing useful properties/methods to deal with
            the validation results
        :rtype: ValidationContext
        """
        import warnings

        shacl_engine = normalize_shacl_engine(shacl_engine or self.shacl_engine)
        if repair_libraries is not None and shacl_engine != DEFAULT_SHACL_ENGINE:
            warnings.warn(
                "repair_libraries is only used by the 'pyshifty' engine and will be ignored.",
                stacklevel=3,
            )
        backend = get_shacl_backend(shacl_engine)

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
            )
            if self._requires_pyshacl_validation(graphs.shape_graph):
                valid, report_g, report_str = get_shacl_backend("pyshacl").validate(
                    graphs.data_graph, graphs.shape_graph
                )
                context_graph = graphs.data_graph + (
                    graphs.shape_graph
                    if graphs.shape_graph is not None
                    else rdflib.Graph()
                )
                return ValidationContext(
                    self.shape_collections,
                    context_graph,
                    valid,
                    report_g,
                    report_str,
                    self.model,
                )
            return AlgebraicValidationContext.from_compiled(
                self.shape_collections,
                graphs.shape_graph
                if graphs.shape_graph is not None
                else rdflib.Graph(),
                graphs.data_graph,
                self.model,
                libraries=repair_libraries,
            )

        (valid, report_g, report_str), context_graph = backend.validate_compiled_model(
            self._compiled_graph,
            self.shape_collections,
            error_on_missing_imports=error_on_missing_imports,
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

    @staticmethod
    def _requires_pyshacl_validation(shape_graph: Optional[rdflib.Graph]) -> bool:
        if shape_graph is None:
            return False
        return (None, A, SH.SPARQLAskValidator) in shape_graph

    def shape_to_table(self, shape: rdflib.URIRef, table: str, conn):
        """
        Turn the shape into a SPARQL query and execute it on the model's graph, storing the results in a table.

        :param shape: the shape to query
        :type shape: rdflib.URIRef
        :param table: the name of the table to store the results in
        :type table: str
        :param conn: the connection to the database
        :type conn: sqlalchemy.engine.base.Connection
        """
        metadata = self.shape_to_df(shape)
        metadata.to_sql(table, conn, if_exists="replace", index=False)

    def shape_to_df(self, shape: rdflib.URIRef) -> pd.DataFrame:
        """
        Turn the shape into a SPARQL query and execute it on the model's graph, storing the results in a dataframe.

        :param shape: the shape to query
        :type shape: rdflib.URIRef
        :return: the results of the query
        :rtype: pd.DataFrame
        """
        defining_sc = self.defining_shape_collection(shape)
        if defining_sc is None:
            raise ValueError(
                f"Shape {shape} is not defined in any of the shape collections"
            )
        query = defining_sc.shape_to_query(shape)
        results = self.graph.query(query)
        columns = [str(col) for col in results.vars]
        metadata = pd.DataFrame(
            [
                {str(col): value for col, value in row.items()}
                for row in results.bindings
            ],
            columns=columns,
            dtype="string",
        )
        # convert the rdflib terms to Python types
        return metadata.map(lambda x: x.toPython())
