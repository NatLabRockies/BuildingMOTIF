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
from buildingmotif.shacl import DEFAULT_SHACL_ENGINE, normalize_shacl_engine


class BuildingMOTIF(metaclass=Singleton):
    """Manages BuildingMOTIF data classes."""

    def __init__(
        self,
        db_uri: str,
        shacl_engine: Optional[str] = DEFAULT_SHACL_ENGINE,
        log_level=logging.WARNING,
        log_file: Optional[Union[str, Path]] = None,
        ontology_cache_path: Optional[Union[str, Path]] = None,
        ontology_search_directories: Optional[Iterable[Union[str, Path]]] = None,
        ontology_fetch_imports: bool = True,
        ontology_offline: bool = False,
        ontology_strict: bool = False,
        graph_store_path: Optional[Union[str, Path]] = None,
        knowledge_index_path: Optional[Union[str, Path]] = None,
        knowledge_service=None,
        create_tables: bool = True,
    ) -> None:
        """Class constructor.

        :param db_uri: database URI
        :type db_uri: str
        :param shacl_engine: the name of the engine to use for validation: "pyshifty", "pyshacl", or "topquadrant". "shifty" is
            accepted as an alias for "pyshifty". Using topquadrant
            requires Java to be installed on this machine, and the "topquadrant" feature on BuildingMOTIF,
            defaults to "pyshifty"
        :type shacl_engine: str, optional
        :param log_level: logging level of detail for the stream handler
        :type log_level: int
        :param log_file: path to write a DEBUG-level log to. Defaults to None
            (no log file). This used to be an unconditional ``BuildingMOTIF.log``
            in the current working directory; it is opt-in now.
        :type log_file: Optional[Union[str, Path]]
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
        :param knowledge_index_path: path for a persistent local knowledge
            index. When supplied, ``bm.knowledge`` provides Docling/Qdrant
            indexing and retrieval and the ``knowledge`` extra is required.
        :param knowledge_service: a pre-built knowledge service for dependency
            injection or a custom index backend. Mutually exclusive with
            ``knowledge_index_path``.
        :param create_tables: if true (the default), create any missing
            BuildingMOTIF tables in the database. This is idempotent and never
            drops or alters an existing table. Pass False when the schema is
            managed out of band -- e.g. by the Alembic migrations under
            ``migrations/`` -- so this instance never touches the schema.
        :type create_tables: bool
        """
        if knowledge_index_path is not None and knowledge_service is not None:
            raise ValueError(
                "knowledge_index_path and knowledge_service are mutually exclusive"
            )
        self.db_uri = db_uri
        self.shacl_engine = normalize_shacl_engine(shacl_engine)
        self.ontology_fetch_imports = ontology_fetch_imports
        self.engine = create_engine(
            db_uri,
            echo=False,
            json_serializer=_custom_json_serializer,
            json_deserializer=_custom_json_deserializer,
        )
        self.session_factory = sessionmaker(bind=self.engine, autoflush=True)
        self.Session = scoped_session(self.session_factory)

        self.setup_logging(log_level, log_file)

        # Create any missing tables up front. This used to happen only for
        # in-memory SQLite, so the first thing a user did against a file-backed
        # or Postgres database failed with a bare "no such table" from the
        # driver unless they knew to call setup_tables() themselves. create_all
        # is idempotent and only ever adds missing tables.
        if create_tables:
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
        self._knowledge = knowledge_service
        if knowledge_index_path is not None:
            from buildingmotif.knowledge import KnowledgeService

            self._knowledge = KnowledgeService.local(self, knowledge_index_path)

    @property
    def has_knowledge(self) -> bool:
        """Return whether document indexing and retrieval are configured."""
        return self._knowledge is not None

    @property
    def knowledge(self):
        """Return this instance's configured knowledge service."""
        if self._knowledge is None:
            from buildingmotif.knowledge.errors import KnowledgeIndexNotConfigured

            raise KnowledgeIndexNotConfigured(
                "knowledge retrieval is not configured; pass knowledge_index_path "
                "to BuildingMOTIF or inject a knowledge_service"
            )
        return self._knowledge

    def configure_knowledge(self, service) -> None:
        """Attach a custom knowledge service to this BuildingMOTIF instance."""
        if self._knowledge is not None and self._knowledge is not service:
            self._knowledge.close()
        self._knowledge = service

    @property
    def shacl_engine(self) -> str:
        return self._shacl_engine

    @shacl_engine.setter
    def shacl_engine(self, engine: Optional[str]) -> None:
        self._shacl_engine = normalize_shacl_engine(engine)

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

    # marks the handlers this class installed, so repeated construction can
    # replace them instead of stacking more on the root logger
    _HANDLER_TAG = "_buildingmotif_handler"

    def setup_logging(self, log_level, log_file=None):
        """Attach a stream handler at ``log_level``, and optionally a DEBUG file
        handler.

        Three things this deliberately does *not* do, because a library should
        not do them to its host application:

        - **Stack handlers.** Handlers this class installed earlier are removed
          first. They used to accumulate: every construction added two more to
          the root logger, unbounded, so a test suite that builds and cleans the
          singleton hundreds of times ended up formatting each record hundreds
          of times.
        - **Force the root logger to DEBUG.** The root level is now only lowered
          as far as is actually needed to let ``log_level`` records through (or
          to DEBUG when a log file is requested, since that handler wants
          everything).
        - **Write a log file unless asked.** ``BuildingMOTIF.log`` used to be
          created in the current working directory on every construction, in
          ``"w"`` mode. Pass ``log_file`` to opt in.

        :param log_level: logging level for the stream handler
        :type log_level: int
        :param log_file: path to write a DEBUG-level log to; None (default)
            installs no file handler
        :type log_file: Optional[Union[str, Path]]
        """
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            if getattr(handler, self._HANDLER_TAG, False):
                root_logger.removeHandler(handler)
                handler.close()

        formatter = logging.Formatter(
            "%(asctime)s | %(name)s |  %(levelname)s: %(message)s"
        )

        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARN)
        logging.getLogger("sqlalchemy.pool").setLevel(logging.WARN)

        handlers: list = []
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(log_level)
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)

        wanted_level = log_level
        if log_file is not None:
            log_file_handler = logging.FileHandler(os.fspath(log_file), mode="w")
            log_file_handler.setLevel(logging.DEBUG)
            log_file_handler.setFormatter(formatter)
            handlers.append(log_file_handler)
            wanted_level = logging.DEBUG

        # only lower the root level; never raise it, which would silence
        # whatever the host application configured
        if root_logger.level == logging.NOTSET or root_logger.level > wanted_level:
            root_logger.setLevel(wanted_level)

        for handler in handlers:
            setattr(handler, self._HANDLER_TAG, True)
            root_logger.addHandler(handler)

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

    def __enter__(self) -> "BuildingMOTIF":
        """Enter a BuildingMOTIF session.

        Using the instance as a context manager ties the SQL side of the two
        stores to the block::

            with BuildingMOTIF("sqlite:///bldg.db") as bm:
                model = Model.create("urn:bldg/")
                model.add_graph(g)
            # committed and closed here

        On a clean exit the session is committed; on an exception it is rolled
        back. Either way the instance is closed (which also reclaims orphaned
        graphs) and the singleton is reset, so a later ``BuildingMOTIF(...)``
        constructs a fresh instance instead of handing back this closed one.

        This matters because BuildingMOTIF spans two stores: triples are written
        through to Oxigraph immediately, while the rows that point at them live
        in SQL and are only durable once the session commits. Leaving the block
        without committing would leave triples on disk that no model or library
        row references.

        :return: this instance
        :rtype: BuildingMOTIF
        """
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Commit (or roll back) and close the instance. See :py:meth:`__enter__`."""
        try:
            if exc_type is None:
                # let a failed commit propagate -- the caller needs to know
                # their work did not persist
                self.session.commit()
            else:
                # best-effort: a failure here must not mask the exception that
                # is already on its way out of the block
                try:
                    self.session.rollback()
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Rollback failed while exiting the BuildingMOTIF context",
                        exc_info=True,
                    )
        finally:
            try:
                self.close()
            finally:
                # drop the singleton so the next constructor call builds a new
                # instance rather than returning this closed one
                type(self).clean()

    def close(self) -> None:
        """Close session and engine."""
        if self._knowledge is not None:
            try:
                self._knowledge.close()
            except Exception:
                logging.getLogger(__name__).warning(
                    "Knowledge service close failed", exc_info=True
                )
            self._knowledge = None
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
        return BuildingMOTIF.instance
    raise SingletonNotInstantiatedException
