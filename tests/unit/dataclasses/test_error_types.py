"""Tests that failures raise a type a caller can actually catch.

The dataclasses used to raise bare `Exception` for bad arguments, malformed
shapes, and unexpected library state alike, so the only way to handle any of
them was `except Exception` -- which also swallows real bugs.
"""

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model
from buildingmotif.utils import get_template_parts_from_shape

BLDG = Namespace("urn:bldg/")
EX = Namespace("http://ex/")


def test_model_load_without_id_or_name_raises_value_error(bm: BuildingMOTIF):
    """Bad arguments are a ValueError, matching Library.load()."""
    with pytest.raises(ValueError, match="either id or name"):
        Model.load()


def test_library_from_directory_missing_raises_file_not_found(bm: BuildingMOTIF):
    with pytest.raises(FileNotFoundError):
        Library.from_directory("no/such/directory")


def test_library_load_without_arguments_raises_value_error(bm: BuildingMOTIF):
    with pytest.raises(ValueError):
        Library.load()


def test_property_shape_without_a_path_raises_value_error(bm: BuildingMOTIF):
    """A malformed shape is bad input, not an unknown failure."""
    shapes = Graph().parse(
        data="""
        @prefix sh:  <http://www.w3.org/ns/shacl#> .
        @prefix ex:  <http://ex/> .
        ex:Bad a sh:NodeShape ;
          sh:property [ sh:minCount 1 ; sh:class ex:T ] .
        """,
        format="turtle",
    )
    with pytest.raises(ValueError, match="no sh:path"):
        get_template_parts_from_shape(EX.Bad, shapes)


def test_shape_with_two_object_types_raises_value_error(bm: BuildingMOTIF):
    shapes = Graph().parse(
        data="""
        @prefix sh:  <http://www.w3.org/ns/shacl#> .
        @prefix ex:  <http://ex/> .
        ex:Bad a sh:NodeShape ;
          sh:property [ sh:path ex:p ; sh:minCount 1 ;
                        sh:class ex:T ; sh:node ex:U ] .
        """,
        format="turtle",
    )
    with pytest.raises(ValueError, match="more than one object type"):
        get_template_parts_from_shape(EX.Bad, shapes)


def test_these_are_all_still_exceptions(bm: BuildingMOTIF):
    """Narrowing the types must not break existing `except Exception:`
    handlers -- ValueError and FileNotFoundError are both Exceptions."""
    for call in (
        Model.load,
        Library.load,
        lambda: Library.from_directory("no/such/directory"),
    ):
        with pytest.raises(Exception):
            call()


# -- the "default" sentinel (API-CLEANUP #13) ----------------------------


def _model_with_shapes(bm: BuildingMOTIF) -> Model:
    model = Model.create("urn:bldg/")
    model.add_graph(
        Graph().parse(
            data="@prefix ex: <http://ex/> .\n<urn:bldg/x> a ex:Foo .", format="turtle"
        )
    )
    return model


def test_compiled_model_inherits_the_engine_by_default(bm: BuildingMOTIF):
    """None means "inherit from the active BuildingMOTIF" -- the sentinel the
    rest of the codebase already uses."""
    compiled = _model_with_shapes(bm).compile([])
    assert compiled.shacl_engine == bm.shacl_engine


def test_compiled_model_honours_an_explicit_engine(bm: BuildingMOTIF):
    compiled = _model_with_shapes(bm).compile([], shacl_engine="pyshacl")
    assert compiled.shacl_engine == "pyshacl"


def test_compiled_model_still_accepts_the_legacy_default_string(bm: BuildingMOTIF):
    """ "default" was the old spelling of "inherit"; it keeps working."""
    from buildingmotif.dataclasses.compiled_model import CompiledModel

    model = _model_with_shapes(bm)
    compiled = CompiledModel(model, [], model.graph, shacl_engine="default")
    assert compiled.shacl_engine == bm.shacl_engine
