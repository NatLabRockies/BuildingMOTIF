import warnings
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Iterable, List, Optional, Union

import rdflib
import rdflib.query
import rfc3987

from buildingmotif import get_building_motif
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.dataclasses.validation_result import ValidationResult
from buildingmotif.shacl import get_shacl_backend
from buildingmotif.utils import Triple

if TYPE_CHECKING:
    from buildingmotif import BuildingMOTIF
    from buildingmotif.dataclasses.algebraic_validation import RepairConfig
    from buildingmotif.dataclasses.compiled_model import CompiledModel
    from buildingmotif.dataclasses.library import Library
    from buildingmotif.dataclasses.manifest import LibraryRef, Manifest


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
    _graph: rdflib.Graph = field(compare=False)
    _bm: "BuildingMOTIF" = field(compare=False)
    _manifest_id: int

    @classmethod
    def create(
        cls,
        uri: Optional[str] = None,
        description: str = "",
        *,
        name: Optional[str] = None,
    ) -> "Model":
        """Create a new model.

        :param uri: the model's URI. This becomes the subject of the model's
            ``owl:Ontology`` declaration and the namespace its entities live in,
            so it must be a syntactically valid URI -- typically an
            ``rdflib.Namespace`` such as ``Namespace("urn:bldg/")``.
        :type uri: str
        :param description: new model description
        :type description: str
        :param name: **deprecated** spelling of ``uri``. The parameter was
            called ``name`` even though it is validated as a URI, becomes the
            ontology's subject, and is what every tutorial passes a Namespace
            to -- which is why issue #339 asks for a constructor that already
            exists (:py:meth:`from_file`).
        :type name: Optional[str]
        :raises TypeError: if both ``uri`` and ``name`` are given, or neither
        :return: new model
        :rtype: Model
        """
        if name is not None:
            if uri is not None:
                raise TypeError(
                    "Model.create() got both uri and name; they are the same "
                    "argument -- use uri"
                )
            warnings.warn(
                "Model.create(name=...) is deprecated; the argument is the "
                "model's URI, so it is called uri now.",
                DeprecationWarning,
                stacklevel=2,
            )
            uri = name
        if uri is None:
            raise TypeError("Model.create() missing required argument 'uri'")

        _validate_uri(uri)
        g = rdflib.Graph()
        g.add((rdflib.URIRef(uri), rdflib.RDF.type, rdflib.OWL.Ontology))
        if description:
            g.add(
                (rdflib.URIRef(uri), rdflib.RDFS.comment, rdflib.Literal(description))
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
        :raises ValueError: if neither id nor name provided
        :return: model
        :rtype: Model
        """
        bm = get_building_motif()
        if id is not None:
            db_model = bm.table_connection.get_db_model(id)
        elif name is not None:
            db_model = bm.table_connection.get_db_model_by_name(name)
        else:
            raise ValueError("Model.load() needs either id or name")
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

    def replace_graph(self, graph: rdflib.Graph) -> None:
        """Atomically replace this Model's contents with ``graph``.

        Uses copy-on-write: ``graph`` is written to a fresh named graph and the
        stored pointer is flipped to it, so a failure or session rollback
        leaves the previous contents intact. The old graph becomes an orphan
        reclaimed by :py:meth:`BuildingMOTIF.collect_graph_garbage`.

        :param graph: the new contents of the model
        :type graph: rdflib.Graph
        """
        new_id, view = self._bm.graph_connection.replace_graph_contents(graph)
        self._bm.table_connection.update_db_model_graph_id(self._id, new_id)
        self._graph = view
        # invalidate the cached `graph` property so it returns the new view
        self.__dict__.pop("graph", None)

    def validate(
        self,
        shape_collections: Optional[List[ShapeCollection]] = None,
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
        :param repair_libraries: libraries whose templates seed template-guided,
            soundness-gated repair (only used by the ``pyshifty`` engine, which
            returns an
            :class:`~buildingmotif.dataclasses.algebraic_validation.AlgebraicValidationContext`).
            Defaults to no template guidance.
        :type repair_libraries: Optional[List[Library]]
        :param repair_config: search budgets for template-guided repair -- how many
            templates, ``Any`` branches, synthesis recursion, and per-hole candidates
            to try (only used by the ``pyshifty`` engine). Defaults to
            :class:`~buildingmotif.dataclasses.algebraic_validation.RepairConfig`.
        :type repair_config: Optional[RepairConfig]

        :return: An object containing useful properties/methods to deal with the
            validation results. Both engines' return values satisfy
            :class:`~buildingmotif.dataclasses.validation_result.ValidationResult`,
            so code that only reads failures need not care which one it got.
        :rtype: ValidationResult
        """
        manifest = None
        if not shape_collections:
            manifest = self.manifest
            shape_collections = manifest.shape_collections(
                error_on_missing=error_on_missing_imports
            )
        compiled_model = self.compile(
            shape_collections, shacl_engine=shacl_engine, manifest=manifest
        )
        return compiled_model.validate(
            error_on_missing_imports,
            shacl_engine,
            repair_libraries=repair_libraries,
            repair_config=repair_config,
        )

    def compile(
        self,
        shape_collections: Optional[List["ShapeCollection"]] = None,
        shacl_engine: Optional[str] = None,
        manifest: Optional["Manifest"] = None,
    ) -> "CompiledModel":
        """Compile the graph of a model against a set of ShapeCollections.

        :param shape_collections: list of ShapeCollections to compile the model
            against. Defaults to the model's manifest.
        :type shape_collections: List[ShapeCollection], optional
        :param shacl_engine: the SHACL engine to use for validation, defaults to whatever
            is set in the BuildingMOTIF object
        :type shacl_engine: str, optional
        :param manifest: the manifest ``shape_collections`` came from, if any.
            Passed on to the :py:class:`CompiledModel` so that validating it
            later resolves imports as one closure rooted at the manifest. It is
            filled in automatically when ``shape_collections`` is omitted.
        :type manifest: Optional[Manifest]
        :return: copy of model's graph that has been compiled against the
            ShapeCollections
        :rtype: Graph
        """
        from buildingmotif.dataclasses.compiled_model import CompiledModel

        if shape_collections is None:
            manifest = self.manifest
            shape_collections = manifest.shape_collections()
        backend = get_shacl_backend(shacl_engine or self._bm.shacl_engine)
        # NB: inference compiles against the member shape collections
        # themselves, *not* the manifest's imports closure -- what a model
        # infers from should be the shapes it was compiled against, and pulling
        # every transitively imported ontology into the inference input would
        # change what lands in every compiled model.
        compiled_graph = backend.compile_model_graph(self.graph, shape_collections)
        return CompiledModel(
            self,
            shape_collections,
            compiled_graph,
            shacl_engine=shacl_engine,
            manifest=manifest,
        )

    @property
    def manifest(self) -> "Manifest":
        """The set of libraries this model is validated and compiled against.

        Behaves like a set of libraries -- see
        :py:class:`~buildingmotif.dataclasses.manifest.Manifest`::

            model.manifest.add(brick_library)
            model.manifest.remove("urn:my/old-shapes")
            model.manifest.library_names

        :return: this model's manifest
        :rtype: Manifest
        """
        from buildingmotif.dataclasses.manifest import Manifest

        return Manifest.for_model(self)

    def get_manifest(self) -> "Manifest":
        """The set of libraries this model is validated and compiled against.

        .. deprecated::
            Use :py:attr:`manifest`. **The return type changed**: a manifest
            now names libraries rather than holding a copy of their shapes, so
            this returns a
            :py:class:`~buildingmotif.dataclasses.manifest.Manifest` where it
            used to return the
            :py:class:`~buildingmotif.dataclasses.shape_collection.ShapeCollection`
            the manifest is stored in. Code that appended to
            ``get_manifest().graph`` must create a Library for those shapes and
            add it; code that passed ``get_manifest()`` to ``validate()`` wants
            ``model.manifest.shape_collections()``.

        :return: this model's manifest
        :rtype: Manifest
        """
        warnings.warn(
            "Model.get_manifest() is deprecated; use Model.manifest. It now "
            "returns a Manifest -- a set of libraries -- rather than the "
            "ShapeCollection the manifest is stored in.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.manifest

    def add_to_manifest(
        self,
        *libraries: Union["LibraryRef", Iterable["LibraryRef"]],
        resolve: bool = True,
    ) -> None:
        """Add libraries to this model's manifest.

        A convenience for :py:meth:`Manifest.add`; ``model.manifest.add(...)``
        is the same call.

        :param libraries: :py:class:`Library` objects, library names, or
            iterables of either
        :param resolve: if True (default), a name that is not already a loaded
            library is resolved through the ontology environment and loaded
        :type resolve: bool
        :raises TypeError: if handed a ShapeCollection. This used to be the
            argument type: the manifest absorbed a copy of the collection's
            shapes. It names libraries now, so the shapes need one.
        """
        self.manifest.add(*libraries, resolve=resolve)

    def remove_from_manifest(
        self, *libraries: Union["LibraryRef", Iterable["LibraryRef"]]
    ) -> None:
        """Remove libraries from this model's manifest.

        A convenience for :py:meth:`Manifest.discard`: a library that is not in
        the manifest is ignored, since what the caller asked for -- that this
        model no longer claim to satisfy it -- is already true.
        """
        self.manifest.discard(*libraries)
