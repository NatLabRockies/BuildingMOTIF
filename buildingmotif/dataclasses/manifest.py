"""The set of libraries a model is validated and compiled against.

A model's *manifest* answers one question: which graphs of shapes does this
model claim to satisfy? It is stored as an RDF graph containing an
``owl:Ontology`` declaration and one ``owl:imports`` per member, and nothing
else -- the shapes themselves live in the :py:class:`Library` each import
names.

That is a deliberate break with the older manifest, which was an arbitrary
shape graph callers appended to with ``model.get_manifest().graph += ...``.
Shapes reached the manifest by being copied into it, so the manifest could not
say *where* a shape came from, could not be told that a library had been
updated, and could only be inspected by reading triples. Naming libraries
instead of copying their triples makes the manifest a set of names: readable,
diffable, and cheap to add to and subtract from.
"""

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Iterable, Iterator, List, Union
from urllib.parse import quote, unquote

import rfc3987
from rdflib import OWL, RDF, Graph, URIRef

from buildingmotif.database.errors import LibraryNotFound
from buildingmotif.dataclasses.library import Library
from buildingmotif.dataclasses.shape_collection import ShapeCollection

if TYPE_CHECKING:
    from buildingmotif.dataclasses.model import Model

logger = logging.getLogger(__name__)

#: Libraries loaded from a directory are named after that directory (e.g.
#: ``guideline36``), which is not a URI and so cannot be the object of an
#: ``owl:imports``. Those names are carried in the manifest graph under this
#: prefix and mapped back on the way out, so a directory-loaded library can be
#: a manifest member without inventing a fake http:// URL for it.
LIBRARY_URN_PREFIX = "urn:buildingmotif/library/"

#: What :py:meth:`Manifest.add` accepts: a Library, its name, or an iterable of
#: either. A ``ShapeCollection`` is deliberately *not* accepted -- see the
#: module docstring.
LibraryRef = Union[Library, str, URIRef]


class ManifestLibraryNotFound(LibraryNotFound):
    """A manifest names a library that could not be found or loaded.

    Subclasses :py:class:`LibraryNotFound` so existing ``except
    LibraryNotFound`` still catches it; it exists to carry a message that says
    what to do about it, since a bare ``LibraryNotFound`` prints only the name.
    """

    def __init__(self, name: str, reason: str = ""):
        super().__init__(name=name)
        self.reason = reason

    def __str__(self) -> str:
        detail = f" ({self.reason})" if self.reason else ""
        return (
            f"No library named {self.lib_name!r} is loaded, and it could not be "
            f"resolved through the ontology environment{detail}. Load it first "
            "-- Library.from_ontology(...) or Library.from_directory(...) -- or "
            "add it with resolve=False to record the import without resolving it."
        )


def _is_uri(name: str) -> bool:
    try:
        return bool(rfc3987.parse(name)["scheme"])
    except ValueError:
        return False


def library_iri(name: str) -> URIRef:
    """The IRI a library of this name takes inside a manifest graph.

    A URI-named library (the usual case: the name is its ontology's URI) is its
    own IRI. Any other name -- a directory-loaded library, named after the
    directory -- is carried under :py:data:`LIBRARY_URN_PREFIX`.
    """
    if _is_uri(name):
        return URIRef(name)
    return URIRef(LIBRARY_URN_PREFIX + quote(name, safe=""))


def library_name(iri: URIRef) -> str:
    """The library name an IRI in a manifest graph refers to.

    Inverse of :py:func:`library_iri`.
    """
    text = str(iri)
    if text.startswith(LIBRARY_URN_PREFIX):
        return unquote(text[len(LIBRARY_URN_PREFIX) :])
    return text


#: Handing a ShapeCollection to a manifest was the *old* way to say "also check
#: these shapes", so it gets its own message rather than the generic type error.
_SHAPE_COLLECTION_MESSAGE = (
    "A manifest holds libraries, not ShapeCollections. Create a library for "
    "these shapes -- Library.from_ontology(graph) names it after the graph's "
    "owl:Ontology declaration -- and add that."
)


def _flatten(items: Iterable) -> List[LibraryRef]:
    """Accept ``add(a, b)``, ``add([a, b])``, and ``add(a, [b, c])`` alike."""
    flat: List[LibraryRef] = []
    for item in items:
        if isinstance(item, ShapeCollection):
            raise TypeError(_SHAPE_COLLECTION_MESSAGE)
        if isinstance(item, (Library, str, URIRef)):
            flat.append(item)
        elif isinstance(item, Iterable):
            flat.extend(_flatten(item))
        else:
            raise TypeError(
                f"A manifest holds libraries, not {type(item).__name__}. Pass a "
                "Library, a library name, or an iterable of either."
            )
    return flat


