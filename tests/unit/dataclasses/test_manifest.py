"""A model's manifest is a set of libraries, stored as owl:imports."""

import pytest
from rdflib import OWL, RDF, Graph, Namespace, URIRef

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Manifest, Model
from buildingmotif.dataclasses.manifest import (
    LIBRARY_URN_PREFIX,
    ManifestLibraryNotFound,
    library_iri,
    library_name,
)
from buildingmotif.namespaces import BRICK, SH
from buildingmotif.ontology_environment import OntologyImportsNotFound

BLDG = Namespace("urn:bldg/")
SHAPE1 = "tests/unit/fixtures/shapes/shape1.ttl"
SHAPE2 = "tests/unit/fixtures/shapes/shape2.ttl"


def _library(uri: str) -> Library:
    """A library with one trivial shape, named ``uri``."""
    graph = Graph()
    graph.parse(
        data=f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        <{uri}> a owl:Ontology .
        <{uri}shape> a sh:NodeShape ; sh:targetClass <urn:ex/Thing> .
        """
    )
    return Library.from_ontology(graph, infer_templates=False)


# -- membership ----------------------------------------------------------


def test_new_manifest_is_empty(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    assert len(model.manifest) == 0
    assert model.manifest.library_names == []
    assert list(model.manifest) == []


def test_add_a_library(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    lib = _library("urn:a/")
    model.manifest.add(lib)
    assert model.manifest.library_names == ["urn:a/"]
    assert lib in model.manifest
    assert "urn:a/" in model.manifest


def test_add_by_name(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    _library("urn:a/")
    model.manifest.add("urn:a/")
    assert model.manifest.library_names == ["urn:a/"]


def test_add_several_at_once_and_iterables(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    a, b, c = (_library(f"urn:{x}/") for x in "abc")
    model.manifest.add(a, [b, "urn:c/"])
    assert model.manifest.library_names == ["urn:a/", "urn:b/", "urn:c/"]


def test_adding_twice_is_a_no_op(bm: BuildingMOTIF):
    """It is a set: a model cannot claim to satisfy a library twice."""
    model = Model.create(uri=BLDG)
    lib = _library("urn:a/")
    model.manifest.add(lib)
    model.manifest.add(lib)
    model.manifest.add("urn:a/")
    assert len(model.manifest) == 1


def test_remove(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    a, b = _library("urn:a/"), _library("urn:b/")
    model.manifest.add(a, b)
    model.manifest.remove(a)
    assert model.manifest.library_names == ["urn:b/"]


def test_remove_absent_raises_keyerror(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    with pytest.raises(KeyError, match="urn:a/"):
        model.manifest.remove("urn:a/")


def test_discard_ignores_absent(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.discard("urn:a/")
    assert len(model.manifest) == 0


def test_clear_keeps_the_declaration(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.add(_library("urn:a/"))
    model.manifest.clear()
    assert len(model.manifest) == 0
    assert (model.manifest.uri, RDF.type, OWL.Ontology) in model.manifest.graph


def test_replace(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    a, b = _library("urn:a/"), _library("urn:b/")
    model.manifest.add(a)
    model.manifest.replace([b])
    assert model.manifest.library_names == ["urn:b/"]


def test_manifest_survives_reloading_the_model(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.add(_library("urn:a/"))
    assert Model.load(model.id).manifest.library_names == ["urn:a/"]


# -- the stored graph ----------------------------------------------------


def test_the_graph_is_imports_only(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.add(_library("urn:a/"))
    graph = model.manifest.graph
    assert (model.manifest.uri, RDF.type, OWL.Ontology) in graph
    assert (model.manifest.uri, OWL.imports, URIRef("urn:a/")) in graph
    assert len(graph) == 2, "a manifest holds its declaration and its imports"


def test_the_graph_is_a_copy(bm: BuildingMOTIF):
    """The old API let callers append shapes here; now that edit goes nowhere."""
    model = Model.create(uri=BLDG)
    copy = model.manifest.graph
    copy.add((URIRef("urn:ex/s"), RDF.type, URIRef("urn:ex/Shape")))
    assert len(model.manifest.graph) == 0


def test_manifest_uri_is_derived_from_the_model(bm: BuildingMOTIF):
    assert Model.create(uri="urn:bldg/").manifest.uri == URIRef("urn:bldg/manifest")
    assert Model.create(uri="urn:other").manifest.uri == URIRef("urn:other/manifest")


def test_directory_libraries_are_carried_under_a_urn(bm: BuildingMOTIF):
    """A directory library is named after its directory, which is not a URI."""
    lib = Library.from_directory("tests/unit/fixtures/matching", infer_templates=False)
    assert lib.name == "matching"
    model = Model.create(uri=BLDG)
    model.manifest.add(lib)
    assert model.manifest.imports == [URIRef(LIBRARY_URN_PREFIX + "matching")]
    assert model.manifest.library_names == ["matching"]
    assert lib in model.manifest
    assert [x.name for x in model.manifest.libraries] == ["matching"]


def test_library_iri_round_trip():
    for name in ("urn:a/", "https://ex.org/a", "guideline36", "a name/with slash"):
        assert library_name(library_iri(name)) == name


# -- resolution ----------------------------------------------------------


def test_unknown_name_raises_on_add(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    with pytest.raises(ManifestLibraryNotFound, match="urn:nope/"):
        model.manifest.add("urn:nope/")
    assert len(model.manifest) == 0


def test_unresolved_can_be_recorded_deliberately(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.add("urn:nope/", resolve=False)
    assert model.manifest.library_names == ["urn:nope/"]
    with pytest.raises(ManifestLibraryNotFound):
        model.manifest.libraries
    assert model.manifest.resolve(error_on_missing=False) == []
    assert model.manifest.shape_collections(error_on_missing=False) == []


def test_a_name_ontoenv_knows_is_loaded_automatically(bm: BuildingMOTIF):
    """The ontology cache is consulted before giving up on a name.

    Adding an ontology to the environment does not create a Library, so this is
    a name that resolves nowhere in the database but is one lookup away.
    """
    name = bm.ontology_environment.add(SHAPE1, fetch_imports=False)
    model = Model.create(uri=BLDG)
    model.manifest.add(name, import_depth=0)
    assert Library.by_name(name).name == name
    assert [len(sc.graph) > 0 for sc in model.manifest.shape_collections()] == [True]


def test_shape_collections_come_from_the_libraries(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    lib = _library("urn:a/")
    model.manifest.add(lib)
    assert model.manifest.shape_collections() == [lib.get_shape_collection()]


# -- expansion of imports ------------------------------------------------


def test_add_pulls_in_what_a_library_imports(bm: BuildingMOTIF):
    """shape1 imports Brick, so adding shape1 adds Brick -- explicitly, as a
    member of its own, rather than resolving it again on every validation."""
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    model = Model.create(uri=BLDG)
    model.manifest.add(Library.from_ontology(SHAPE1, infer_templates=False))
    assert model.manifest.library_names == [
        "https://brickschema.org/schema/1.4/Brick",
        "urn:shape1/",
    ]


def test_import_depth_controls_expansion(bm: BuildingMOTIF):
    """OntoEnv's own meaning: 0 is the named library alone, -1 the closure."""
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology(SHAPE1, infer_templates=False)

    shallow = Model.create(uri="urn:shallow/")
    shallow.manifest.add(lib, import_depth=0)
    assert shallow.manifest.library_names == ["urn:shape1/"]

    deep = Model.create(uri="urn:deep/")
    deep.manifest.add(lib, import_depth=1)
    assert "https://brickschema.org/schema/1.4/Brick" in deep.manifest


def test_removal_does_not_cascade(bm: BuildingMOTIF):
    """A manifest is a flat set, exactly as it reads: removing the library
    that pulled Brick in leaves Brick a member until it is removed too."""
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology(SHAPE1, infer_templates=False)
    model = Model.create(uri=BLDG)
    model.manifest.add(lib)
    model.manifest.remove(lib)
    assert model.manifest.library_names == ["https://brickschema.org/schema/1.4/Brick"]


def test_expansion_follows_a_directory_library_too(bm: BuildingMOTIF):
    """A directory library is not an ontology OntoEnv knows, so its imports
    are read from its own shape collection instead."""
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    g36 = Library.from_directory("libraries/ashrae/guideline36", infer_templates=False)
    assert not bm.ontology_environment.knows(g36.name)
    model = Model.create(uri=BLDG)
    model.manifest.add(g36)
    assert model.manifest.library_names == [
        "guideline36",
        "https://brickschema.org/schema/1.4/Brick",
    ]


def test_shapes_graph_is_the_union_of_the_members(bm: BuildingMOTIF):
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    model = Model.create(uri=BLDG)
    model.manifest.add(Library.from_ontology(SHAPE1, infer_templates=False))

    graph = model.manifest.shapes_graph()
    for collection in model.manifest.shape_collections():
        assert len(graph) >= len(collection.graph)
        for triple in collection.graph:
            assert triple in graph
    assert (BRICK.VAV, RDF.type, OWL.Class) in graph, "Brick came along"
    assert (URIRef("urn:shape1/vav_shape"), RDF.type, SH.NodeShape) in graph


def test_shapes_graph_reports_imports_no_member_covers(bm: BuildingMOTIF):
    """The safety net for a library added with import_depth=0, or reloaded
    with new imports after it was added."""
    model = Model.create(uri=BLDG)
    lib = Library.from_ontology(SHAPE1, infer_templates=False)
    model.manifest.add(lib, import_depth=0)  # Brick deliberately left out
    with pytest.raises(OntologyImportsNotFound, match="Brick"):
        model.manifest.shapes_graph()
    assert len(model.manifest.shapes_graph(error_on_missing=False)) > 0


def test_shapes_graph_tracks_membership_changes(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.add(_library("urn:a/"))
    before = len(model.manifest.shapes_graph())
    model.manifest.clear()
    assert len(model.manifest.shapes_graph()) == 0 < before


def test_manifest_and_explicit_list_validation_agree(bm: BuildingMOTIF, shacl_engine):
    """Taking the shapes graph from the members must report exactly what
    resolving each collection's imports separately reports."""
    bm.shacl_engine = shacl_engine
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology(SHAPE1)
    model = Model.create(uri="https://example.com")
    model.graph.add((URIRef("https://example.com/vav1"), RDF.type, BRICK.VAV))
    model.manifest.add(lib)

    # no arguments -> the members' union; an explicit list -> per collection
    via_manifest = model.validate()
    via_collections = model.validate(model.manifest.shape_collections())

    # NB: not `is False` -- the topquadrant backend reports 0/1, not a bool
    assert not via_manifest.valid and not via_collections.valid
    assert set(via_manifest.diffset) == set(via_collections.diffset)
    assert {
        (f, str(d.reason())) for f, s in via_manifest.diffset.items() for d in s
    } == {(f, str(d.reason())) for f, s in via_collections.diffset.items() for d in s}


# -- what a manifest is not ----------------------------------------------


def test_shape_collections_are_rejected(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    lib = _library("urn:a/")
    with pytest.raises(TypeError, match="not ShapeCollections"):
        model.manifest.add(lib.get_shape_collection())
    with pytest.raises(TypeError, match="not ShapeCollections"):
        model.add_to_manifest(lib.get_shape_collection())


def test_other_types_are_rejected(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    with pytest.raises(TypeError, match="not int"):
        model.manifest.add(3)


# -- Model's side of it --------------------------------------------------


def test_model_conveniences(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    lib = _library("urn:a/")
    model.add_to_manifest(lib)
    assert model.manifest.library_names == ["urn:a/"]
    model.remove_from_manifest(lib)
    assert model.manifest.library_names == []
    # unlike Manifest.remove, this one forgives an absent library
    model.remove_from_manifest(lib)


def test_get_manifest_is_deprecated_and_returns_a_manifest(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    with pytest.warns(DeprecationWarning, match="Model.manifest"):
        manifest = model.get_manifest()
    assert isinstance(manifest, Manifest)


def test_validate_uses_the_manifest(bm: BuildingMOTIF, shacl_engine):
    """The point of the manifest: validate() with no arguments uses it."""
    bm.shacl_engine = shacl_engine
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology(SHAPE1)

    model = Model.create(uri="https://example.com")
    model.graph.add((URIRef("https://example.com/vav1"), RDF.type, BRICK.VAV))
    assert model.validate().valid, "an empty manifest asks nothing of the model"

    model.manifest.add(lib)
    assert not model.validate().valid, "the manifest's shapes are now in force"

    model.manifest.clear()
    assert model.validate().valid, "and emptying the manifest lifts them again"


def test_replace_expands_like_add(bm: BuildingMOTIF):
    """replace() is clear() + add(), expansion included -- documented in
    docs/explanations/manifests.md, so it needs to stay true."""
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology(SHAPE1, infer_templates=False)
    model = Model.create(uri=BLDG)
    model.manifest.replace([lib])
    assert model.manifest.library_names == [
        "https://brickschema.org/schema/1.4/Brick",
        "urn:shape1/",
    ]
    model.manifest.replace([lib], import_depth=0)
    assert model.manifest.library_names == ["urn:shape1/"]
