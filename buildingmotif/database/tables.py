from typing import Dict, List, Optional

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, Session, declarative_base, relationship

# from sqlalchemy.dialects.postgresql import JSON
from buildingmotif.database.utils import JSONType

Base = declarative_base()


# https://docs.sqlalchemy.org/en/14/dialects/sqlite.html#foreign-key-support
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class DBModel(Base):
    """A Model is a metadata model of all or part of a building."""

    __tablename__ = "models"
    id: Mapped[int] = Column(Integer, primary_key=True)
    name: Mapped[str] = Column(String())
    description: Mapped[str] = Column(Text(), default="", nullable=False)
    graph_id: Mapped[str] = Column(String())
    manifest_id: Mapped[int] = Column(
        Integer, ForeignKey("shape_collection.id", ondelete="CASCADE"), nullable=False
    )
    manifest: "DBShapeCollection" = relationship(
        "DBShapeCollection",
        uselist=False,
        cascade="all",
        passive_deletes=True,
    )


class DBShapeCollection(Base):
    """A ShapeCollection is a collection of shapes, which are used to validate
    parts of a model.
    """

    __tablename__ = "shape_collection"
    id: Mapped[int] = Column(Integer, primary_key=True)
    graph_id: Mapped[str] = Column(String())


class DBLibrary(Base):
    """A Library is a distributable collection of Templates and Shapes."""

    __tablename__ = "library"
    id: Mapped[int] = Column(Integer, primary_key=True)
    name: Mapped[str] = Column(String(), nullable=False, unique=True)

    # do not use passive_deletes here because we want to handle the deletion of templates
    templates: Mapped[List["DBTemplate"]] = relationship(
        "DBTemplate", back_populates="library", cascade="all"
    )

    shape_collection_id = Column(
        Integer, ForeignKey("shape_collection.id", ondelete="CASCADE"), nullable=False
    )
    shape_collection: DBShapeCollection = relationship(
        "DBShapeCollection",
        uselist=False,
        cascade="all",
        passive_deletes=True,
    )


class DBTemplate(Base):
    """A Template is used to generate content for a model."""

    # TODO: doc table properties better.
    __tablename__ = "template"
    id: Mapped[int] = Column(Integer, primary_key=True)
    name: Mapped[str] = Column(String(), nullable=False)
    body_id: Mapped[str] = Column(String())
    optional_args: Mapped[List[str]] = Column(JSONType)  # type: ignore

    library_id: Mapped[int] = Column(
        Integer, ForeignKey("library.id", ondelete="CASCADE"), nullable=False
    )
    library: Mapped[DBLibrary] = relationship("DBLibrary", back_populates="templates")

    dependencies: Mapped[List["DBTemplateDependency"]] = relationship(
        "DBTemplateDependency", back_populates="template", cascade="all,delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "name",
            "library_id",
            name="name_library_unique_constraint",
        ),
    )


class DBTemplateDependency(Base):
    __tablename__ = "template_dependency"
    id: Mapped[int] = Column(Integer, primary_key=True)

    template_id: Mapped[int] = Column(
        Integer, ForeignKey("template.id", ondelete="CASCADE"), nullable=False
    )
    template: Mapped[DBTemplate] = relationship(
        DBTemplate, back_populates="dependencies"
    )

    dependency_library_name: Mapped[str] = Column(String, nullable=False)
    dependency_template_name: Mapped[str] = Column(String, nullable=False)

    # args are a mapping of dependee args to dependant args
    args: Mapped[Dict[str, str]] = Column(JSONType)  # type: ignore

    @hybrid_property
    def dependency_template(self) -> Optional[DBTemplate]:
        session = Session.object_session(self)
        statement = (
            select(DBTemplate)
            .join(DBTemplate.library)
            .where(
                DBTemplate.name == self.dependency_template_name,
                DBLibrary.name == self.dependency_library_name,
            )
        )
        try:
            return session.scalars(statement).one()
        except NoResultFound:
            return None

    @dependency_template.expression
    def _dependency_tempalate(self):
        return (
            select(DBTemplate)
            .join(DBTemplate.library)
            .where(
                DBTemplate.name == self.dependency_template_name,
                DBLibrary.name == self.dependency_library_name,
            )
        )

    __table_args__ = (
        UniqueConstraint(
            "template_id",
            "dependency_library_name",
            "dependency_template_name",
            "args",
            name="template_dependency_unique_constraint",
        ),
    )
