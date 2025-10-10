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
