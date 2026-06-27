import logging
import os
from pathlib import Path
from typing import Iterable, Optional, Union

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
from buildingmotif.namespaces import bind_prefixes
from buildingmotif.ontology_environment import OntologyEnvironment


class BuildingMOTIF(metaclass=Singleton):
    """Manages BuildingMOTIF data classes."""

    def __init__(
        self,
        db_uri: str,
        shacl_engine: Optional[str] = "pyshacl",
        log_level=logging.WARNING,
        ontology_cache_path: Optional[Union[str, Path]] = None,
        ontology_search_directories: Optional[Iterable[Union[str, Path]]] = None,
        ontology_fetch_imports: bool = True,
        ontology_offline: bool = False,
        ontology_strict: bool = False,
        graph_store_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Class constructor.

        :param db_uri: database URI
        :type db_uri: str
        :param shacl_engine: the name of the engine to use for validation: "pyshacl" or "topquadrant". Using topquadrant
            requires Java to be installed on this machine, and the "topquadrant" feature on BuildingMOTIF,
            defaults to "pyshacl"
        :type shacl_engine: str, optional
        :param log_level: logging level of detail
        :type log_level: int
        :default log_level: INFO
        :param ontology_cache_path: path to the ontoenv workspace. If omitted,
            an in-memory temporary environment is used.
        :param ontology_search_directories: directories ontoenv should scan when
            resolving imports.
        :param ontology_fetch_imports: default for whether library loading should
            fetch owl:imports dependencies.
        :param ontology_offline: if true, ontoenv will not fetch remote imports.
        :param ontology_strict: if true, ontoenv treats missing imports as errors.
        :param graph_store_path: directory for the Oxigraph graph store. If
            omitted, GRAPH_STORE_PATH is used when set. File-backed SQLite
            databases default to <sqlite-db-file>.oxigraph. In-memory SQLite
            databases use an in-memory graph store. Other databases default to
            .buildingmotif-oxigraph in the current working directory.
        """
        self.db_uri = db_uri
        self.shacl_engine = shacl_engine or "pyshacl"
        self.ontology_fetch_imports = ontology_fetch_imports
        self.engine = create_engine(
            db_uri,
            echo=False,
            json_serializer=_custom_json_serializer,
            json_deserializer=_custom_json_deserializer,
        )
        self.session_factory = sessionmaker(bind=self.engine, autoflush=True)
        self.Session = scoped_session(self.session_factory)

        self.setup_logging(log_level)

        # setup tables automatically if using a in-memory sqlite database
        if self._is_in_memory_sqlite():
            self.setup_tables()

        self.table_connection = TableConnection(self.engine, self)
        self.graph_store_path = self._resolve_graph_store_path(graph_store_path)
        self.graph_connection = GraphConnection(self.graph_store_path)

        g = Graph()
        bind_prefixes(g)
        self.template_ns_mgr: NamespaceManager = NamespaceManager(g)
        self.ontology_environment = OntologyEnvironment(
            path=ontology_cache_path,
            search_directories=ontology_search_directories,
            offline=ontology_offline,
            strict=ontology_strict,
            graph_connection=self.graph_connection,
        )

    @property
    def session(self):
        return self.Session()

    def setup_tables(self):
        """Creates all tables in the underlying database."""
        BuildingMOTIFBase.metadata.create_all(self.engine)

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

    def _resolve_graph_store_path(
        self, graph_store_path: Optional[Union[str, Path]]
    ) -> Optional[Path]:
        """Resolve the Oxigraph graph store path for this instance."""
        if graph_store_path is not None:
            return Path(graph_store_path)

        env_graph_store_path = os.getenv("GRAPH_STORE_PATH")
        if env_graph_store_path:
            return Path(env_graph_store_path)

        if self.engine.dialect.name == "sqlite":
            if self._is_in_memory_sqlite():
                return None
            database = self.engine.url.database
            if database:
                return Path(f"{database}.oxigraph")
            return None

        return Path(".buildingmotif-oxigraph")

    def setup_logging(self, log_level):
        """Create log file with DEBUG level and stdout handler with specified
        logging level.

        :param log_level: logging level of detail
        :type log_level: int
        """
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s | %(name)s |  %(levelname)s: %(message)s"
        )

        log_file_handler = logging.FileHandler(
            os.path.join(os.getcwd(), "BuildingMOTIF.log"), mode="w"
        )
        log_file_handler.setLevel(logging.DEBUG)
        log_file_handler.setFormatter(formatter)

        engine_logger = logging.getLogger("sqlalchemy.engine")
        pool_logger = logging.getLogger("sqlalchemy.pool")

        engine_logger.setLevel(logging.WARN)
        pool_logger.setLevel(logging.WARN)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)

        root_logger.addHandler(log_file_handler)
        root_logger.addHandler(stream_handler)

    def collect_graph_garbage(self) -> list:
        """Reclaim orphaned named graphs no longer referenced by any table row.

        Copy-on-write graph replacement and row deletion leave behind
        unreferenced Oxigraph named graphs; this removes them. Only graphs with
        UUID identifiers (models, shape collections, template bodies) are
        considered, so OntoEnv-managed ontology graphs are never touched. Safe
        to call when no write transaction is in flight.

        :return: identifiers of the graphs that were reclaimed
        :rtype: list
        """
        live_ids = self.table_connection.get_all_graph_ids()
        return self.graph_connection.collect_garbage(live_ids)

    def close(self) -> None:
        """Close session and engine."""
        try:
            self.collect_graph_garbage()
        except Exception:
            logging.getLogger(__name__).warning(
                "Graph garbage collection failed during close", exc_info=True
            )
        try:
            self.ontology_environment.close()
        finally:
            try:
                self.graph_connection.close()
            finally:
                try:
                    self.session.close()
                finally:
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
