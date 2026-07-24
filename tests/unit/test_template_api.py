import warnings

import pytest
from rdflib import Graph, Namespace

from buildingmotif import BuildingMOTIF
from buildingmotif.dataclasses import Library, Model, Template
from buildingmotif.namespaces import BRICK, PARAM, A
from buildingmotif.template_matcher import TemplateMatcher
from buildingmotif.utils import graph_size

BLDG = Namespace("urn:building/")


def test_template_evaluate(bm: BuildingMOTIF):
    """
    Test the Template.evaluate() method.
    """
    lib = Library.load(directory="tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    assert zone.parameters == {"name", "cav"}

    with pytest.warns():
        partial = zone.evaluate({"name": BLDG["zone1"]})
        assert isinstance(partial, Template)
        assert partial.parameters == {"cav"}

    graph = partial.evaluate({"cav": BLDG["cav1"]})
    assert isinstance(graph, Graph)
    assert (BLDG["cav1"], A, BRICK.CAV) in graph
    assert (BLDG["zone1"], A, BRICK.HVAC_Zone) in graph
    assert (BLDG["zone1"], BRICK.isFedBy, BLDG["cav1"]) in graph
    assert len(list(graph.triples((None, None, None)))) == 3


def test_template_fill(bm: BuildingMOTIF):
    """
    Test the Template.fill() method.
    """
    lib = Library.load(directory="tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    assert zone.parameters == {"name", "cav"}

    bindings, graph = zone.fill(BLDG)
    assert isinstance(bindings, dict)
    assert "name" in bindings.keys()
    assert "cav" in bindings.keys()
    assert isinstance(graph, Graph)
    assert len(list(graph.triples((None, None, None)))) == 3


def test_template_copy(bm: BuildingMOTIF):
    """
    Test the Template.copy() method.
    """
    lib = Library.load(directory="tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    assert zone.parameters == {"name", "cav"}

    zone2 = zone.in_memory_copy()
    assert zone2.parameters == {"name", "cav"}
    # should be able to edit the copy without editing the original
    zone2.body.add((PARAM["zone2"], A, BRICK.Zone))
    assert zone2.parameters == {"name", "zone2", "cav"}
    assert zone.parameters == {"name", "cav"}


def test_template_to_inline(bm: BuildingMOTIF):
    """
    Test the Template.to_inline() method.
    """
    lib = Library.load(directory="tests/unit/fixtures/templates")
    zone = lib.get_template_by_name("zone")
    assert zone.parameters == {"name", "cav"}

    # inline *all* parameters
    inlined = zone.to_inline()
    assert all([x.endswith("-inlined") for x in inlined.parameters])
    assert len(inlined.parameters) == len(zone.parameters)

    # inline *some* parameters
    inlined = zone.to_inline(preserve_args=["cav"])
    inlined_params = [
        x for x in inlined.parameters if x.endswith("-inlined") and x.startswith("name")
    ]
    assert len(inlined_params) == 1
    assert "cav" in inlined.parameters


def test_template_inline_dependencies(bm: BuildingMOTIF):
    """
    Test the Template.inline_dependencies() method.
    """
    lib = Library.load(directory="tests/unit/fixtures/templates")
    templ = lib.get_template_by_name("single-zone-vav-ahu")
    assert len(templ.get_dependencies()) == 2
    inlined = templ.inline_dependencies()
    transitive_params = templ.transitive_parameters
    assert len(inlined.get_dependencies()) == 0
    preserved_params = {
        "name",
        "sf",
        "oad",
        "cd",
        "hd",
        "zt",
        "occ",
        "mat",
        "rat",
        "sat",
        "oat",
        "zone",
        "sf-spd",
        "sf-ss",
        "sf-st",
        "oad-pos",
        "oad-sen",
    }
    assert inlined.parameters == preserved_params
    assert transitive_params == preserved_params

    # test optional 'name' param on dependency; this should
    # preserve optionality of all params in the dependency
    lib = Library.load(directory="tests/unit/fixtures/inline-dep-test")
    templ = lib.get_template_by_name("A")
    assert templ.parameters == {"name", "b", "c", "d"}
    assert set(templ.optional_args) == {"d"}
    assert len(templ.get_dependencies()) == 3
    inlined = templ.inline_dependencies()
    transitive_params = templ.transitive_parameters
    assert len(inlined.get_dependencies()) == 0
    assert inlined.parameters == {"name", "b", "c", "b-bp", "c-cp", "d", "d-dp"}
    assert transitive_params == inlined.parameters
    assert set(inlined.optional_args) == {"d", "d-dp"}

    # test optional non-'name' parameter on dependency; this should
    # only make that single parameter optional
    templ = lib.get_template_by_name("A-alt")
    assert templ.parameters == {"name", "b"}
    assert set(templ.optional_args) == {"b-bp"}
    assert len(templ.get_dependencies()) == 1
    inlined = templ.inline_dependencies()
    transitive_params = templ.transitive_parameters
    assert len(inlined.get_dependencies()) == 0
    assert inlined.parameters == {"name", "b", "b-bp"}
    assert transitive_params == inlined.parameters
    assert set(inlined.optional_args) == {"b-bp"}

    # test inlining 2 or more levels
    parent = lib.get_template_by_name("Parent")
    assert parent.parameters == {"name", "level1"}
    inlined = parent.inline_dependencies()
    transitive_params = parent.transitive_parameters
    assert inlined.parameters == {
        "name",
        "level1",
        "level1-level2",
        "level1-level2-level3",
    }
    assert transitive_params == inlined.parameters
    assert len(inlined.optional_args) == 0

    # test inlining 2 or more levels with optional params
    parent = lib.get_template_by_name("Parent-opt")
    assert parent.parameters == {"name", "level1"}
    inlined = parent.inline_dependencies()
    transitive_params = parent.transitive_parameters
    assert inlined.parameters == {
        "name",
        "level1",
        "level1-level2",
        "level1-level2-level3",
    }
    assert transitive_params == inlined.parameters
    assert set(inlined.optional_args) == {
        "level1",
        "level1-level2",
        "level1-level2-level3",
    }


def test_template_inline_dependencies_with_optional(bm: BuildingMOTIF):
    # fixes https://github.com/NREL/BuildingMOTIF/issues/237
    lib = Library.load(directory="tests/unit/fixtures/optional-inline")
    templ = lib.get_template_by_name("hot-water-coil")
    templ = templ.inline_dependencies()
    bindings, _ = templ.fill(BLDG, include_optional=False)
    assert "supply-water-temp" in bindings.keys()
    assert "name" in bindings.keys()
    assert "supply-water-temp-sensor" not in bindings.keys()

    bindings, _ = templ.fill(BLDG, include_optional=True)
    assert "supply-water-temp" in bindings.keys()
    assert "name" in bindings.keys()
    assert "supply-water-temp-sensor" in bindings.keys()


def test_template_evaluate_with_optional(bm: BuildingMOTIF):
    """
    Test that template evaluation works with optional parameters.
    """
    lib = Library.load(directory="tests/unit/fixtures/templates")
    templ = lib.get_template_by_name("opt-vav")
    assert templ.parameters == {"name", "occ", "zone"}
    assert templ.optional_args == ["occ", "zone"]

    g = templ.evaluate({"name": BLDG["vav"]})
    assert isinstance(g, Graph)
    assert graph_size(g) == 1

    g = templ.evaluate({"name": BLDG["vav"], "zone": BLDG["zone1"]})
    assert isinstance(g, Graph)
    assert graph_size(g) == 1

    t = templ.evaluate(
        {"name": BLDG["vav"], "zone": BLDG["zone1"]}, require_optional_args=True
    )
    assert isinstance(t, Template)
    assert t.parameters == {"occ"}

    with pytest.warns():
        t = templ.evaluate(
            {"name": BLDG["vav"], "zone": BLDG["zone1"]}, require_optional_args=True
        )
    assert isinstance(t, Template)
    assert t.parameters == {"occ"}

    # assert no unused-parameter warning is raised when optional args are not
    # required. (evaluate() itself is deprecated and always warns about that,
    # which is not what this assertion is about.)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        warnings.simplefilter("ignore", DeprecationWarning)
        t = templ.evaluate({"name": BLDG["vav"]})

    with pytest.warns():
        partial_templ = templ.evaluate(
            {"name": BLDG["vav"]}, require_optional_args=True
        )
    assert isinstance(partial_templ, Template)
    g = partial_templ.evaluate({"zone": BLDG["zone1"]})
    assert isinstance(g, Graph)
    t = partial_templ.evaluate({"zone": BLDG["zone1"]}, require_optional_args=True)
    assert isinstance(t, Template)
    assert t.parameters == {"occ"}


def test_template_matching(bm: BuildingMOTIF):
    EX = Namespace("urn:ex/")
    brick = Library.load(ontology_graph="tests/unit/fixtures/matching/brick.ttl")
    lib = Library.load(directory="tests/unit/fixtures/templates")
    damper = lib.get_template_by_name("outside-air-damper")

    bldg = Model.create("https://example.com")
    bldg.add_graph(Graph().parse("tests/unit/fixtures/matching/model.ttl"))

    matcher = TemplateMatcher(bldg.graph, damper, brick.get_shape_collection().graph)
    assert matcher is not None
    mapping, _ = next(matcher.building_mapping_subgraphs_iter())
    assert mapping == {
        EX["damper1"]: PARAM["name"],
        BRICK["Outside_Air_Damper"]: BRICK["Outside_Air_Damper"],
    }

    remaining_template = matcher.remaining_template(mapping)
    assert isinstance(remaining_template, Template)
    assert remaining_template.parameters == {"sen", "pos"}


def test_template_matcher_with_graph_target(bm: BuildingMOTIF):
    BLDG = Namespace("urn:template-match-test/")
    brick = Library.load(
        ontology_graph="tests/unit/fixtures/Brick1.3rc1-equip-only.ttl"
    )
    templ_lib = Library.load(directory="tests/unit/fixtures/templates")
    sf_templ = templ_lib.get_template_by_name("supply-fan")

    data = """
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix : <urn:template-match-test/> .
:sf1 a brick:Fan .
    """
    model = Model.create(BLDG + "1")
    model.add_graph(Graph().parse(data=data))
    matcher = TemplateMatcher(model.graph, sf_templ, brick.get_shape_collection().graph)
    mapping, graph = next(matcher.building_mapping_subgraphs_iter())
    assert len(mapping) == 2
    print(mapping)
    assert graph is not None
    assert mapping[BLDG["sf1"]] == PARAM["name"]
    assert mapping[BRICK["Fan"]] == BRICK["Supply_Fan"]

    data = """
@prefix brick: <https://brickschema.org/schema/Brick#> .
@prefix : <urn:template-match-test/> .
:sf1 a brick:Fan .
:sf2 a brick:Fan .
    """
    model = Model.create(BLDG + "2")
    model.add_graph(Graph().parse(data=data))
    matcher = TemplateMatcher(
        model.graph, sf_templ, brick.get_shape_collection().graph, BLDG["sf2"]
    )
    mapping, graph = next(matcher.building_mapping_subgraphs_iter())
    assert len(mapping) == 2
    print(mapping)
    assert graph is not None
    assert mapping[BLDG["sf2"]] == PARAM["name"]
    assert mapping[BRICK["Fan"]] == BRICK["Supply_Fan"]

    matcher = TemplateMatcher(
        model.graph, sf_templ, brick.get_shape_collection().graph, BLDG["sf1"]
    )
    mapping, graph = next(matcher.building_mapping_subgraphs_iter())
    assert len(mapping) == 2
    print(mapping)
    assert graph is not None
    assert mapping[BLDG["sf1"]] == PARAM["name"]
    assert mapping[BRICK["Fan"]] == BRICK["Supply_Fan"]
