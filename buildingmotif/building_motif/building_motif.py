import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

from rdflib import Graph
from rdflib.namespace import NamespaceManager
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from buildingmotif.building_motif.singleton import (
    Singleton,
    SingletonNotInstantiatedException,
)
from buildingmotif.database.graph_connection import GraphConnection
from buildingmotif.database.table_connection import TableConnection
from buildingmotif.database.tables import Base as BuildingMOTIFBase
from buildingmotif.database.utils import (
    _custom_json_deserializer,
    _custom_json_serializer,
)
from buildingmotif.dependency_resolver import build_dependency_resolver
from buildingmotif.namespaces import bind_prefixes


class BuildingMOTIF(metaclass=Singleton):
    """Manages BuildingMOTIF data classes."""

    def __init__(
        self,
        db_uri: str,
        shacl_engine: Optional[str] = "pyshifty",
        dependency_resolver: str = "ontoenv",
        ontoenv_kwargs: Optional[Dict[str, Any]] = None,
        log_level=logging.WARNING,
    ) -> None:
        """Class constructor.

        :param db_uri: database URI
        :type db_uri: str
        :param shacl_engine: the name of the engine to use for validation: "pyshacl",
            "topquadrant", or "pyshifty". Using topquadrant requires Java to be
            installed on this machine, and the "topquadrant" feature on
            BuildingMOTIF, defaults to "pyshacl"
        :type shacl_engine: str, optional
        :param log_level: logging level of detail
        :type log_level: int
        :default log_level: INFO
        """
        self.db_uri = db_uri
        self.shacl_engine = shacl_engine or "pyshifty"
        self.log_level = log_level
        self.dependency_resolver_name = dependency_resolver
        self.engine = create_engine(
            db_uri,
            echo=False,
            json_serializer=_custom_json_serializer,
            json_deserializer=_custom_json_deserializer,
        )
        self.session_factory = sessionmaker(bind=self.engine, autoflush=True)
        self.Session = scoped_session(self.session_factory)

        # setup tables automatically if using a in-memory sqlite database
        if self._is_in_memory_sqlite():
            self.setup_tables()

        self.table_connection = TableConnection(self.engine, self)
        self.graph_connection = GraphConnection(
            BuildingMotifEngine(self.engine, self.Session)
        )
        self.ontology_resolver = build_dependency_resolver(
            self,
            resolver_name=dependency_resolver,
            ontoenv_kwargs=ontoenv_kwargs,
        )

        g = Graph()
        bind_prefixes(g)
        self.template_ns_mgr: NamespaceManager = NamespaceManager(g)

    @property
    def session(self):
        return self.Session()

    def setup_tables(self):
        """Creates all tables in the underlying database."""
        BuildingMOTIFBase.metadata.create_all(self.engine)
        if hasattr(self, "ontology_resolver"):
            self.ontology_resolver.rebuild_from_graph_store()

    def _scope_ontology_graphs(self, library=None, model=None):
        from buildingmotif.dataclasses.library import Library
        from buildingmotif.dataclasses.model import Model

        if library is not None and model is not None:
            raise ValueError("Pass only one of 'library' or 'model'")

        if library is not None:
            graph = library.get_shape_collection().graph
            return [(graph, str(library.name))]

        if model is not None:
            manifest = model.get_manifest()
            manifest_name = manifest.graph_name
            return [
                (model.graph, str(model.name)),
                (
                    manifest.graph,
                    str(manifest_name) if manifest_name is not None else None,
                ),
            ]

        graphs = []
        for db_library in self.table_connection.get_all_db_libraries():
            scoped_library = Library.load(db_id=db_library.id)
            graphs.append(
                (scoped_library.get_shape_collection().graph, str(scoped_library.name))
            )

        for db_model in self.table_connection.get_all_db_models():
            scoped_model = Model.load(id=db_model.id)
            manifest = scoped_model.get_manifest()
            manifest_name = manifest.graph_name
            graphs.extend(
                [
                    (scoped_model.graph, str(scoped_model.name)),
                    (
                        manifest.graph,
                        str(manifest_name) if manifest_name is not None else None,
                    ),
                ]
            )

        return graphs

    def list_ontology_closure(self, library=None, model=None) -> list[str]:
        """List resolved ontology imports for a specific library or model."""
        scoped_graphs = self._scope_ontology_graphs(library=library, model=model)
        if library is None and model is None:
            raise ValueError("Pass either 'library' or 'model'")

        closure = set()
        for graph, graph_name in scoped_graphs:
            closure.update(
                self.ontology_resolver.get_closure(
                    graph,
                    graph_name=graph_name,
                    error_on_missing_imports=False,
                )
            )
        return sorted(closure)

    def list_missing_ontologies(self, library=None, model=None) -> list[str]:
        """List missing ontology imports globally or for a specific library/model."""
        scoped_graphs = self._scope_ontology_graphs(library=library, model=model)
        graphs = [graph for graph, _graph_name in scoped_graphs]
        return self.ontology_resolver.get_missing_ontologies(graphs)

    def _is_in_memory_sqlite(self) -> bool:
        """Returns true if the BuildingMOTIF instance uses an in-memory SQLite
        database.
        """
        if self.engine.dialect.name != "sqlite":
            return False
        # get the 'filename' of the database; if this is empty, the db is in-memory
        raw_conn = self.engine.raw_connection()
        filename = (
            raw_conn.cursor()
            .execute("select file from pragma_database_list where name='main';", ())
            .fetchone()
        )
        # length is 0 if the db is in-memory
        return not len(filename[0])

    def close(self) -> None:
        """Close session and engine."""
        self.ontology_resolver.close()
        self.session.close()
        self.engine.dispose()


def get_building_motif() -> "BuildingMOTIF":
    """Returns singleton instance of BuildingMOTIF.

    Requires that BuildingMOTIF has been instantiated before, otherwise raises
    an exception.

    :raises SingletonNotInstantiatedException: if buildingmotif hasn't been
        instantiated
    :return: singleton instance of buildingmotif
    :rtype: BuildingMOTIF
    """
    if hasattr(BuildingMOTIF, "instance"):
        return BuildingMOTIF.instance  # type: ignore
    raise SingletonNotInstantiatedException


class BuildingMotifEngine:
    """BuildingMotifEngine is a class that wraps a SQLAlchemy Engine and
    Session.

    This enables the use of sessioned transactions in rdflib-sqlalchemy.
    If we are experiencing weird graph database issues this may be the cause.
    """

    def __init__(self, engine, Session) -> None:
        self.engine = engine
        self.Session = Session

    # begin and connect attributes are queried from the wrapped session.

    @contextmanager
    def begin(self):
        yield self.Session()

    @contextmanager
    def connect(self):
        yield self.Session()

    def __getattr__(self, attr):
        # When an attribute is requested, see if we have overriden it
        # If we have not return the attr of the wrapped engine
        if attr in self.__dict__:
            return getattr(self, attr)
        return getattr(self.engine, attr)
