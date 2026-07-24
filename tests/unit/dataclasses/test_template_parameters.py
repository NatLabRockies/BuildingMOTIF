"""Tests for Template.parameters_with_dependencies(), the single entry point
replacing all_parameters / dependency_parameters / transitive_parameters.

The equivalence tests are the load-bearing ones: they pin the new method's
flag combinations to exactly what the old properties returned.
"""

import warnings
from collections import Counter

import pytest

from buildingmotif import BuildingMOTIF
from buildingmotif.database.errors import TemplateNotFound
from buildingmotif.dataclasses import Library


@pytest.fixture
def lib(bm: BuildingMOTIF):
    return Library.from_directory("tests/unit/fixtures/templates")


@pytest.fixture
def ahu(lib):
    """A template with two dependencies (supply-fan, outside-air-damper), each
    with dependencies of their own."""
    return lib.get_template_by_name("single-zone-vav-ahu")


@pytest.fixture
def vav(lib):
    """A template whose dependency uses a parameter name (`name`) that the
    parent also uses -- the overlap case."""
    return lib.get_template_by_name("vav")


def _quiet(fn):
    """Read a deprecated property without turning its warning into an error."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return fn()


# -- the axes ------------------------------------------------------------


def test_parameters_is_local_only(ahu):
    """`parameters` is unchanged: the body's own parameters, no dependencies."""
    assert "sf" in ahu.parameters, "sf is bound in this template's own body"
    assert "sf-spd" not in ahu.parameters, "sf-spd belongs to the dependency"


def test_transitive_recurses_further_than_direct(ahu):
    direct = ahu.parameters_with_dependencies(transitive=False, renamed=False)
    transitive = ahu.parameters_with_dependencies(transitive=True, renamed=False)
    assert direct.issubset(transitive)


def test_renamed_matches_what_inlining_produces(ahu):
    """The point of `renamed=True`: it answers "what will I have to bind after
    inline_dependencies()" without doing the inlining."""
    assert ahu.parameters_with_dependencies() == ahu.inline_dependencies().parameters


def test_renamed_uses_the_dependency_arg_names(ahu):
    """A dependency parameter bound by `args` is reported under the parent's
    name for it; one that isn't gets the `name` binding as a prefix."""
    renamed = ahu.parameters_with_dependencies(transitive=True, renamed=True)
    raw = ahu.parameters_with_dependencies(transitive=True, renamed=False)
    # the supply-fan dependency is bound to the parent's "sf" parameter, so its
    # own "spd" parameter surfaces as "sf-spd"
    assert "sf-spd" in renamed
    assert "spd" in raw and "sf-spd" not in raw


def test_include_self_excludes_only_the_top_level(ahu):
    with_self = ahu.parameters_with_dependencies(transitive=False, renamed=False)
    without = ahu.parameters_with_dependencies(
        transitive=False, renamed=False, include_self=False
    )
    assert without.issubset(with_self)
    assert "oat" in with_self, "oat is one of this template's own parameters"
    assert "oat" not in without


def test_include_self_is_not_a_set_difference(vav):
    """The subtlety `include_self` exists for: a dependency may use a parameter
    name the parent also uses, so `include_self=False` is not
    `all - parameters`."""
    without_self = vav.parameters_with_dependencies(
        transitive=False, renamed=False, include_self=False
    )
    with_self = vav.parameters_with_dependencies(transitive=False, renamed=False)
    difference = with_self - vav.parameters

    assert "name" in without_self, "the dependency has its own `name` parameter"
    assert (
        "name" not in difference
    ), "...but subtracting loses it, since the parent has one too"
    assert without_self != difference


# -- equivalence with the deprecated properties --------------------------


def test_equivalent_to_all_parameters(ahu, vav):
    for templ in (ahu, vav):
        assert _quiet(
            lambda: templ.all_parameters
        ) == templ.parameters_with_dependencies(transitive=False, renamed=False)


def test_equivalent_to_dependency_parameters(ahu, vav):
    for templ in (ahu, vav):
        assert _quiet(
            lambda: templ.dependency_parameters
        ) == templ.parameters_with_dependencies(
            transitive=False, renamed=False, include_self=False
        )


def test_equivalent_to_transitive_parameters(ahu, vav):
    for templ in (ahu, vav):
        assert (
            _quiet(lambda: templ.transitive_parameters)
            == templ.parameters_with_dependencies()
        )


def test_template_without_dependencies_is_just_its_parameters(lib):
    templ = lib.get_template_by_name("zone")
    assert not templ.get_dependencies()
    for kwargs in (
        {},
        {"transitive": False, "renamed": False},
        {"transitive": True, "renamed": False},
    ):
        assert templ.parameters_with_dependencies(**kwargs) == templ.parameters
    assert (
        templ.parameters_with_dependencies(include_self=False) == set()
    ), "no dependencies means nothing to contribute"


# -- deprecation ---------------------------------------------------------


@pytest.mark.parametrize(
    "prop", ["all_parameters", "dependency_parameters", "transitive_parameters"]
)
def test_deprecated_properties_warn(ahu, prop):
    with pytest.warns(DeprecationWarning, match="parameters_with_dependencies"):
        getattr(ahu, prop)


def test_parameters_is_not_deprecated(ahu):
    """The workhorse accessor keeps working without a warning."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert ahu.parameters


# -- the phantom argument (API-CLEANUP #7) -------------------------------


def test_error_on_missing_dependency_is_actually_settable(ahu):
    """These used to be @property methods declaring an
    `error_on_missing_dependency` argument nobody could ever pass. It is now a
    real argument on a real method."""
    assert ahu.parameters_with_dependencies(
        error_on_missing_dependency=False
    ) == ahu.parameters_with_dependencies(
        error_on_missing_dependency=True
    ), "with every dependency resolvable, the flag makes no difference"


def test_missing_dependency_raises_by_default(ahu, monkeypatch):
    """An unresolvable dependency raises unless the caller opts out."""
    deps = ahu.get_dependencies()
    assert deps, "fixture must have dependencies for this test to mean anything"
    monkeypatch.setattr(type(deps[0]), "template", property(lambda self: None))

    with pytest.raises(TemplateNotFound):
        ahu.parameters_with_dependencies()

    # ...and skips it when asked to
    skipped = ahu.parameters_with_dependencies(error_on_missing_dependency=False)
    assert skipped == ahu.parameters


# -- parameter_counts ----------------------------------------------------


def test_parameter_counts_is_a_histogram(ahu):
    counts = ahu.parameter_counts
    assert isinstance(counts, Counter)
    # every local parameter is counted at least once
    for param in ahu.parameters:
        assert counts[param] >= 1


def test_parameter_counts_keys_match_the_raw_transitive_set(ahu):
    """parameter_counts is the multiset version of
    parameters_with_dependencies(renamed=False)."""
    assert set(ahu.parameter_counts) == ahu.parameters_with_dependencies(
        transitive=True, renamed=False
    )


def test_parameter_counts_takes_no_arguments(ahu):
    """It used to declare an `error_on_missing_dependency` argument that could
    never be supplied."""
    with pytest.raises(TypeError):
        ahu.parameter_counts(error_on_missing_dependency=False)
