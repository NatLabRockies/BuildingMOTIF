import logging
import pathlib
import tempfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

import pygit2
import rdflib
import yaml
from pkg_resources import resource_exists, resource_filename
from rdflib.exceptions import ParserError
from rdflib.plugins.parsers.notation3 import BadSyntax
from rdflib.util import guess_format

from buildingmotif import get_building_motif
from buildingmotif.database.errors import LibraryNotFound
from buildingmotif.database.tables import DBLibrary, DBTemplate
from buildingmotif.dataclasses.shape_collection import ShapeCollection
from buildingmotif.dataclasses.template import Template
from buildingmotif.namespaces import bind_prefixes
from buildingmotif.schemas import validate_libraries_yaml
from buildingmotif.template_compilation import compile_template_spec
from buildingmotif.utils import get_ontology_files, shacl_inference

if TYPE_CHECKING:
    from buildingmotif import BuildingMOTIF


@dataclass
class Library:
    """This class mirrors :py:class:`database.tables.DBLibrary`."""

    _id: int
    _name: str
    _bm: "BuildingMOTIF" = field(compare=False)

    @classmethod
    def create(cls, name: str, overwrite: Optional[bool] = True) -> "Library":
        """Create new Library.

        :param name: library name
        :type name: str
        :param overwrite: if True, overwrite the existing copy of the library.
        :type overwrite: Optional[bool]
        :return: new library
        :rtype: Library
        """
        bm = get_building_motif()
        try:
            db_library = bm.table_connection.get_db_library_by_name(name)
            if overwrite:
                cls._clear_library(db_library)
            else:
                logging.warning(
                    f'Library {name} already exists in database. To ovewrite load library with "overwrite=True"'  # noqa
                )
        except LibraryNotFound:
            db_library = bm.table_connection.create_db_library(name)

        return cls(_id=db_library.id, _name=db_library.name, _bm=bm)

    @classmethod
    def _clear_library(cls, library: DBLibrary) -> None:
        """Clear contents of a library.

        :param library: library to clear
        :type library: DBLibrary
        """
        bm = get_building_motif()
        for template in library.templates:  # type: ignore
            bm.session.delete(template)

    # TODO: load library from URI? Does the URI identify the library uniquely?
    # TODO: can we deduplicate shape graphs? use hash of graph?
    @classmethod
    def load(
        cls,
        db_id: Optional[int] = None,
        ontology_graph: Optional[Union[str, rdflib.Graph]] = None,
        directory: Optional[str] = None,
        name: Optional[str] = None,
        overwrite: Optional[bool] = True,
        infer_templates: Optional[bool] = True,
        run_shacl_inference: Optional[bool] = True,
        fetch_imports: Optional[bool] = None,
    ) -> "Library":
        """Loads a library from the database or an external source.
        When specifying a path to load a library or ontology_graph from,
        paths within the buildingmotif.libraries module will be prioritized
        if they resolve.

        :param db_id: the unique id of the library in the database,
            defaults to None
        :type db_id: Optional[int], optional
        :param ontology_graph: a path to a serialized RDF graph.
            Supports remote ontology URLs, defaults to None
        :type ontology_graph: Optional[str|rdflib.Graph], optional
        :param directory: a path to a directory containing a library,
            or an rdflib graph, defaults to None
        :type directory: Optional[str], optional
        :param name: the name of the library inside the database,
            defaults to None
        :type name: Optional[str], optional
        :param overwrite: if true, replace any existing copy of the
            library, defaults to True
        :type overwrite: Optional[true], optional
        :param infer_templates: if true, infer shapes from the ontology graph,
            defaults to True
        :type infer_templates: Optional[bool], optional
        :param run_shacl_inference: if true, run SHACL inference on the ontology graph,
            using the BuildingMOTIF SHACL engine, defaults to True
        :type run_shacl_inference: Optional[bool], optional
        :param fetch_imports: if true, use ontoenv to fetch owl:imports dependencies
            and create BuildingMOTIF Library rows for the resolved imported ontologies.
            If None, uses the active BuildingMOTIF default.
        :type fetch_imports: Optional[bool], optional
        :return: the loaded library
        :rtype: Library
        :raises Exception: if the library cannot be loaded
        """
        bm = get_building_motif()
        if fetch_imports is None:
            fetch_imports = bm.ontology_fetch_imports

        if db_id is not None:
            return cls._load_from_db(db_id)
        elif ontology_graph is not None:
            if isinstance(ontology_graph, str):
                ontology_graph_path = ontology_graph
                if not pathlib.Path(
                    ontology_graph_path
                ).is_absolute() and resource_exists(
                    "buildingmotif.libraries", ontology_graph_path
                ):
                    logging.debug(f"Loading builtin library: {ontology_graph_path}")
                    ontology_graph_path = resource_filename(
                        "buildingmotif.libraries", ontology_graph_path
                    )
                ontology_name = bm.ontology_environment.add(
                    ontology_graph_path,
                    fetch_imports=fetch_imports,
                    overwrite=overwrite is not False,
                )
                if not overwrite and cls._library_exists(ontology_name):
                    return cls.load(name=ontology_name)
                ontology_graph = bm.ontology_environment.graph_copy(ontology_name)
                closure_names = [ontology_name]
                if fetch_imports:
                    _, closure_names = bm.ontology_environment.closure_copy(
                        ontology_name
                    )
                lib = cls._load_from_ontology(
                    ontology_graph,
                    overwrite=overwrite,
                    infer_templates=False,
                    run_shacl_inference=run_shacl_inference,
                )
                cls._load_imported_ontology_libraries(
                    root_name=lib.name,
                    closure_names=closure_names,
                    infer_templates=False,
                    run_shacl_inference=run_shacl_inference,
                )
                if infer_templates:
                    cls._infer_templates_for_libraries(closure_names)
                return lib
            ontology_name = bm.ontology_environment.add(
                ontology_graph,
                fetch_imports=fetch_imports,
                overwrite=overwrite is not False,
            )
            if not overwrite and cls._library_exists(ontology_name):
                return cls.load(name=ontology_name)
            closure_names = [ontology_name]
            if fetch_imports:
                _, closure_names = bm.ontology_environment.closure_copy(ontology_name)
            return cls._load_from_ontology(
                ontology_graph,
                overwrite=overwrite,
                infer_templates=False,
                run_shacl_inference=run_shacl_inference,
            )._load_imports_and_return(
                closure_names,
                infer_templates=infer_templates,
                run_shacl_inference=run_shacl_inference,
            )
        elif directory is not None:
            if resource_exists("buildingmotif.libraries", directory):
                logging.debug(f"Loading builtin library: {directory}")
                src = pathlib.Path(
                    resource_filename("buildingmotif.libraries", directory)
                )
            else:
                src = pathlib.Path(directory)
            if not src.exists():
                raise Exception(f"Directory {src} does not exist")
            return cls._load_from_directory(
                src,
                overwrite=overwrite,
                infer_templates=infer_templates,
                run_shacl_inference=run_shacl_inference,
            )
        elif name is not None:
            bm = get_building_motif()
            db_library = bm.table_connection.get_db_library_by_name(name)
            return cls(_id=db_library.id, _name=db_library.name, _bm=bm)
        else:
            raise Exception("No library information provided")

    def _load_imports_and_return(
        self,
        closure_names: List[str],
        infer_templates: Optional[bool] = True,
        run_shacl_inference: Optional[bool] = True,
    ) -> "Library":
        self._load_imported_ontology_libraries(
            root_name=self.name,
            closure_names=closure_names,
            infer_templates=False,
            run_shacl_inference=run_shacl_inference,
        )
        if infer_templates:
            self._infer_templates_for_libraries(closure_names)
        return self

    @classmethod
    def _load_imported_ontology_libraries(
        cls,
        root_name: str,
        closure_names: List[str],
        infer_templates: Optional[bool] = True,
        run_shacl_inference: Optional[bool] = True,
    ) -> None:
        bm = get_building_motif()
        for ontology_name in closure_names:
            if ontology_name == root_name:
                continue
            if cls._library_exists(ontology_name):
                continue
            graph = bm.ontology_environment.graph_copy(ontology_name)
            cls._load_from_ontology(
                graph,
                overwrite=False,
                infer_templates=infer_templates,
                run_shacl_inference=False,
            )

    @classmethod
    def _infer_templates_for_libraries(cls, library_names: List[str]) -> None:
        inferred_library_ids = set()
        for library_name in reversed(library_names):
            try:
                lib = cls.load(name=library_name)
            except LibraryNotFound:
                continue
            if lib.id in inferred_library_ids:
                continue
            inferred_library_ids.add(lib.id)
            if lib.get_templates():
                continue
            lib.get_shape_collection().infer_templates(lib)

    @classmethod
    def _load_from_db(cls, id: int) -> "Library":
        """Load library from database by id.

        :param id: id of library
        :type id: int
        :return: library
        :rtype: Library
        """
        bm = get_building_motif()
        db_library = bm.table_connection.get_db_library(id)

        return cls(_id=db_library.id, _name=db_library.name, _bm=bm)

    @classmethod
    def _load_from_ontology(
        cls,
        ontology: rdflib.Graph,
        overwrite: Optional[bool] = True,
        infer_templates: Optional[bool] = True,
        run_shacl_inference: Optional[bool] = True,
    ) -> "Library":
        """
        Load a library from an ontology graph. This proceeds as follows.
        First, get all entities in the graph that are instances of *both* owl:Class
        and sh:NodeShape. (this is "candidates")

        For each candidate, use the utility function to parse the NodeShape and turn
        it into a Template.

        :param ontology: the graph to load into BuildingMOTIF and interpret as a Library
        :type ontology: rdflib.Graph
        :param overwrite: if true, overwrite the existing copy of the Library
        :type overwrite: bool
        :param infer_templates: if true, infer shapes from the ontology graph
        :type infer_templates: bool
        :param run_shacl_inference: if true, run SHACL inference on the ontology graph
        :type run_shacl_inference: bool
        :return: the loaded Library
        :rtype: "Library"
        """
        # get the name of the ontology; this will be the name of the library
        # any=False will raise an error if there is more than one ontology defined  in the graph
        ontology_name = ontology.value(
            predicate=rdflib.RDF.type, object=rdflib.OWL.Ontology, any=False
        ) or rdflib.URIRef("urn:unnamed/")

        if not overwrite:
            if cls._library_exists(ontology_name):
                logging.warning(
                    f'Library "{ontology_name}" already exists in database and "overwrite=False". Returning existing library.'  # noqa
                )
                return Library.load(name=ontology_name)

        # expand the ontology graph before we insert it into the database. This will ensure
        # that the output of compiled models will not contain triples that really belong to
        # the ontology
        if run_shacl_inference:
            ontology = shacl_inference(
                ontology, engine=get_building_motif().shacl_engine
            )

        lib = cls.create(ontology_name, overwrite=overwrite)

        # load the ontology graph as a shape_collection
        shape_col_id = lib.get_shape_collection().id
        assert shape_col_id is not None  # should always pass
        shape_col = ShapeCollection.load(shape_col_id)
        try:
            shape_col.replace_graph(ontology)
        except Exception:
            # Copy-on-write left the previous graph untouched, so rolling back
            # the session reverts the library rows and the newly written graph
            # becomes an orphan reclaimed by garbage collection.
            get_building_motif().session.rollback()
            raise

        if infer_templates:
            # infer shapes from any class/nodeshape candidates in the graph
            shape_col.infer_templates(lib)

        return lib

    def _load_shapes_from_directory(
        self,
        directory: pathlib.Path,
        infer_templates: Optional[bool] = True,
        run_shacl_inference: Optional[bool] = True,
    ):
        """Helper method to read all graphs in the given directory into this
        library.

        :param directory: directory containing graph files
        :type directory: pathlib.Path
        :param infer_templates: if true, infer shapes from the ontology graph
        :type infer_templates: bool
        :param run_shacl_inference: if true, run SHACL inference on the ontology graph
        :type run_shacl_inference: bool
        """
        bm = get_building_motif()
        shape_col_id = self.get_shape_collection().id
        assert shape_col_id is not None  # this should always pass
        shape_col = ShapeCollection.load(shape_col_id)
        graph_id = bm.table_connection.get_db_shape_collection(shape_col_id).graph_id
        for filename in get_ontology_files(directory):
            try:
                # Oxigraph's native loader is much faster than rdflib.parse for
                # large ontologies; it falls back to rdflib internally if needed.
                bm.graph_connection.load_file_into_graph(
                    graph_id, filename, guess_format(str(filename))
                )
            except (ParserError, BadSyntax) as e:
                logging.getLogger(__name__).error(
                    f"Could not parse file {filename}: {e}"
                )
                raise e
            # Register the file with OntoEnv under its own declared name (if
            # any), independent of the bulk load above. Directory-loaded
            # libraries often bundle several files that only make sense
            # merged (e.g. guideline36's per-equipment fragments have no
            # owl:Ontology header of their own), alongside files that
            # declare a real ontology identity and import each other or
            # ontologies outside the directory (e.g. Brick's imports/*.ttl).
            # Without this, those names are never known to OntoEnv, so any
            # owl:imports referencing them - from inside or outside this
            # directory - fails to resolve instead of finding the
            # already-loaded content.
            bm.ontology_environment.add(filename, fetch_imports=False, overwrite=True)
        # Native loading does not propagate file prefixes to the rdflib
        # namespace manager; restore the standard BuildingMOTIF prefixes so
        # serialization stays readable.
        bind_prefixes(shape_col.graph)
        if run_shacl_inference:
            shape_col.graph = shacl_inference(
                shape_col.graph, engine=get_building_motif().shacl_engine
            )
        # infer shapes from any class/nodeshape candidates in the graph
        if infer_templates:
            shape_col.infer_templates(self)

    @classmethod
    def _load_from_directory(
        cls,
        directory: pathlib.Path,
        overwrite: Optional[bool] = True,
        infer_templates: Optional[bool] = True,
        run_shacl_inference: Optional[bool] = True,
    ) -> "Library":
        """
        Load a library from a directory.

        Templates are read from YML files in the directory. The name of the
        library is given by the name of the directory.

        :param directory: directory containing a library
        :type directory: pathlib.Path
        :param overwrite: if true, overwrite the existing copy of the Library
        :type overwrite: bool
        :param infer_templates: if true, infer shapes from the ontology graph
        :type infer_templates: bool
        :param run_shacl_inference: if true, run SHACL inference on the ontology graph
        :type run_shacl_inference: bool
        :raises e: if cannot create template
        :raises e: if cannot resolve dependencies
        :return: library
        :rtype: Library
        """

        if not overwrite:
            if cls._library_exists(directory.name):
                logging.warning(
                    f'Library "{directory.name}" already exists in database and "overwrite=False". Returning existing library.'  # noqa
                )
                return Library.load(name=directory.name)

        lib = cls.create(directory.name, overwrite=overwrite)

        # read all .yml files
        for file in directory.rglob("*.yml"):
            # if .ipynb_checkpoints, skip; these are cached files that Jupyter creates
            if ".ipynb_checkpoints" in file.parts:
                continue
            lib._read_yml_file(file)
        # load shape collections from all ontology files in the directory
        lib._load_shapes_from_directory(
            directory,
            infer_templates=infer_templates,
            run_shacl_inference=run_shacl_inference,
        )

        return lib

    @classmethod
    def load_from_libraries_yml(cls, filename: str):
        """
        Loads *multiple* libraries from a properly-formatted 'libraries.yml'
        file. Does not return a Library! You will need to load the libraries by
        name in order to get the dataclasses.Library object. We recommend loading
        libraries directly, one-by-one, in most cases. This method is here to support
        the commandline tool.

        :param filename: the filename of the YAML file to load library names from
        :type filename: str
        :rtype: None
        """
        libraries = yaml.load(open(filename, "r"), Loader=yaml.FullLoader)
        validate_libraries_yaml(libraries)  # raises exception
        for description in libraries:
            _resolve_library_definition(description)

    @staticmethod
    def _library_exists(library_name: str) -> bool:
        """Checks whether a library with the given name exists in the database."""
        bm = get_building_motif()
        try:
            bm.table_connection.get_db_library_by_name(library_name)
            return True
        except LibraryNotFound:
            return False

    def _read_yml_file(self, file: pathlib.Path):
        """Read a YML file into this library. Utility function for `_load_from_directory`."""
        contents = yaml.load(open(file, "r"), Loader=yaml.FullLoader)
        for templ_name, templ_spec in contents.items():
            # compile the template body using its rules
            templ_spec = compile_template_spec(templ_spec)
            # input name of template
            templ_spec.update({"name": templ_name})
            # remove dependencies so we can resolve them to their IDs later
            templ_spec["optional_args"] = templ_spec.pop("optional", [])
            try:
                self.create_template(**templ_spec)
            except Exception as e:
                logging.error(
                    f"Error creating template {templ_name} from file {file}: {e}"
                )
                raise e

    @property
    def id(self) -> Optional[int]:
        return self._id

    @id.setter
    def id(self, new_id):
        raise AttributeError("Cannot modify db id")

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, new_name: str):
        self._bm.table_connection.update_db_library_name(self._id, new_name)
        self._name = new_name

    @property
    def graph_imports(self) -> List[rdflib.URIRef]:
        """
        Get the list of owl:imports for this library's shape collection
        """
        shape_col = self.get_shape_collection()
        return [
            i
            for i in shape_col.graph.objects(None, rdflib.OWL.imports)
            if isinstance(i, rdflib.URIRef)
        ]

    def create_template(
        self,
        name: str,
        body: Optional[rdflib.Graph] = None,
        optional_args: Optional[List[str]] = None,
        dependencies: Optional[List] = None,
    ) -> Template:
        """Create template in this library.

        :param name: name
        :type name: str
        :param body: template body
        :type body: rdflib.Graph
        :param optional_args: optional parameters for the template
        :type optional_args: list[str]
        :return: created template
        :rtype: Template
        """
        db_template = self._bm.table_connection.create_db_template(name, self._id)
        body = self._bm.graph_connection.create_graph(
            db_template.body_id, body if body else rdflib.Graph()
        )
        # ensure the "param" namespace is bound to the graph
        body.namespace_manager = self._bm.template_ns_mgr
        if optional_args is None:
            optional_args = []
        self._bm.table_connection.update_db_template_optional_args(
            db_template.id, optional_args
        )

        if dependencies is not None:
            for dependency in dependencies:
                dependency_template = dependency["template"]
                dependency_library = None
                if "library" in dependency:
                    dependency_library = dependency["library"]
                else:
                    dependency_library = self.name
                dependency_args = dependency["args"]
                self._bm.table_connection.add_template_dependency_preliminary(
                    db_template.id,
                    dependency_library,
                    dependency_template,
                    dependency_args,
                )

        return Template(
            _id=db_template.id,
            _name=db_template.name,
            body=body,
            optional_args=optional_args,
            _bm=self._bm,
        )

    def get_templates(self) -> List[Template]:
        """Get templates from library.

        :return: list of templates
        :rtype: List[Template]
        """
        db_library = self._bm.table_connection.get_db_library(self._id)
        templates: List[DBTemplate] = db_library.templates
        return [Template.load(t.id) for t in templates]

    def get_shape_collection(self) -> ShapeCollection:
        """Get ShapeCollection from library.

        :return: library's shape collection
        :rtype: ShapeCollection
        """
        # TODO: we should save the libraries shape_collection to a class attr on load/create. That
        # way we wont need an additional db query each time we call this function.
        db_library = self._bm.table_connection.get_db_library(self._id)

        return ShapeCollection.load(db_library.shape_collection.id)

    def get_template_by_name(self, name: str) -> Template:
        """Get template by name from library.

        :param name: template name
        :type name: str
        :raises ValueError: if template not in library
        :return: template
        :rtype: Template
        """
        dbt = self._bm.table_connection.get_db_template_by_name(name)
        if dbt.library_id != self._id:
            raise ValueError(f"Template {name} not in library {self._name}")
        return Template.load(dbt.id)


def _resolve_library_definition(desc: Dict[str, Any]):
    """
    Loads a library from a description in libraries.yml
    """
    if "directory" in desc:
        spath = pathlib.Path(desc["directory"]).absolute()
        if spath.exists() and spath.is_dir():
            logging.info(f"Load local library {spath} (directory)")
            Library.load(directory=str(spath))
        else:
            raise Exception(f"{spath} is not an existing directory")
    elif "ontology" in desc:
        ont = desc["ontology"]
        g = rdflib.Graph().parse(ont, format=rdflib.util.guess_format(ont))
        logging.info(f"Load library {ont} as ontology graph")
        Library.load(ontology_graph=g)
    elif "git" in desc:
        repo = desc["git"]["repo"]
        branch = desc["git"]["branch"]
        path = desc["git"]["path"]
        logging.info(f"Load library {path} from git repository: {repo}@{branch}")
        with tempfile.TemporaryDirectory() as temp_loc:
            pygit2.clone_repository(
                repo, temp_loc, checkout_branch=branch
            )  # , depth=1)
            new_path = pathlib.Path(temp_loc) / pathlib.Path(path)
            if new_path.is_dir():
                _resolve_library_definition({"directory": new_path})
            else:
                _resolve_library_definition({"ontology": new_path})
