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
    model.manifest.add(name)
    assert Library.by_name(name).name == name
    assert [len(sc.graph) > 0 for sc in model.manifest.shape_collections()] == [True]


def test_shape_collections_come_from_the_libraries(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    lib = Library.from_ontology(SHAPE1, infer_templates=False)
    model.manifest.add(lib)
    assert model.manifest.shape_collections() == [lib.get_shape_collection()]


# -- the imports closure -------------------------------------------------


def test_the_manifest_is_an_ontology_ontoenv_can_resolve(bm: BuildingMOTIF):
    """What makes a single closure possible: the manifest is itself an
    ontology whose owl:imports name every member."""
    model = Model.create(uri=BLDG)
    model.manifest.add(Library.from_ontology(SHAPE1, infer_templates=False))
    assert model.manifest.register() == str(model.manifest.uri)
    assert bm.ontology_environment.knows(str(model.manifest.uri))


def test_closure_is_transitive_and_rooted_at_the_manifest(bm: BuildingMOTIF):
    """shape1 imports Brick, which the manifest never names directly."""
    brick = Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    model = Model.create(uri=BLDG)
    model.manifest.add(Library.from_ontology(SHAPE1, infer_templates=False))

    closure = model.manifest.imports_closure()
    assert len(closure) > len(brick.get_shape_collection().graph)
    assert (BRICK.VAV, RDF.type, OWL.Class) in closure, "Brick came along"
    assert (URIRef("urn:shape1/vav_shape"), RDF.type, SH.NodeShape) in closure


def test_closure_covers_members_ontoenv_cannot_resolve(bm: BuildingMOTIF):
    """A directory library is not an ontology OntoEnv knows, so the closure
    cannot reach it and its shape collection is unioned in instead."""
    g36 = Library.from_directory("libraries/ashrae/guideline36", infer_templates=False)
    model = Model.create(uri=BLDG)
    model.manifest.add(g36)
    assert not bm.ontology_environment.knows(g36.name)

    closure = model.manifest.imports_closure(error_on_missing=False)
    shapes = g36.get_shape_collection().graph
    assert len(closure) >= len(shapes)
    a_shape = next(iter(shapes.subjects(RDF.type, SH.NodeShape)))
    assert (a_shape, RDF.type, SH.NodeShape) in closure


def test_closure_reports_what_it_could_not_resolve(bm: BuildingMOTIF):
    model = Model.create(uri=BLDG)
    model.manifest.add("urn:nope/", resolve=False)
    with pytest.raises(OntologyImportsNotFound, match="urn:nope/"):
        model.manifest.imports_closure()
    # lenient: skip it, the same choice validate(error_on_missing_imports=False) makes
    assert len(model.manifest.imports_closure(error_on_missing=False)) >= 0


def test_closure_tracks_membership_changes(bm: BuildingMOTIF):
    """register() overwrites, so a manifest edited after a validate() does not
    validate against its previous membership."""
    model = Model.create(uri=BLDG)
    lib = Library.from_ontology(SHAPE1, infer_templates=False)
    model.manifest.add(lib)
    with_member = len(model.manifest.imports_closure(error_on_missing=False))
    model.manifest.remove(lib)
    without = len(model.manifest.imports_closure(error_on_missing=False))
    assert without < with_member


def test_closure_and_per_collection_validation_agree(bm: BuildingMOTIF, shacl_engine):
    """The closure is an optimization, not a behavior change: validating
    against the manifest must report exactly what resolving each collection's
    imports separately reports."""
    bm.shacl_engine = shacl_engine
    Library.from_ontology("tests/unit/fixtures/Brick.ttl")
    lib = Library.from_ontology(SHAPE1)
    model = Model.create(uri="https://example.com")
    model.graph.add((URIRef("https://example.com/vav1"), RDF.type, BRICK.VAV))
    model.manifest.add(lib)

    # no arguments -> the manifest closure; an explicit list -> per collection
    via_closure = model.validate()
    via_collections = model.validate(model.manifest.shape_collections())

    # NB: not `is False` -- the topquadrant backend reports 0/1, not a bool
    assert not via_closure.valid and not via_collections.valid
    assert set(via_closure.diffset) == set(via_collections.diffset)
    assert {
        (f, str(d.reason())) for f, s in via_closure.diffset.items() for d in s
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

    model.manifest.remove(lib)
    assert model.validate().valid, "and removing the library lifts them again"
