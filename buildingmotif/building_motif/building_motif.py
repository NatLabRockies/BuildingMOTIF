import logging
import os
from contextlib import contextmanager
from typing import Optional

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
from buildingmotif.shacl import normalize_shacl_engine


class BuildingMOTIF(metaclass=Singleton):
    """Manages BuildingMOTIF data classes."""

    def __init__(
        self,
        db_uri: str,
        shacl_engine: Optional[str] = "pyshacl",
        log_level=logging.WARNING,
    ) -> None:
        """Class constructor.

        :param db_uri: database URI
        :type db_uri: str
        :param shacl_engine: the name of the engine to use for validation: "pyshacl", "shifty", or "topquadrant". Using topquadrant
            requires Java to be installed on this machine, and the "topquadrant" feature on BuildingMOTIF,
            defaults to "pyshacl"
        :type shacl_engine: str, optional
        :param log_level: logging level of detail
        :type log_level: int
        :default log_level: INFO
        """
        self.db_uri = db_uri
        self.shacl_engine = normalize_shacl_engine(shacl_engine)
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
        self.graph_connection = GraphConnection(
            BuildingMotifEngine(self.engine, self.Session)
        )

        g = Graph()
        bind_prefixes(g)
        self.template_ns_mgr: NamespaceManager = NamespaceManager(g)

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

    def close(self) -> None:
        """Close session and engine."""
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