def _name_of(item: LibraryRef) -> str:
    if isinstance(item, Library):
        return item.name
    if isinstance(item, ShapeCollection):
        raise TypeError(_SHAPE_COLLECTION_MESSAGE)
    return str(item)


def default_manifest_uri(model_name: str) -> URIRef:
    """The URI a model's manifest declares itself under, absent one already."""
    text = str(model_name)
    if text.endswith(("/", "#", ":")):
        return URIRef(text + "manifest")
    return URIRef(text + "/manifest")


@dataclass
class Manifest:
    """The set of libraries a model is validated and compiled against.

    Behaves like a set of library names. It is unordered by nature -- adding
    the same library twice is a no-op, and the members come back sorted so two
    equal manifests read the same way::

        model.manifest.add(brick)                   # a Library
        model.manifest.add("urn:my/shapes")         # or its name
        "urn:my/shapes" in model.manifest           # True
        len(model.manifest)                         # 2
        model.manifest.remove(brick)
        model.manifest.libraries                    # [Library(...)]

    :py:meth:`Model.validate` and :py:meth:`Model.compile` use
    :py:meth:`shape_collections` when they are given no explicit list, which is
    what makes the manifest "the shapes this model is checked against" rather
    than merely a record of intent.
    """

    _model: "Model"
    _shape_collection: ShapeCollection = field(compare=False)

    @classmethod
    def for_model(cls, model: "Model") -> "Manifest":
        """The manifest of ``model``. Prefer :py:attr:`Model.manifest`."""
        return cls(model, ShapeCollection.load(model._manifest_id))

    @property
    def model(self) -> "Model":
        return self._model

    @property
    def shape_collection(self) -> ShapeCollection:
        """The ShapeCollection this manifest is stored in.

        A storage detail, exposed because the manifest graph has to live
        somewhere and callers doing surgery may need it. Writing shapes into it
        does not make them part of the manifest in any way the rest of the API
        understands: only ``owl:imports`` are read back out.
        """
        return self._shape_collection

    @property
    def uri(self) -> URIRef:
        """The URI this manifest graph declares itself under."""
        declared = self._shape_collection.graph_name
        if declared is not None:
            return declared
        return default_manifest_uri(self._model.name)

    @property
    def graph(self) -> Graph:
        """A **copy** of the stored manifest graph.

        Serialize it, diff it, hand it to another tool. Mutating it does
        nothing to the manifest -- that is the point, since the older API's
        ``manifest.graph += shapes`` is exactly what this class replaces. Use
        :py:meth:`add` and :py:meth:`remove`.
        """
        copy = Graph()
        copy += self._shape_collection.graph
        return copy

    @property
    def imports(self) -> List[URIRef]:
        """The ``owl:imports`` in the manifest graph, sorted.

        These are IRIs; :py:attr:`library_names` is the same list as library
        names, which is what :py:meth:`add` and :py:meth:`remove` speak.
        """
        return sorted(
            {
                obj
                for obj in self._shape_collection.graph.objects(None, OWL.imports)
                if isinstance(obj, URIRef)
            }
        )

    @property
    def library_names(self) -> List[str]:
        """The names of the libraries in this manifest, sorted."""
        return sorted(library_name(iri) for iri in self.imports)

    @property
    def libraries(self) -> List[Library]:
        """The libraries in this manifest, loading any that are not yet loaded.

        :raises ManifestLibraryNotFound: if a member cannot be resolved. Use
            :py:meth:`resolve` with ``error_on_missing=False`` to skip those
            instead.
        """
        return self.resolve()

    def __contains__(self, item: object) -> bool:
        try:
            name = _name_of(item)  # type: ignore[arg-type]
        except TypeError:
            return False
        return name in self.library_names

    def __iter__(self) -> Iterator[str]:
        """Iterate the member library *names*, so ``for x in m`` matches ``in``."""
        return iter(self.library_names)

    def __len__(self) -> int:
        return len(self.imports)

    def __repr__(self) -> str:
        return f"Manifest({self.uri}, {self.library_names})"

    def add(
        self, *libraries: Union[LibraryRef, Iterable[LibraryRef]], resolve: bool = True
    ) -> None:
        """Add libraries to this manifest. Adding a member twice is a no-op.

        :param libraries: :py:class:`Library` objects, library names, or
            iterables of either
        :param resolve: if True (default), a name that is not already a loaded
            library is resolved through the ontology environment -- taken from
            the ontology cache if it is known there, fetched if it is a URL and
            the active BuildingMOTIF permits fetching -- and loaded as a
            library. A name that resolves nowhere raises rather than being
            recorded as an import that will fail later. Pass False to record
            the import without resolving it.
        :type resolve: bool
        :raises ManifestLibraryNotFound: if ``resolve`` and a name resolves
            nowhere
        :raises TypeError: if handed something that is not a library or a name
        """
        graph = self._shape_collection.graph
        self._ensure_declared()
        for item in _flatten(libraries):
            name = _name_of(item)
            if resolve and not isinstance(item, Library):
                self._resolve_one(name)
            graph.add((self.uri, OWL.imports, library_iri(name)))

    def remove(self, *libraries: Union[LibraryRef, Iterable[LibraryRef]]) -> None:
        """Remove libraries from this manifest.

        :raises KeyError: if a library is not in the manifest, as
            :py:meth:`set.remove` does. Use :py:meth:`discard` to ignore that.
        """
        present = set(self.library_names)
        names = [_name_of(item) for item in _flatten(libraries)]
        missing = [name for name in names if name not in present]
        if missing:
            raise KeyError(
                f"{', '.join(repr(name) for name in missing)} not in the manifest "
                f"of {self._model.name}"
            )
        self._remove_names(names)

    def discard(self, *libraries: Union[LibraryRef, Iterable[LibraryRef]]) -> None:
        """Remove libraries from this manifest, ignoring any that are absent."""
        self._remove_names([_name_of(item) for item in _flatten(libraries)])

    def clear(self) -> None:
        """Remove every library from this manifest, keeping its declaration."""
        graph = self._shape_collection.graph
        for triple in list(graph.triples((None, OWL.imports, None))):
            graph.remove(triple)

    def replace(
        self, libraries: Iterable[LibraryRef] = (), resolve: bool = True
    ) -> None:
        """Make ``libraries`` the entire contents of this manifest.

        Equivalent to :py:meth:`clear` followed by :py:meth:`add`, and the
        replacement for the old ``Model.replace_manifest``.
        """
        self.clear()
        self.add(libraries, resolve=resolve)

    def resolve(self, error_on_missing: bool = True) -> List[Library]:
        """The member libraries, loading any that are not yet loaded.

        :param error_on_missing: if True (default), a member that resolves
            nowhere raises. If False it is logged and skipped, which is what
            ``Model.validate(error_on_missing_imports=False)`` asks for.
        :type error_on_missing: bool
        :raises ManifestLibraryNotFound: per ``error_on_missing``
        :return: the libraries, in :py:attr:`library_names` order
        :rtype: List[Library]
        """
        libraries = []
        for name in self.library_names:
            try:
                libraries.append(self._resolve_one(name))
            except ManifestLibraryNotFound:
                if error_on_missing:
                    raise
                logger.warning(
                    "Manifest of %s names library %r, which is not loaded and "
                    "could not be resolved; skipping it.",
                    self._model.name,
                    name,
                )
        return libraries

    def shape_collections(self, error_on_missing: bool = True) -> List[ShapeCollection]:
        """The shape collections this model is validated and compiled against.

        This is what :py:meth:`Model.validate` and :py:meth:`Model.compile` use
        when given no explicit list. The manifest's *own* graph is not among
        them: it holds imports, not shapes.
        """
        return [
            library.get_shape_collection()
            for library in self.resolve(error_on_missing=error_on_missing)
        ]

    def _ensure_declared(self) -> None:
        """Give the manifest graph an ``owl:Ontology`` declaration if it has none."""
        graph = self._shape_collection.graph
        if self._shape_collection.graph_name is None:
            graph.add((self.uri, RDF.type, OWL.Ontology))

    def _remove_names(self, names: Iterable[str]) -> None:
        graph = self._shape_collection.graph
        for name in names:
            graph.remove((None, OWL.imports, library_iri(name)))

    def _resolve_one(self, name: str) -> Library:
        """Find the library called ``name``, loading it if BuildingMOTIF can.

        Three steps, cheapest first: a library already in the database; an
        ontology the ontology environment already has (loading it as a library
        costs no network); and, for an http(s) name, a fetch -- which is what
        makes ``manifest.add("https://brickschema.org/schema/1.4/Brick")`` work
        on a machine that has never seen Brick.
        """
        try:
            return Library.by_name(name)
        except LibraryNotFound:
            pass

        bm = self._model._bm
        env = bm.ontology_environment
        if env.knows(name):
            # Already in the ontology cache: no network, and OntoEnv has the
            # parsed graph, so hand that to Library rather than re-fetching.
            return Library.from_ontology(env.graph_copy(name), overwrite=False)

        if name.startswith(("http://", "https://")) and bm.ontology_fetch_imports:
            try:
                return Library.from_ontology(name, overwrite=False)
            except Exception as exc:
                raise ManifestLibraryNotFound(name, str(exc)) from exc

        raise ManifestLibraryNotFound(name)
