from dataclasses import dataclass
from functools import cached_property
from typing import Dict, List, Optional

import pandas as pd
import rdflib
import rdflib.query
from rdflib import URIRef

from buildingmotif.dataclasses.model import Model
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.dataclasses.validation import ValidationContext
from buildingmotif.namespaces import OWL, SH, A
from buildingmotif.shacl_backends import shacl_validate
from buildingmotif.utils import (
    copy_graph,
    rewrite_shape_graph,
    skolemize_shapes,
)


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
    ):
        self.model = model
        self.shape_collections = shape_collections
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

        for shape_uri in shapes_to_test:
            temp_model_graph = copy_graph(model_graph)
            for (s,) in targets:
                temp_model_graph.add((URIRef(s), A, shape_uri))

            valid, report_g, report_str = shacl_validate(
                temp_model_graph, ontology_graph, engine=self.model._bm.shacl_engine
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
        # TODO: determine the return types; At least a bool for valid/invalid,
        # but also want a report. Is this the base pySHACL report? Or a useful
        # transformation, like a list of deltas for potential fixes?
        shapeg = copy_graph(self._compiled_graph)
        # aggregate shape graphs
        for sc in self.shape_collections:
            shapeg += sc.resolve_imports(
                error_on_missing_imports=error_on_missing_imports
            ).graph
        # inline sh:node for interpretability
        shapeg = rewrite_shape_graph(shapeg)

        # remove imports from sg
        shapeg.remove((None, OWL.imports, None))

        # skolemize the shape graph so we have consistent identifiers across
        # validation through the interpretation of the validation report
        shapeg = skolemize_shapes(shapeg)

        # remove imports from data graph
        shapeg.remove((None, OWL.imports, None))

        # validate the data graph
        valid, report_g, report_str = shacl_validate(
            shapeg, engine=self.model._bm.shacl_engine
        )
        return ValidationContext(
            self.shape_collections,
            shapeg,
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
        metadata = pd.DataFrame(self.graph.query(query).bindings, dtype="string")
        # metadata.columns will be rdflib.term.Variable objects, so we need to convert them to strings
        metadata.columns = [str(col) for col in metadata.columns]
        # convert the rdflib terms to Python types
        return metadata.map(lambda x: x.toPython())


class PyshiftyCompiledModel(CompiledModel):
    """
    Specialized CompiledModel for the pyshifty SHACL engine.
    Keeps data and shape graphs separate and avoids shape skolemization.
    """

    def _build_shape_graph(self, error_on_missing_imports: bool = True) -> rdflib.Graph:
        shape_graph = rdflib.Graph()
        for sc in self.shape_collections:
            shape_graph += sc.resolve_imports(
                error_on_missing_imports=error_on_missing_imports
            ).graph
        shape_graph = rewrite_shape_graph(shape_graph)
        shape_graph.remove((None, OWL.imports, None))
        return skolemize_shapes(shape_graph)

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

        shape_graph = rdflib.Graph()
        for shape_collection in self.shape_collections:
            shape_graph += shape_collection.graph
        shape_graph = skolemize_shapes(shape_graph)

        for shape_uri in shapes_to_test:
            temp_model_graph = copy_graph(model_graph)
            for (s,) in targets:
                temp_model_graph.add((URIRef(s), A, shape_uri))

            valid, report_g, report_str = shacl_validate(
                temp_model_graph, shape_graph, engine=self.model._bm.shacl_engine
            )
            results[shape_uri] = ValidationContext(
                self.shape_collections,
                shape_graph,
                valid,
                report_g,
                report_str,
                self.model,
            )

        return results

    def validate(
        self,
        error_on_missing_imports: bool = True,
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
        data_graph = copy_graph(self._compiled_graph)
        data_graph.remove((None, OWL.imports, None))

        shape_graph = self._build_shape_graph(
            error_on_missing_imports=error_on_missing_imports
        )

        valid, report_g, report_str = shacl_validate(
            data_graph, shape_graph, engine=self.model._bm.shacl_engine
        )
        return ValidationContext(
            self.shape_collections,
            shape_graph,
            valid,
            report_g,
            report_str,
            self.model,
        )
