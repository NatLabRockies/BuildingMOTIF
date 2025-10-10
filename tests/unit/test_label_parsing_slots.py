from buildingmotif.label_parsing.combinators import (
    COMMON_EQUIP_ABBREVIATIONS_BRICK,
    abbreviations,
    regex,
    sequence,
)
from buildingmotif.label_parsing.parser import parse_list, results_to_tokens
from buildingmotif.label_parsing.tokens import Delimiter, Identifier
from buildingmotif.namespaces import BRICK


def test_slot_grouping_non_adjacent():
    # Constant (equip type) and Identifier (equip id) are not adjacent due to a delimiter in between,
    # but share the same slot "equip", so results_to_tokens should pair them together.
    parser = sequence(
        abbreviations(COMMON_EQUIP_ABBREVIATIONS_BRICK, slot="equip"),
        regex(r"-", Delimiter),
        regex(r"[0-9]+", Identifier, slot="equip"),
    )

    results, failed = parse_list(parser, ["AHU-1"])
    assert len(failed) == 0
    assert "AHU-1" in results

    grouped = results_to_tokens(results)
    assert grouped == [
        {
            "label": "AHU-1",
            "tokens": [
                {"identifier": "1", "type": BRICK.Air_Handling_Unit.toPython()},
            ],
            "warnings": [],
        }
    ]


def test_slot_grouping_cross_order_two_groups():
    """
    More complex example: tokens appear as
      <ident 1> <ident 2> <const 2> <const 1>
    and should still pair by slot into two (identifier, type) entries.
    """
    parser = sequence(
        regex(r"\d+", Identifier, slot="g1"),
        regex(r"[-_]", Delimiter),
        regex(r"\d+", Identifier, slot="g2"),
        abbreviations({"SP": BRICK.Setpoint}, slot="g2"),
        abbreviations({"AHU": BRICK.Air_Handling_Unit}, slot="g1"),
    )

    results, failed = parse_list(parser, ["1-2SPAHU"])
    assert len(failed) == 0

    grouped = results_to_tokens(results)
    assert grouped == [
        {
            "label": "1-2SPAHU",
            "tokens": [
                {"identifier": "1", "type": BRICK.Air_Handling_Unit.toPython()},
                {"identifier": "2", "type": BRICK.Setpoint.toPython()},
            ],
            "warnings": [],
        }
    ]


def test_slot_method_returns_copy_and_groups():
    """
    Demonstrates using Parser.slot() to assign slots after constructing the parsers.
    Ensures the original parser is not mutated and that grouping works with non-adjacent tokens.
    """
    # Base parsers without slots
    equip = abbreviations(COMMON_EQUIP_ABBREVIATIONS_BRICK)
    ident = regex(r"\d+", Identifier)

    # Original equip parser should have no slot
    base_res = equip("AHU")
    assert base_res and base_res[0].slot is None

    # Use slot() to create slotted copies for grouping
    parser = sequence(
        equip.slot("equip"),
        regex(r"-", Delimiter),  # not slotted, just a delimiter
        ident.slot("equip"),
    )

    results, failed = parse_list(parser, ["AHU-7"])
    assert len(failed) == 0

    grouped = results_to_tokens(results)
    assert grouped == [
        {
            "label": "AHU-7",
            "tokens": [
                {"identifier": "7", "type": BRICK.Air_Handling_Unit.toPython()},
            ],
            "warnings": [],
        }
    ]
