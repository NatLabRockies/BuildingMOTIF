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
    with pytest.raises(Exception):
        Model.load()
    with pytest.raises(Exception):
        Library.load()
    with pytest.raises(Exception):
        Library.from_directory("no/such/directory")


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


# -- add_dependency argument handling (API-CLEANUP #18) ------------------


def _two_templates(bm: BuildingMOTIF):
    lib = Library.from_directory("tests/unit/fixtures/templates")
    return lib.get_template_by_name("zone"), lib.get_template_by_name("vav")


def test_add_dependency_positional_form(bm: BuildingMOTIF):
    a, b = _two_templates(bm)
    a.add_dependency(b, {"name": "name"})
    assert len(a.get_dependencies()) == 1


def test_add_dependency_keyword_form(bm: BuildingMOTIF):
    """The form the @overload signature documents. It used to raise IndexError,
    because `kwargs.get("dependency", args[0])` evaluates its default eagerly
    and `args` is empty in the keyword form."""
    a, b = _two_templates(bm)
    a.add_dependency(dependency=b, args={"name": "name"})
    assert len(a.get_dependencies()) == 1


@pytest.mark.parametrize("n_args", [1, 4, 5])
def test_add_dependency_with_wrong_arity_raises(bm: BuildingMOTIF, n_args):
    """The dispatch matched exactly 2 or 3 arguments with no else, so any other
    count silently did nothing and the dependency was never created."""
    a, b = _two_templates(bm)
    call_args = [b, {"name": "name"}, {}, {}, {}][:n_args]
    with pytest.raises(TypeError):
        a.add_dependency(*call_args)
    assert len(a.get_dependencies()) == 0


def test_add_dependency_unknown_keyword_raises(bm: BuildingMOTIF):
    a, b = _two_templates(bm)
    with pytest.raises(TypeError, match="unexpected keyword"):
        a.add_dependency(b, {"name": "name"}, nonsense=1)


def test_add_dependency_duplicate_value_raises(bm: BuildingMOTIF):
    a, b = _two_templates(bm)
    with pytest.raises(TypeError, match="multiple values"):
        a.add_dependency(b, {"name": "name"}, dependency=b)


def test_add_dependency_by_name(bm: BuildingMOTIF):
    a, b = _two_templates(bm)
    a.add_dependency_by_name(b.defining_library.name, b.name, {"name": "name"})
    assert len(a.get_dependencies()) == 1


def test_three_argument_form_is_deprecated_but_works(bm: BuildingMOTIF):
    a, b = _two_templates(bm)
    with pytest.warns(DeprecationWarning, match="add_dependency_by_name"):
        a.add_dependency(b.defining_library.name, b.name, {"name": "name"})
    assert len(a.get_dependencies()) == 1
