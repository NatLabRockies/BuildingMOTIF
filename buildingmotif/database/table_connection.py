import logging
import uuid
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoResultFound

from buildingmotif.database.errors import (
    LibraryNotFound,
    ModelNotFound,
    ShapeCollectionNotFound,
    TemplateNotFound,
)
from buildingmotif.database.tables import (
    DBLibrary,
    DBModel,
    DBShapeCollection,
    DBTemplate,
    DBTemplateDependency,
)


class TableConnection:
    """Controls interaction with the database."""

    def __init__(self, engine: Engine, bm) -> None:
        """Class constructor.

        :param engine: database engine
        :type engine: Engine
        :param bm: contains the session to use
        :type bm: BuildingMOTIF
        """
        self.logger = logging.getLogger(__name__)
        self.bm = bm

    # model functions

    def create_db_model(self, name: str, description: str = "") -> DBModel:
        """Create a database model.

        :param name: name of DBModel
        :type name: str
        :param description: description of the model
        :type description: str
        :return: DBModel
        :rtype: DBModel
        """
        manifest_id = str(uuid.uuid4())
        self.logger.debug(f"Creating shape collection in model: '{name}'")
        manifest = DBShapeCollection(graph_id=manifest_id)
        self.bm.session.add(manifest)

        graph_id = str(uuid.uuid4())
        self.logger.debug(f"Creating model: '{name}', with graph: '{graph_id}'")
        db_model = DBModel(
            name=name,
            graph_id=graph_id,
            description=description,
            manifest=manifest,
        )
        self.bm.session.add(db_model)

        self.bm.session.flush()

        return db_model

    def get_all_db_models(self) -> List[DBModel]:
        """Get all database models.

        :return: all DBModels
        :rtype: List[DBModel]
        """
        return self.bm.session.query(DBModel).all()

    def get_db_model(self, id: int) -> DBModel:
        """Get database model by id.

        :param id: id of DBModel
        :type id: int
        :return: DBModel
        :rtype: DBModel
        """
        try:
            db_model = self.bm.session.query(DBModel).filter(DBModel.id == id).one()
        except NoResultFound:
            raise ModelNotFound(idnum=id)
        return db_model

    def get_db_model_by_name(self, name: str) -> DBModel:
        """Get database model by name.

        :param name: name of DBModel
        :type name: str
        :return: DBModel
        :rtype: DBModel
        """
        try:
            db_model = self.bm.session.query(DBModel).filter(DBModel.name == name).one()
        except NoResultFound:
            raise ModelNotFound(name=name)
        return db_model

    def update_db_model_name(self, id: int, name: str) -> None:
        """Update database model name.

        :param id: id of DBModel
        :type id: int
        :param name: new name
        :type name: str
        """
        db_model = self.get_db_model(id)
        self.logger.debug(f"Updating model name from: '{db_model.name}' to: '{name}'")
        db_model.name = name

    def update_db_model_description(self, id: int, description: str) -> None:
        """Update database model description.

        :param id: id of DBModel
        :type id: int
        :param description: new description
        :type description: str
        """
        db_model = self.get_db_model(id)
        self.logger.debug(
            f"Updating model description from: '{db_model.description}' to: '{description}'"
        )
        db_model.description = description

    def update_db_model_graph_id(self, id: int, graph_id: str) -> None:
        """Point a database model at a new graph identifier (copy-on-write).

        :param id: id of DBModel
        :type id: int
        :param graph_id: the new graph identifier
        :type graph_id: str
        """
        db_model = self.get_db_model(id)
        self.logger.debug(
            f"Updating model graph id from: '{db_model.graph_id}' to: '{graph_id}'"
        )
        db_model.graph_id = graph_id

    def delete_db_model(self, id: int) -> None:
        """Delete database model.

        :param id: id of deleted DBModel
        :type id: int
        """

        db_model = self.get_db_model(id)
        self.logger.debug(f"Deleting model: '{db_model.name}'")
        self.bm.session.delete(db_model)

    # shape collection functions
    def create_db_shape_collection(self) -> DBShapeCollection:
        """Create a database shape collection.

        :return: DBShapeCollection
        :rtype: DBShapeCollection
        """
        db_shape_collection = DBShapeCollection(graph_id=str(uuid.uuid4()))

        self.bm.session.add(db_shape_collection)
        self.bm.session.flush()

        return db_shape_collection

    def get_all_db_shape_collections(self) -> List[DBShapeCollection]:
        """Get all database shape collections.

        :return: all DBShapeCollections
        :rtype: List[DBShapeCollection]
        """
        return self.bm.session.query(DBShapeCollection).all()

    def get_db_shape_collection(self, id: int) -> DBShapeCollection:
        """Get database shape collection by id.

        :param id: id of DBShapeCollection
        :type id: int
        :return: DBShapeCollection
        :rtype: DBShapeCollection
        """
        try:
            return (
                self.bm.session.query(DBShapeCollection)
                .filter(DBShapeCollection.id == id)
                .one()
            )
        except NoResultFound:
            raise ShapeCollectionNotFound(idnum=id)

    def update_db_shape_collection_graph_id(self, id: int, graph_id: str) -> None:
        """Point a shape collection at a new graph identifier (copy-on-write).

        :param id: id of DBShapeCollection
        :type id: int
        :param graph_id: the new graph identifier
        :type graph_id: str
        """
        db_shape_collection = self.get_db_shape_collection(id)
        self.logger.debug(
            f"Updating shape collection graph id from: "
            f"'{db_shape_collection.graph_id}' to: '{graph_id}'"
        )
        db_shape_collection.graph_id = graph_id

    def delete_db_shape_collection(self, id: int) -> None:
        """Delete database shape collection.

        :param id: id of deleted DBShapeCollection
        :type id: int
        """
        db_shape_collection = self.get_db_shape_collection(id)
        self.bm.session.delete(db_shape_collection)

    # library functions

    def create_db_library(self, name: str) -> DBLibrary:
        """Create database library.

        :param name: name of DBLibrary
        :type name: str
        :return: DBLibrary
        :rtype: DBLibrary
        """
        self.logger.debug(f"Creating shape collection in library: '{name}'")
        shape_collection = DBShapeCollection(graph_id=str(uuid.uuid4()))
        self.bm.session.add(shape_collection)

        self.logger.debug(f"Creating database library: '{name}'")
        library = DBLibrary(name=name, shape_collection=shape_collection)
        self.bm.session.add(library)

        self.bm.session.flush()

        return library

    def get_all_db_libraries(self) -> List[DBLibrary]:
        """Get all database libraries.

        :return: all DBLibrary
        :rtype: List[DBLibrary]
        """
        db_libraries = self.bm.session.query(DBLibrary).all()
        return db_libraries

    def get_db_library(self, id: int) -> DBLibrary:
        """Get database library by id.

        :param id: id of DBLibrary
        :type id: int
        :return: DBLibrary
        :rtype: DBLibrary
        """
        try:
            db_library = (
                self.bm.session.query(DBLibrary).filter(DBLibrary.id == id).one()
            )
        except NoResultFound:
            raise LibraryNotFound(idnum=id)
        return db_library

    def get_db_library_by_name(self, name: str) -> DBLibrary:
        """Get database library by name.

        :param name: name of DBLibrary
        :type name: str
        :return: DBLibrary
        :rtype: DBLibrary
        """
        try:
            return self.bm.session.query(DBLibrary).filter(DBLibrary.name == name).one()
        except NoResultFound:
            raise LibraryNotFound(name=name)

    def update_db_library_name(self, id: int, name: str) -> None:
        """Update database library name.

        :param id: id of DBLibrary
        :type id: int
        :param name: new name
        :type name: str
        """
        db_library = self.get_db_library(id)
        self.logger.debug(
            f"Updating database library name: '{db_library.name}' -> '{name}'"
        )
        db_library.name = name

    def delete_db_library(self, id: int) -> None:
        """Delete database library.

        :param id: id of deleted DBLibrary
        :type id: int
        """

        db_library = self.get_db_library(id)

        self.logger.debug(f"Deleting database library: '{db_library.name}'")
        self.bm.session.delete(db_library)

    # template functions

    def create_db_template(self, name: str, library_id: int) -> DBTemplate:
        """Create database template.

        :param name: name of DBTemplate
        :type name: str
        :param library_id: id of the template's library
        :type library_id: int
        :return: DBTemplate
        :rtype: DBTemplate
        """
        self.logger.debug(f"Creating database template: '{name}'")
        library = self.get_db_library(library_id)
        template = DBTemplate(
            name=name,
            body_id=str(uuid.uuid4()),
            optional_args=[],  # type: ignore
            library=library,
        )

        self.bm.session.add(template)
        self.bm.session.flush()

        return template

    def get_all_db_templates(self) -> List[DBTemplate]:
        """Get all database templates.

        :return: all DBTemplate
        :rtype: List[DBTemplate]
        """
        db_templates = self.bm.session.query(DBTemplate).all()
        return db_templates

    def get_db_template(self, id: int) -> DBTemplate:
        """Get database template by id.

        :param id: id of DBTemplate
        :type id: int
        :return: DBTemplate
        :rtype: DBTemplate
        """
        try:
            db_template = (
                self.bm.session.query(DBTemplate).filter(DBTemplate.id == id).one()
            )
        except NoResultFound:
            raise TemplateNotFound(idnum=id)
        return db_template

    def get_db_template_by_name(
        self, name: str, library_id: Optional[int] = None
    ) -> DBTemplate:
        """Get database template by name.

        :param name: name of DBTemplate
        :type name: str
        :param library_id: optional id of the template's library
        :type library_id: Optional[int]
        :return: DBTemplate
        :rtype: DBTemplate
        """
        try:
            query = self.bm.session.query(DBTemplate).filter(DBTemplate.name == name)
            if library_id is not None:
                query = query.filter(DBTemplate.library_id == library_id)
            db_template = query.one()
        except NoResultFound:
            raise TemplateNotFound(name=name)
        return db_template

    def get_library_defining_db_template(self, id: int) -> DBLibrary:
        """Returns the library defining the given template.

        :param id: id of template
        :type id: int
        :return: DBLibrary
        :rtype: DBLibrary
        """
        return self.get_db_template(id).library

    def get_db_template_dependencies(self, id: int) -> Tuple[DBTemplateDependency, ...]:
        """Get a template's dependencies and its arguments.

        If you don't need the arguments, consider using
        :py:method:`dataclasses.template.get_dependencies`.

        :param id: template id
        :type id: int
        :return: tuple of tuple, where each tuple has the dependant_id
            and it's args
        :rtype: tuple[tuple[int, list[str]]]
        """
        db_template_dependencies = tuple(
            self.bm.session.query(DBTemplateDependency)
            .filter(DBTemplateDependency.template_id == id)
            .all()
        )
        return db_template_dependencies

    def get_db_template_dependency(self, id: int) -> Optional[DBTemplateDependency]:
        """Get template dependency object by its id

        :param id: template dependency id
        :type id: int
        :return: the template dependency or None
        :rtype: Optional[DBTemplateDependency]"""
        try:
            return (
                self.bm.session.query(DBTemplateDependency)
                .filter(DBTemplateDependency.id == id)
                .one()
            )
        except NoResultFound:
            return None

    def update_db_template_name(self, id: int, name: str) -> None:
        """Update database template name.

        :param id: id of DBTemplate
        :type id: int
        :param name: new name
        :type name: str
        """
        db_template = self.get_db_template(id)
        self.logger.debug(
            f"Updating database template name: '{db_template.name}' -> '{name}'"
        )
        db_template.name = name

    def update_db_template_optional_args(
        self, id: int, optional_args: List[str]
    ) -> None:
        """Update database template optional arguments.

        :param id: id of DBTemplate
        :type id: int
        :param optional_args: new list of optional_args
        :type name: List[str]
        """
        try:
            db_template = (
                self.bm.session.query(DBTemplate).filter(DBTemplate.id == id).one()
            )
        except NoResultFound:
            raise TemplateNotFound(idnum=id)
        db_template.optional_args = optional_args

    def add_template_dependency_preliminary(
        self,
        template_id: int,
        dependency_library: str,
        dependency_template: str,
        args: Dict[str, str],
    ):
        """Creates a *preliminary* dependency between two templates. This dependency
        is preliminary because the bindings between the dependent/dependency templates
        are *not validated*. This serves to populate the directed acyclic graph of dependencies between templates
        before the parameter bindings are checked. This ensures that all of the parameters for
        a template *and those in its dependencies* can all be identified and used as part of
        the parameter binding check. The upshot of this process is dependencies between two
        templates can refer to parameters in a template *or its dependencies*. This is necessary
        to support templates that contain many nested components that refer to each other (such
        as the s223:mapsTo property).

        **Important:** Be sure to run "check_all_template_dependencies" to ensure all of your templates.
        will work as you expect!

        :param template_id: dependant template id
        :type template_id: int
        :param dependency_id: dependency template id
        :type dependency_id: int
        :param args: mapping of dependency params to dependant params
        :type args: Dict[str, str]
        :raises ValueError: if all dependee required_params not in args
        :raises ValueError: if dependant and dependency template don't share a
        """
        self.logger.debug(
            f"Creating depencency from templates with id: '{template_id}' and target: '{dependency_library}:{dependency_template}'"
        )
        templ = self.get_db_template(template_id)
        if "name" not in args.keys():
            raise ValueError(
                f"The name parameter is required for the dependency '{templ.name}'."
            )
        # In the past we had a check here to make sure the two templates were in the same library.
        # This has been removed because it wasn't actually necessary, but we may add it back in
        # in the future.
        relationship = DBTemplateDependency(
            template_id=template_id,
            dependency_library_name=dependency_library,
            dependency_template_name=dependency_template,
            args=args,  # type: ignore
        )

        self.bm.session.add(relationship)
        self.bm.session.flush()
        self.logger.debug(f"Created Dependency with id: '{relationship.id}'")

    def check_all_template_dependencies(self):
        """
        Verifies that all template dependencies have valid references to the parameters
        in the dependency or (recursively) its dependencies. Raises an exception if any
        issues are found. Checks all templates in the database.
        """
        # TODO: maybe optimize this to only check recently added templates
        # (i.e. maybe those added since last commit?)
        for db_templ in self.get_all_db_templates():
            for dep in self.get_db_template_dependencies(db_templ.id):
                self.check_template_dependency_relationship(dep)

    @lru_cache(maxsize=128)
    def check_template_dependency_relationship(self, dep: DBTemplateDependency):
        """Verify that the dependency between two templates is well-formed. This involves
        a series of checks:
        - existence of the dependent and dependency templates is performed during the
        :py:method:`database.template_connection.`add_template_dependency_preliminary` method
        - the args keys appear in the dependency, or recursively in a template that is a dependency
        of the named dependency
        - the args values appear in the dependent template
        - there is a 'name' parameter in the dependent template

        :param dep: the dependency object to check
        :type dep: DepsAssociation
        :raises ValueError: if all dependee required_params not in args
        :raises ValueError: if dependant and dependency template don't share a
            library
        """
        template_id = dep.template_id
        args = dep.args
        self.logger.debug(
            f"Creating depencency from templates with ids: '{template_id}' and: '{dep.dependency_template_name}'"
        )
        from buildingmotif.dataclasses import Template

        templ = Template.load(template_id)
        params = templ.parameters_with_dependencies()

        dep_templ = Template.load(dep.dependency_template.id)
        dep_params = dep_templ.parameters_with_dependencies()

        # check parameters are valid
        if not set(args.values()).issubset(params):
            raise ValueError(
                f"In {templ.name} the values of the bindings to {dep_templ.name} must correspond to the "
                "parameters in the dependant template."
                f"Dependency {dep_templ.name} refers to params {set(args.values()).difference(params)} "
                f"that do not appear in template {templ.name} ({params})."
            )
        # do the same for the dependency
        binding_params = set(args.keys())
        if not binding_params.issubset(dep_params):
            diff = binding_params.difference(dep_params)
            raise ValueError(
                f"In {templ.name} the keys of the bindings to {dep_templ.name} must correspond to the "
                "parameters in the template dependency. "
                f"The dependency binding uses params {diff} which don't appear in the dependency template. "
                f"Available dependency parameters are {dep_params}"
            )

        # TODO: do we need this kind of check?
        if len(params) > 0 and args["name"] not in params:
            raise ValueError(
                "The name parameter of the dependency must be bound to a param in this template."
                f"'name' was bound to {args['name']} but available params are {params}"
            )

    def delete_template_dependency(self, template_id: int, dependency_id: int):
        """Delete dependency between two templates.

        :param template_id: dependant template id
        :type template_id: int
        :param dependency_id: dependency template id
        :type dependency_id: int
        """
        self.logger.debug(
            f"Deleting depencency from templates with ids: '{template_id}' and: '{dependency_id}'"  # noqa
        )

        dependency_template = self.get_db_template(dependency_id)

        relationship = (
            self.bm.session.query(DBTemplateDependency)
            .filter(
                DBTemplateDependency.template_id == template_id,
                DBTemplateDependency.dependency_library_name
                == dependency_template.library.name,
                DBTemplateDependency.dependency_template_name
                == dependency_template.name,
            )
            .one()
        )
        self.bm.session.delete(relationship)

    def update_db_template_library(self, id: int, library_id: int) -> None:
        """Update database template library.

        :param id: id of DBTemplate
        :type id: int
        :param library_id: id of the new library
        :type library_id: int
        """
        db_template = self.get_db_template(id)
        self.logger.debug(
            f"Updating database template library: '{db_template.library_id}' -> '{library_id}'"  # noqa
        )
        db_template.library_id = library_id

    def delete_db_template(self, id: int) -> None:
        """Delete database template.

        :param id: id of deleted DBTemplate
        :type id: int
        """
        db_template = self.get_db_template(id)
        self.logger.debug(f"Deleting template: '{db_template.name}'")

        self.bm.session.delete(db_template)

    # graph reference functions

    def get_all_graph_ids(self) -> Set[str]:
        """Return every graph identifier referenced by a table row.

        This is the set of named graphs that must be kept: model graphs, shape
        collection graphs (including model manifests), and template bodies.
        Anything else with a UUID identifier in the graph store is an orphan
        eligible for garbage collection.

        :return: referenced graph identifiers
        :rtype: Set[str]
        """
        model_ids = self.bm.session.query(DBModel.graph_id)
        shape_collection_ids = self.bm.session.query(DBShapeCollection.graph_id)
        template_body_ids = self.bm.session.query(DBTemplate.body_id)
        return {
            graph_id
            for (graph_id,) in model_ids.union(
                shape_collection_ids, template_body_ids
            ).all()
            if graph_id is not None
        }
