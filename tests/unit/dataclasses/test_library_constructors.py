"""Tests for Library's named constructors -- from_ontology / from_directory /
by_name -- and for load(), which is now the by-id loader (matching
Template.load(id) and ShapeCollection.load(id)) with every other keyword
deprecated.
"""

import logging
import pathlib
import warnings

import pytest
import rdflib

from buildingmotif import BuildingMOTIF
from buildingmotif.database.errors import LibraryNotFound
from buildingmotif.dataclasses import Library

FIXTURES = "tests/unit/fixtures/templates"


def _ontology_graph(name: str = "urn:ex/ont") -> rdflib.Graph:
    return rdflib.Graph().parse(
        data=f"""
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        <{name}> a owl:Ontology .
        """,
        format="turtle",
    )


# -- from_directory ------------------------------------------------------


def test_from_directory(bm: BuildingMOTIF):
    lib = Library.from_directory(FIXTURES)
    assert lib.name == "templates"
    assert lib.get_templates()


def test_from_directory_accepts_a_path_object(bm: BuildingMOTIF):
    """pathlib.Path is the natural thing to pass; load() only took str."""
    lib = Library.from_directory(pathlib.Path(FIXTURES))
    assert lib.name == "templates"


def test_from_directory_resolves_builtins(bm: BuildingMOTIF):
    """A relative name matching a packaged library resolves to the builtin."""
    lib = Library.from_directory("bacnet")
    assert lib.name == "bacnet"
    assert lib.get_templates()


def test_from_directory_missing_raises_file_not_found(bm: BuildingMOTIF):
    """Used to be a bare Exception."""
    with pytest.raises(FileNotFoundError, match="does not exist"):
        Library.from_directory("no/such/directory")


# -- from_ontology -------------------------------------------------------


def test_from_ontology_with_a_graph(bm: BuildingMOTIF):
    lib = Library.from_ontology(
        _ontology_graph(), run_shacl_inference=False, fetch_imports=False
    )
    assert lib.name == "urn:ex/ont"


def test_from_ontology_with_a_path(bm: BuildingMOTIF, tmp_path):
    path = tmp_path / "ont.ttl"
    _ontology_graph("urn:ex/from-file").serialize(
        destination=str(path), format="turtle"
    )
    lib = Library.from_ontology(
        str(path), run_shacl_inference=False, fetch_imports=False
    )
    assert lib.name == "urn:ex/from-file"


def test_from_ontology_accepts_a_path_object(bm: BuildingMOTIF, tmp_path):
    path = tmp_path / "ont.ttl"
    _ontology_graph("urn:ex/path-obj").serialize(destination=str(path), format="turtle")
    lib = Library.from_ontology(path, run_shacl_inference=False, fetch_imports=False)
    assert lib.name == "urn:ex/path-obj"


# -- by_name / load(id) --------------------------------------------------


def test_by_name_round_trips(bm: BuildingMOTIF):
    lib = Library.from_directory(FIXTURES)
    assert Library.by_name(lib.name).id == lib.id


def test_load_by_id_round_trips(bm: BuildingMOTIF):
    """`load(id)` is the by-id loader, matching Template.load(id) and
    ShapeCollection.load(id)."""
    lib = Library.from_directory(FIXTURES)
    assert Library.load(lib.id).name == lib.name


def test_by_name_unknown_raises(bm: BuildingMOTIF):
    with pytest.raises(LibraryNotFound):
        Library.by_name("no-such-library")


def test_load_unknown_id_raises(bm: BuildingMOTIF):
    with pytest.raises(LibraryNotFound):
        Library.load(123456)


def test_by_name_does_not_load_from_disk(bm: BuildingMOTIF):
    """by_name is a database lookup; it must not fall back to reading the
    directory of the same name."""
    with pytest.raises(LibraryNotFound):
        Library.by_name("bacnet")


# -- overwrite=False is a documented no-op -------------------------------


def test_overwrite_false_returns_the_existing_library(bm: BuildingMOTIF):
    first = Library.from_directory(FIXTURES)
    again = Library.from_directory(FIXTURES, overwrite=False)
    assert again.id == first.id


def test_overwrite_false_does_not_warn(bm: BuildingMOTIF, caplog):
    """Returning the existing library is what overwrite=False means, so it is
    logged at INFO rather than raised as a warning."""
    Library.from_directory(FIXTURES)
    with caplog.at_level(logging.DEBUG):
        Library.from_directory(FIXTURES, overwrite=False)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any(
        "overwrite=False" in r.getMessage() and r.levelno == logging.INFO
        for r in caplog.records
    )


# -- load(): id is current, every other keyword is deprecated ------------


def test_load_with_an_id_does_not_warn(bm: BuildingMOTIF):
    """Loading by id is what load() is *for*, so it must be warning-free."""
    lib = Library.from_directory(FIXTURES)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        assert Library.load(lib.id).name == lib.name
        assert Library.load(db_id=lib.id).name == lib.name


@pytest.mark.parametrize(
    "kwargs, replacement",
    [
        ({"directory": FIXTURES}, "from_directory"),
        ({"name": "templates"}, "by_name"),
    ],
)
def test_deprecated_load_keywords_warn_and_still_work(bm, kwargs, replacement):
    if "name" in kwargs:
        Library.from_directory(FIXTURES)  # so there is something to find
    with pytest.warns(DeprecationWarning, match=replacement):
        lib = Library.load(**kwargs)
    assert lib.name == "templates"


def test_deprecated_ontology_graph_keyword_warns(bm: BuildingMOTIF):
    with pytest.warns(DeprecationWarning, match="from_ontology"):
        lib = Library.load(
            ontology_graph=_ontology_graph("urn:ex/dep"),
            run_shacl_inference=False,
            fetch_imports=False,
        )
    assert lib.name == "urn:ex/dep"


def test_load_with_no_arguments_raises_value_error(bm: BuildingMOTIF):
    """Used to be a bare Exception."""
    with pytest.raises(ValueError, match="database id"):
        Library.load()


def test_load_with_id_and_a_source_keyword_is_ambiguous(bm: BuildingMOTIF):
    """Previously db_id silently won and the other argument was ignored."""
    lib = Library.from_directory(FIXTURES)
    with pytest.raises(ValueError, match="both db_id"):
        Library.load(lib.id, directory=FIXTURES)


def test_named_constructors_do_not_warn(bm: BuildingMOTIF):
    """The replacements must be usable without tripping the deprecation."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        lib = Library.from_directory(FIXTURES)
        Library.by_name(lib.name)
        Library.load(lib.id)
