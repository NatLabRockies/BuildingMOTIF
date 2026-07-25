import logging
import pathlib
import tempfile
import warnings
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
                logging.info(
                    'Library "%s" already exists and overwrite=False; keeping '
                    "its existing contents. Pass overwrite=True to replace them.",
                    name,
                )
        except LibraryNotFound:
            db_library = bm.table_connection.create_db_library(name)

        # Normalize the name to a string so it matches the database type, as
        # Model.from_graph does. Loading from an ontology passes an
        # rdflib.URIRef here, and URIRef.__eq__ is type-strict -- so without
        # this, `Library.from_ontology(g).name == "urn:ex/ont"` was False while
        # `Library.by_name(...).name == "urn:ex/ont"` was True, and the
        # root-skip guard in _load_imported_ontology_libraries (which compares
        # against OntoEnv's plain-str closure names) could never match.
        return cls(_id=db_library.id, _name=str(db_library.name), _bm=bm)

    @classmethod
    def _clear_library(cls, library: DBLibrary) -> None:
        """Clear contents of a library.

        :param library: library to clear
        :type library: DBLibrary
        """
        bm = get_building_motif()
        for template in library.templates:  # type: ignore
            bm.session.delete(template)

    # TODO: can we deduplicate shape graphs? use hash of graph?

    @staticmethod
    def _resolve_builtin(reference: str, expect_dir: bool = False) -> Optional[str]:
        """Resolve ``reference`` against the libraries packaged inside
        ``buildingmotif.libraries``, or None if it names no builtin.

        Packaged builtins take precedence over the filesystem, which means a
        local ``brick/`` directory is shadowed by the shipped one. That is
        long-standing behavior; this logs at INFO when it actually happens so
        the surprise is at least visible. Pass an absolute path to bypass it.

        :param reference: the path as the caller wrote it
        :type reference: str
        :param expect_dir: whether the local candidate would be a directory
        :type expect_dir: bool
        :return: the resolved filesystem path of the builtin, or None
        :rtype: Optional[str]
        """
        # An absolute path is never a builtin resource name, and asking
        # pkg_resources about one raises a DeprecationWarning that is slated to
        # become an error.
        if pathlib.Path(reference).is_absolute():
            return None
        if not resource_exists("buildingmotif.libraries", reference):
            return None
        resolved = resource_filename("buildingmotif.libraries", reference)
        local = pathlib.Path(reference)
        if local.is_dir() if expect_dir else local.exists():
            logging.info(
                "Loading the *builtin* library %r from %s. A path of the same "
                "name exists relative to the working directory and was NOT "
                "used; pass an absolute path to load that one instead.",
                reference,
                resolved,
            )
        else:
            logging.debug(f"Loading builtin library: {reference}")
        return resolved

    @classmethod
    def by_name(cls, name: str) -> "Library":
        """Get a library already in the database, by name.

        This does *not* load anything from disk -- use :py:meth:`from_ontology`
        or :py:meth:`from_directory` for that.

        :param name: the name of the library inside the database
        :type name: str
        :raises LibraryNotFound: if no library has that name
        :return: the library
        :rtype: Library
        """
        bm = get_building_motif()
        db_library = bm.table_connection.get_db_library_by_name(name)
        return cls(_id=db_library.id, _name=db_library.name, _bm=bm)

    @classmethod
    def from_ontology(
        cls,
        ontology: Union[str, pathlib.Path, rdflib.Graph],
        overwrite: bool = True,
        infer_templates: bool = True,
        run_shacl_inference: bool = True,
        fetch_imports: Optional[bool] = None,
    ) -> "Library":
        """Load a library from an ontology.

        :param ontology: an in-memory ``rdflib.Graph``, or a path/URL to a
            serialized RDF graph. A relative path is resolved against the
            libraries packaged inside ``buildingmotif.libraries`` first (e.g.
            ``"brick/Brick.ttl"``) and the filesystem second; pass an absolute
            path to skip the builtins.
        :type ontology: Union[str, pathlib.Path, rdflib.Graph]
        :param overwrite: if True (default), replace any existing copy of the
            library. If False and a library of this name already exists, the
            **existing library is returned unchanged** -- nothing is loaded.
        :type overwrite: bool
        :param infer_templates: if True (default), infer templates from the
            class/NodeShape candidates in the graph
        :type infer_templates: bool
        :param run_shacl_inference: if True (default), run SHACL inference over
            the ontology using the configured engine before storing it
        :type run_shacl_inference: bool
        :param fetch_imports: if True, use OntoEnv to fetch ``owl:imports``
            dependencies and create Library rows for the resolved imports. If
            None (default), use the active BuildingMOTIF's setting.
        :type fetch_imports: Optional[bool]
        :return: the loaded library
        :rtype: Library
        """
        bm = get_building_motif()
        if fetch_imports is None:
            fetch_imports = bm.ontology_fetch_imports

        if isinstance(ontology, pathlib.Path):
            ontology = str(ontology)

        is_path = isinstance(ontology, str)
        source: Union[str, rdflib.Graph] = ontology
        if is_path:
            source = cls._resolve_builtin(ontology) or ontology  # type: ignore[arg-type]

        ontology_name = bm.ontology_environment.add(
            source,
            fetch_imports=fetch_imports,
            overwrite=overwrite is not False,
        )
        if not overwrite and cls._library_exists(ontology_name):
            return cls.by_name(ontology_name)

        # For a path we take OntoEnv's parsed copy; for a graph the caller
        # already handed us the triples.
        graph = (
            bm.ontology_environment.graph_copy(ontology_name) if is_path else ontology
        )

        closure_names = [ontology_name]
        if fetch_imports:
            _, closure_names = bm.ontology_environment.closure_copy(ontology_name)

        return cls._load_from_ontology(
            graph,  # type: ignore[arg-type]
            overwrite=overwrite,
            infer_templates=False,
            run_shacl_inference=run_shacl_inference,
        )._load_imports_and_return(
            closure_names,
            infer_templates=infer_templates,
            run_shacl_inference=run_shacl_inference,
        )

    @classmethod
    def from_directory(
        cls,
        directory: Union[str, pathlib.Path],
        overwrite: bool = True,
        infer_templates: bool = True,
        run_shacl_inference: bool = True,
    ) -> "Library":
        """Load a library from a directory of ``.yml`` templates and ontology
        files. The library is named after the directory.

        :param directory: path to the directory. A relative path is resolved
            against the libraries packaged inside ``buildingmotif.libraries``
            first (e.g. ``"bacnet"``) and the filesystem second; pass an
            absolute path to skip the builtins.
        :type directory: Union[str, pathlib.Path]
        :param overwrite: if True (default), replace any existing copy of the
            library. If False and a library of this name already exists, the
            **existing library is returned unchanged** -- nothing is loaded.
        :type overwrite: bool
        :param infer_templates: if True (default), infer templates from the
            class/NodeShape candidates in the directory's graphs
        :type infer_templates: bool
        :param run_shacl_inference: if True (default), run SHACL inference over
            the directory's graphs using the configured engine
        :type run_shacl_inference: bool
        :raises FileNotFoundError: if the directory does not exist
        :return: the loaded library
        :rtype: Library
        """
        reference = str(directory)
        builtin = cls._resolve_builtin(reference, expect_dir=True)
        src = pathlib.Path(builtin) if builtin else pathlib.Path(reference)
        if not src.exists():
            raise FileNotFoundError(f"Library directory {src} does not exist")
        return cls._load_from_directory(
            src,
            overwrite=overwrite,
            infer_templates=infer_templates,
            run_shacl_inference=run_shacl_inference,
        )

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
        """Get a library from the database by its id.

        This matches :py:meth:`buildingmotif.dataclasses.template.Template.load`
        and :py:meth:`buildingmotif.dataclasses.shape_collection.ShapeCollection.load`,
        which have always meant "load the row with this id"::

            lib = Library.load(3)

        .. deprecated::
            Every other keyword. ``load()`` used to be four unrelated
            operations behind one signature, selected by which of eight
            optional keywords you happened to pass. They still work and still
            behave identically, but each now warns and will be removed:

            ==================================== ==========================================
            deprecated keyword                   replacement
            ==================================== ==========================================
            ``ontology_graph=g`` / ``=path``     :py:meth:`from_ontology`
            ``directory=path``                   :py:meth:`from_directory`
            ``name=name``                        :py:meth:`by_name`
            ==================================== ==========================================

            ``overwrite``, ``infer_templates``, ``run_shacl_inference``, and
            ``fetch_imports`` are meaningless for an id lookup; they exist here
            only to forward to those replacements.

        :param db_id: the unique id of the library in the database
        :type db_id: Optional[int]
        :param ontology_graph: **deprecated**, use :py:meth:`from_ontology`
        :type ontology_graph: Optional[str|rdflib.Graph], optional
        :param directory: **deprecated**, use :py:meth:`from_directory`
        :type directory: Optional[str], optional
        :param name: **deprecated**, use :py:meth:`by_name`
        :type name: Optional[str], optional
        :param overwrite: forwarded to the deprecated loaders only
        :type overwrite: Optional[bool], optional
        :param infer_templates: forwarded to the deprecated loaders only
        :type infer_templates: Optional[bool], optional
        :param run_shacl_inference: forwarded to the deprecated loaders only
        :type run_shacl_inference: Optional[bool], optional
        :param fetch_imports: forwarded to the deprecated loaders only
        :type fetch_imports: Optional[bool], optional
        :raises LibraryNotFound: if no library has that id
        :raises ValueError: if given no arguments, or an id *and* a deprecated
            source keyword (which of the two was meant is ambiguous)
        :return: the library
        :rtype: Library
        """
        sources = {
            "ontology_graph": ontology_graph,
            "directory": directory,
            "name": name,
        }
        given = {k: v for k, v in sources.items() if v is not None}

        if db_id is not None:
            if given:
                raise ValueError(
                    f"Library.load() got both db_id={db_id!r} and "
                    f"{', '.join(given)}; it loads by id. Use "
                    "Library.from_ontology()/from_directory()/by_name() for the "
                    "others."
                )
            return cls._load_from_db(db_id)

        if not given:
            raise ValueError(
                "Library.load() takes the library's database id. To load from "
                "disk use Library.from_ontology() or Library.from_directory(); "
                "to look one up by name use Library.by_name()."
            )

        # NB: the flags are forwarded *uncoerced*. This signature has always
        # accepted None for them, and None was not equivalent to False:
        # `overwrite=None` reached OntoEnv as `overwrite is not False` -> True
        # while still taking the `if not overwrite` branch. Coercing to bool
        # here would silently change that.
        if ontology_graph is not None:
            warnings.warn(
                "Library.load(ontology_graph=...) is deprecated; use "
                "Library.from_ontology(...).",
                DeprecationWarning,
                stacklevel=2,
            )
            return cls.from_ontology(
                ontology_graph,
                overwrite=overwrite,  # type: ignore[arg-type]
                infer_templates=infer_templates,  # type: ignore[arg-type]
                run_shacl_inference=run_shacl_inference,  # type: ignore[arg-type]
                fetch_imports=fetch_imports,
            )
        if directory is not None:
            warnings.warn(
                "Library.load(directory=...) is deprecated; use "
                "Library.from_directory(...).",
                DeprecationWarning,
                stacklevel=2,
            )
            return cls.from_directory(
                directory,
                overwrite=overwrite,  # type: ignore[arg-type]
                infer_templates=infer_templates,  # type: ignore[arg-type]
                run_shacl_inference=run_shacl_inference,  # type: ignore[arg-type]
            )
        warnings.warn(
            "Library.load(name=...) is deprecated; use Library.by_name(...).",
            DeprecationWarning,
            stacklevel=2,
        )
        return cls.by_name(name)  # type: ignore[arg-type]

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
                lib = cls.by_name(library_name)
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
                # Returning the existing library is what overwrite=False
                # *means*, so this is an outcome, not an anomaly -- INFO, not a
                # warning.
                logging.info(
                    'Library "%s" is already loaded and overwrite=False; '
                    "returning the existing library without reloading.",
                    ontology_name,
                )
                return Library.by_name(ontology_name)

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
                logging.info(
                    'Library "%s" is already loaded and overwrite=False; '
                    "returning the existing library without reloading.",
                    directory.name,
                )
                return Library.by_name(directory.name)

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
    def load_from_libraries_yml(cls, filename: str) -> List["Library"]:
        """
        Loads *multiple* libraries from a properly-formatted 'libraries.yml'
        file. Mostly here to support the commandline tool; for a single library
        prefer :py:meth:`from_ontology` or :py:meth:`from_directory` directly.

        :param filename: the filename of the YAML file to load library names from
        :type filename: str
        :return: the loaded libraries, in the order the file lists them
        :rtype: List[Library]
        """
        with open(filename, "r") as f:
            libraries = yaml.load(f, Loader=yaml.FullLoader)
        validate_libraries_yaml(libraries)  # raises exception
        return [_resolve_library_definition(desc) for desc in libraries]

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
    def id(self) -> int:
        """The library's database id.

        Never None: ``_id`` is a required field and every constructor takes it
        from a flushed row. It was annotated ``Optional[int]``, which forced
        callers passing it straight back to :py:meth:`by_id` to placate the
        type checker.
        """
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
        dbt = self._bm.table_connection.get_db_template_by_name(name, self._id)
        return Template.load(dbt.id)


def _resolve_library_definition(desc: Dict[str, Any]) -> "Library":
    """
    Loads a library from a description in libraries.yml

    :return: the loaded library
    :rtype: Library
    """
    if "directory" in desc:
        spath = pathlib.Path(desc["directory"]).absolute()
        if not (spath.exists() and spath.is_dir()):
            raise FileNotFoundError(f"{spath} is not an existing directory")
        logging.info(f"Load local library {spath} (directory)")
        return Library.from_directory(str(spath))
    elif "ontology" in desc:
        ont = desc["ontology"]
        g = rdflib.Graph().parse(ont, format=rdflib.util.guess_format(ont))
        logging.info(f"Load library {ont} as ontology graph")
        return Library.from_ontology(g)
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
                return _resolve_library_definition({"directory": new_path})
            return _resolve_library_definition({"ontology": new_path})
    raise ValueError(
        "a libraries.yml entry needs one of 'directory', 'ontology', or 'git'; "
        f"got {sorted(desc)}"
    )
