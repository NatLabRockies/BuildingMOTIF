from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, List, Optional

import rdflib
import rdflib.query
import rfc3987

from buildingmotif import get_building_motif
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.dataclasses.validation import ValidationContext
from buildingmotif.shacl import get_shacl_backend
from buildingmotif.utils import Triple

if TYPE_CHECKING:
    from buildingmotif import BuildingMOTIF
    from buildingmotif.dataclasses.compiled_model import CompiledModel


def _validate_uri(uri: str):
    parsed = rfc3987.parse(uri)
    if not parsed["scheme"]:
        raise ValueError(
            f"{uri} does not look like a valid URI, trying to serialize this will break."
        )


@dataclass
class Model:
    """This class mirrors :py:class:`database.tables.DBModel`."""

    _id: int
    _name: str
    _description: str
    _graph: rdflib.Graph
    _bm: "BuildingMOTIF"
    _manifest_id: int

    @classmethod
    def create(cls, name: str, description: str = "") -> "Model":
        """Create a new model.

        :param name: new model name
        :type name: str
        :param description: new model description
        :type description: str
        :return: new model
        :rtype: Model
        """
        _validate_uri(name)
        g = rdflib.Graph()
        g.add((rdflib.URIRef(name), rdflib.RDF.type, rdflib.OWL.Ontology))
        if description:
            g.add(
                (rdflib.URIRef(name), rdflib.RDFS.comment, rdflib.Literal(description))
            )
        return cls.from_graph(g)

    @classmethod
    def from_graph(cls, graph: rdflib.Graph) -> "Model":
        """Create a new model from a graph. The name of the model is taken from the
        ontology declaration in the graph (subject of rdf:type owl:Ontology triple).
        The description of the model can be set through an RDFS comment on the ontology

        :param graph: graph to create model from
        :type graph: rdflib.Graph
        :return: new model
        :rtype: Model
        """
        bm = get_building_motif()

        name = graph.value(predicate=rdflib.RDF.type, object=rdflib.OWL.Ontology)
        if name is None:
            raise ValueError("Graph does not contain an ontology declaration")
        _validate_uri(name)

        # the 'description' is the rdfs:comment of the ontology
        description = graph.value(name, rdflib.RDFS.comment)
        description = str(description) if description is not None else ""

        db_model = bm.table_connection.create_db_model(name, description)

        graph = bm.graph_connection.create_graph(db_model.graph_id, graph)

        # below, we normalize the name to a string so it matches the database type
        return cls(
            _id=db_model.id,
            _name=str(db_model.name),
            _description=db_model.description,
            _graph=graph,
            _bm=bm,
            _manifest_id=db_model.manifest_id,
        )

    @classmethod
    def from_file(cls, url_or_path: str) -> "Model":
        """Create a new model from a file.

        :param url_or_path: url or path to file
        :type url_or_path: str
        :return: new model
        :rtype: Model
        """
        graph = rdflib.Graph()
        # if guess_format doesn't match anything, it will return None,
        # which tells graph.parse to guess 'turtle'

        # if graph parsing fails, it will raise an exception
        graph.parse(url_or_path, format=rdflib.util.guess_format(url_or_path))
        return cls.from_graph(graph)

    @classmethod
    def load(cls, id: Optional[int] = None, name: Optional[str] = None) -> "Model":
        """Get model from database by id or name.

        :param id: model id, defaults to None
        :type id: Optional[int], optional
        :param name: model name, defaults to None
        :type name: Optional[str], optional
        :raises Exception: if neither id nor name provided
        :return: model
        :rtype: Model
        """
        bm = get_building_motif()
        if id is not None:
            db_model = bm.table_connection.get_db_model(id)
        elif name is not None:
            db_model = bm.table_connection.get_db_model_by_name(name)
        else:
            raise Exception("Neither id nor name provided to load Model")
        graph = bm.graph_connection.get_graph(db_model.graph_id)

        return cls(
            _id=db_model.id,
            _name=db_model.name,
            _description=db_model.description,
            _graph=graph,
            _bm=bm,
            _manifest_id=db_model.manifest_id,
        )

    @property
    def id(self) -> Optional[int]:
        return self._id

    @id.setter
    def id(self, new_id):
        raise AttributeError("Cannot modify db id")

    @cached_property
    def graph(self) -> rdflib.Graph:
        return self._graph

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, new_name: str):
        self._bm.table_connection.update_db_model_name(self._id, new_name)
        self._name = new_name

    @property
    def description(self):
        return self._description

    @description.setter
    def description(self, new_description: str):
        self._bm.table_connection.update_db_model_description(self._id, new_description)
        self._description = new_description

    def add_triples(self, *triples: Triple) -> None:
        """Add the given triples to the model.

        :param triples: a sequence of triples to add to the graph
        :type triples: Triple
        """
        for triple in triples:
            self.graph.add(triple)

    def add_graph(self, graph: rdflib.Graph) -> None:
        """Add the given graph to the model.

        :param graph: the graph to add to the model
        :type graph: rdflib.Graph
        """
        self.graph += graph

    def validate(
        self,
        shape_collections: Optional[List[ShapeCollection]] = None,
        error_on_missing_imports: bool = True,
        shacl_engine: Optional[str] = None,
    ) -> "ValidationContext":
        """Validates this model against the given list of ShapeCollections.
        If no list is provided, the model will be validated against the model's "manifest".
        If a list of shape collections is provided, the manifest will *not* be automatically
        included in the set of shape collections.

        Loads all of the ShapeCollections into a single graph.

        :param shape_collections: a list of ShapeCollections against which the
            graph should be validated. If an empty list or None is provided, the
            model will be validated against the model's manifest.
        :type shape_collections: List[ShapeCollection]
        :param error_on_missing_imports: if True, raises an error if any of the dependency
            ontologies are missing (i.e. they need to be loaded into BuildingMOTIF), defaults
            to True
        :type error_on_missing_imports: bool, optional
        :return: An object containing useful properties/methods to deal with
            the validation results
        :param shacl_engine: the SHACL engine to use for validation, defaults to whatever
            is set in the BuildingMOTIF object
        :type shacl_engine: str, optional

        :rtype: ValidationContext
        """
        compiled_model = self.compile(
            shape_collections or [self.get_manifest()], shacl_engine=shacl_engine
        )
        return compiled_model.validate(error_on_missing_imports, shacl_engine)

    def compile(
        self,
        shape_collections: Optional[List["ShapeCollection"]] = None,
        shacl_engine: Optional[str] = None,
    ) -> "CompiledModel":
        """Compile the graph of a model against a set of ShapeCollections.

        :param shape_collections: list of ShapeCollections to compile the model
            against. Defaults to the model's manifest.
        :type shape_collections: List[ShapeCollection], optional
        :param shacl_engine: the SHACL engine to use for validation, defaults to whatever
            is set in the BuildingMOTIF object
        :type shacl_engine: str, optional
        :return: copy of model's graph that has been compiled against the
            ShapeCollections
        :rtype: Graph
        """
        from buildingmotif.dataclasses.compiled_model import CompiledModel

        if shape_collections is None:
            shape_collections = [self.get_manifest()]
        backend = get_shacl_backend(shacl_engine or self._bm.shacl_engine)
        compiled_graph = backend.compile_model_graph(self.graph, shape_collections)
        return CompiledModel(
            self,
            shape_collections,
            compiled_graph,
            shacl_engine=shacl_engine or "default",
        )

    def get_manifest(self) -> ShapeCollection:
        """Get ShapeCollection from model.

        :return: model's shape collection
        :rtype: ShapeCollection
        """
        return ShapeCollection.load(self._manifest_id)

    def update_manifest(self, manifest: ShapeCollection):
        """Updates the manifest for this model by adding in the contents
        of the shape graph inside the provided SHapeCollection

        :param manifest: the ShapeCollection containing additional shapes against which to validate this model
        :type manifest: ShapeCollection
        """
        self.get_manifest().graph += manifest.graph
