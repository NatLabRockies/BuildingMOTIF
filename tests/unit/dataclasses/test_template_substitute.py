"""Tests for the single-return-type template API: substitute() always returns a
Template, to_graph() always returns a Graph. Replaces the Template|Graph union
that Template.evaluate() returns."""

import warnings

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import IncompleteTemplateError, Library, Template
from buildingmotif.namespaces import BRICK, A

BLDG = Namespace("urn:building/")


@pytest.fixture
def lib(bm: BuildingMOTIF):
    return Library.load(directory="tests/unit/fixtures/templates")


@pytest.fixture
def zone(lib):
    """A template with two required parameters: name, cav."""
    templ = lib.get_template_by_name("zone")
    assert templ.parameters == {"name", "cav"}
    return templ


@pytest.fixture
def opt_vav(lib):
    """A template with one required parameter (name) and two optional
    (occ, zone)."""
    templ = lib.get_template_by_name("opt-vav")
    assert templ.parameters == {"name", "occ", "zone"}
    assert templ.optional_args == ["occ", "zone"]
    return templ


# -- substitute always returns a Template --------------------------------


def test_substitute_returns_template_when_partially_bound(zone):
    result = zone.substitute({"name": BLDG["zone1"]})
    assert isinstance(result, Template)
    assert not result.is_complete
    assert result.parameters == {"cav"}


def test_substitute_returns_template_when_fully_bound(zone):
    """The case where evaluate() would have switched to returning a Graph."""
    result = zone.substitute({"name": BLDG["zone1"], "cav": BLDG["cav1"]})
    assert isinstance(result, Template)
    assert result.is_complete


def test_substitute_returns_template_with_no_bindings(zone):
    result = zone.substitute({})
    assert isinstance(result, Template)
    assert result.parameters == {"name", "cav"}


def test_substitute_does_not_mutate_the_original(zone):
    zone.substitute({"name": BLDG["zone1"], "cav": BLDG["cav1"]})
    assert zone.parameters == {"name", "cav"}


def test_substitute_is_chainable(zone):
    """Partial application composes without changing type along the way."""
    graph = (
        zone.substitute({"name": BLDG["zone1"]})
        .substitute({"cav": BLDG["cav1"]})
        .to_graph()
    )
    assert isinstance(graph, Graph)
    assert (BLDG["zone1"], BRICK.isFedBy, BLDG["cav1"]) in graph


