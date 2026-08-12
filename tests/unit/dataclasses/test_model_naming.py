"""Model.create()'s argument is a URI, and a manifest holds libraries."""

import warnings

import pytest
from rdflib import Namespace

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


# -- manifest methods ----------------------------------------------------
#
# The manifest is a set of *libraries* now, so the ShapeCollection-shaped
# methods this section used to cover (add_to_manifest of a collection,
# replace_manifest, update_manifest) are gone. What replaced them lives in
# test_manifest.py; the one thing worth pinning here is that the old argument
# type is rejected outright rather than doing something surprising.


def test_a_shape_collection_is_no_longer_a_manifest(bm: BuildingMOTIF):
    model = Model.create(BLDG)
    with pytest.raises(TypeError, match="not ShapeCollections"):
        model.add_to_manifest(ShapeCollection.create())


def test_the_replaced_methods_are_gone(bm: BuildingMOTIF):
    model = Model.create(BLDG)
    assert not hasattr(model, "replace_manifest")
    assert not hasattr(model, "update_manifest")
