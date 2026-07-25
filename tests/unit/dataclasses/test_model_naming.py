"""Model.create()'s argument is a URI, and the manifest methods say what they do."""

import warnings

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Model, ShapeCollection

BLDG = Namespace("urn:bldg/")


# -- Model.create(uri=...) (API-CLEANUP #11) -----------------------------


def test_create_takes_a_uri_positionally(bm: BuildingMOTIF):
    assert Model.create(BLDG).name == "urn:bldg/"


def test_create_takes_uri_by_keyword(bm: BuildingMOTIF):
    assert Model.create(uri="urn:bldg/").name == "urn:bldg/"


def test_create_with_description(bm: BuildingMOTIF):
    model = Model.create(BLDG, "a description")
    assert model.description == "a description"


def test_name_keyword_still_works_but_warns(bm: BuildingMOTIF):
    with pytest.warns(DeprecationWarning, match="uri"):
        model = Model.create(name="urn:bldg/")
    assert model.name == "urn:bldg/"


def test_uri_and_name_together_is_an_error(bm: BuildingMOTIF):
    with pytest.raises(TypeError, match="same argument"):
        Model.create(uri="urn:a/", name="urn:b/")


def test_create_with_no_argument_is_an_error(bm: BuildingMOTIF):
    with pytest.raises(TypeError, match="missing required argument"):
        Model.create()


def test_create_still_rejects_a_non_uri(bm: BuildingMOTIF):
    with pytest.raises(ValueError):
        Model.create("not a uri")


def test_uri_keyword_does_not_warn(bm: BuildingMOTIF):
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        Model.create(uri="urn:bldg/")


# -- manifest methods (API-CLEANUP #17) ----------------------------------


def _shapes(path: str) -> ShapeCollection:
    sc = ShapeCollection.create()
    sc.add_graph(
        Graph().parse(
            data=f"""
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix ex: <http://ex/> .
            ex:{path} a sh:NodeShape .
            """,
            format="turtle",
        )
    )
    return sc


def test_add_to_manifest_merges(bm: BuildingMOTIF):
    model = Model.create(BLDG)
    model.add_to_manifest(_shapes("A"))
    model.add_to_manifest(_shapes("B"))
    text = model.get_manifest().graph.serialize(format="turtle")
    assert "A" in text and "B" in text, "add_to_manifest should keep both"


def test_replace_manifest_replaces(bm: BuildingMOTIF):
    """There was previously no way to do this: update_manifest only merged, so
    a manifest could grow but never shrink."""
    model = Model.create(BLDG)
    model.add_to_manifest(_shapes("A"))
    model.replace_manifest(_shapes("B"))
    text = model.get_manifest().graph.serialize(format="turtle")
    assert "B" in text
    assert "ex:A" not in text, "replace_manifest should drop the previous shapes"


def test_update_manifest_still_works_but_warns(bm: BuildingMOTIF):
    model = Model.create(BLDG)
    with pytest.warns(DeprecationWarning, match="add_to_manifest"):
        model.update_manifest(_shapes("A"))
    assert "A" in model.get_manifest().graph.serialize(format="turtle")


def test_update_manifest_is_still_a_merge(bm: BuildingMOTIF):
    """The deprecated name keeps its old behavior exactly."""
    model = Model.create(BLDG)
    model.add_to_manifest(_shapes("A"))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        model.update_manifest(_shapes("B"))
    text = model.get_manifest().graph.serialize(format="turtle")
    assert "A" in text and "B" in text