def test_substitute_is_quiet_by_default(zone):
    """Unlike evaluate(), a partial result is ordinary and does not warn."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        zone.substitute({"name": BLDG["zone1"]})


def test_substitute_can_warn_on_request(zone):
    with pytest.warns(UserWarning, match="cav"):
        zone.substitute({"name": BLDG["zone1"]}, warn_unused=True)


def test_substitute_does_not_warn_when_complete(zone):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        zone.substitute({"name": BLDG["zone1"], "cav": BLDG["cav1"]}, warn_unused=True)


# -- is_complete / missing_parameters ------------------------------------


def test_is_complete_ignores_unbound_optionals(opt_vav):
    result = opt_vav.substitute({"name": BLDG["vav1"]})
    assert result.is_complete
    assert result.missing_parameters == set()
    # the optionals are still parameters, they just do not block to_graph()
    assert result.parameters == {"occ", "zone"}


def test_missing_parameters_lists_only_required(zone):
    result = zone.substitute({"name": BLDG["zone1"]})
    assert result.missing_parameters == {"cav"}


# -- to_graph always returns a Graph -------------------------------------


def test_to_graph_returns_graph(zone):
    graph = zone.substitute({"name": BLDG["zone1"], "cav": BLDG["cav1"]}).to_graph()
    assert isinstance(graph, Graph)
    assert (BLDG["zone1"], A, BRICK.HVAC_Zone) in graph
    assert (BLDG["cav1"], A, BRICK.CAV) in graph
    assert len(graph) == 3


def test_to_graph_raises_when_incomplete(zone):
    with pytest.raises(IncompleteTemplateError) as excinfo:
        zone.substitute({"name": BLDG["zone1"]}).to_graph()
    assert excinfo.value.missing == {"cav"}
    assert "cav" in str(excinfo.value)


def test_incomplete_template_error_is_a_value_error(zone):
    """Subclassing ValueError keeps existing handlers working."""
    with pytest.raises(ValueError):
        zone.substitute({}).to_graph()


def test_to_graph_drops_unbound_optionals(opt_vav):
    graph = opt_vav.substitute({"name": BLDG["vav1"]}).to_graph()
    assert isinstance(graph, Graph)
    # only the type triple survives; occ and zone triples are dropped
    assert len(graph) == 1
    assert (BLDG["vav1"], None, None) in graph


def test_to_graph_keeps_bound_optionals(opt_vav):
    """A bound optional's triples survive, as long as they do not also touch an
    unbound one."""
    graph = opt_vav.substitute({"name": BLDG["vav1"], "occ": BLDG["occ1"]}).to_graph()
    assert (BLDG["vav1"], BRICK.hasPoint, BLDG["occ1"]) in graph
    assert (BLDG["occ1"], A, BRICK.Occupancy_Sensor) in graph


def test_dropping_an_unbound_optional_cascades(opt_vav):
    """Dropping an unbound optional also drops triples that merely mention it,
    even where the other terms are bound.

    In ``opt-vav`` the only triple naming ``zone`` is ``occ brick:isPointOf
    zone``, so binding ``zone`` but not ``occ`` still loses it -- only the
    ``name a brick:VAV`` triple survives.
    """
    graph = opt_vav.substitute({"name": BLDG["vav1"], "zone": BLDG["zone1"]}).to_graph()
    assert len(graph) == 1
    assert (BLDG["vav1"], A, BRICK.VAV) in graph
    assert not any(BLDG["zone1"] in triple for triple in graph)


def test_to_graph_require_optional_args_raises_on_unbound_optional(opt_vav):
    with pytest.raises(IncompleteTemplateError) as excinfo:
        opt_vav.substitute({"name": BLDG["vav1"]}).to_graph(require_optional_args=True)
    assert excinfo.value.missing == {"occ", "zone"}


def test_to_graph_require_optional_args_succeeds_when_all_bound(opt_vav):
    graph = opt_vav.substitute(
        {"name": BLDG["vav1"], "occ": BLDG["occ1"], "zone": BLDG["zone1"]}
    ).to_graph(require_optional_args=True)
    assert isinstance(graph, Graph)
    assert any(BLDG["occ1"] in triple for triple in graph)


def test_to_graph_binds_namespaces(zone):
    graph = zone.substitute({"name": BLDG["zone1"], "cav": BLDG["cav1"]}).to_graph(
        namespaces={"bldg": BLDG}
    )
    assert "bldg" in dict(graph.namespaces())


def test_to_graph_does_not_mutate_the_template(opt_vav):
    filled = opt_vav.substitute({"name": BLDG["vav1"]})
    before = len(filled.body)
    filled.to_graph()
    assert len(filled.body) == before, "to_graph() stripped optionals in place"
    # and it is repeatable
    assert len(filled.to_graph()) == len(filled.to_graph())


# -- evaluate() still works, but is deprecated ---------------------------


def test_evaluate_is_deprecated_but_unchanged(zone):
    with pytest.warns(DeprecationWarning, match="substitute"):
        result = zone.evaluate({"name": BLDG["zone1"], "cav": BLDG["cav1"]})
    assert isinstance(result, Graph), "evaluate() must keep its old return type"


def test_evaluate_still_returns_template_when_partial(zone):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = zone.evaluate({"name": BLDG["zone1"]})
    assert isinstance(result, Template)


def test_evaluate_and_substitute_agree(zone):
    """The deprecated path is implemented in terms of the new one, so the two
    must produce the same graph."""
    bindings = {"name": BLDG["zone1"], "cav": BLDG["cav1"]}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        old = zone.evaluate(bindings)
    new = zone.substitute(bindings).to_graph()
    assert isinstance(old, Graph)
    assert set(old) == set(new)


def test_fill_still_returns_a_graph(zone):
    """fill() is unchanged and now routes through substitute()/to_graph()."""
    bindings, graph = zone.fill(BLDG)
    assert isinstance(graph, Graph)
    assert set(bindings.keys()) == {"name", "cav"}
    assert len(graph) == 3
