import logging
import re
from typing import List

from rdflib import URIRef

from buildingmotif.label_parsing.parser import Parser
from buildingmotif.label_parsing.tokens import (
    Constant,
    Delimiter,
    Identifier,
    Null,
    Token,
    TokenOrConstructor,
    TokenResult,
    ensure_token,
)
from buildingmotif.namespaces import BRICK

logger = logging.getLogger()


class string(Parser):
    """Constructs a parser that matches a string."""

    def __init__(self, s: str, type_name: TokenOrConstructor, id=None):
        self.s = s
        self.type_name = type_name
        self.id = id

    def __call__(self, target: str) -> List[TokenResult]:
        if target.startswith(self.s):
            return [
                TokenResult(
                    self.s,
                    ensure_token(self.type_name, self.s),
                    len(self.s),
                    id=self.id,
                )
            ]
        return [
            TokenResult(
                None,
                Null(),
                0,
                f"Expected {self.s}, got {target[:len(self.s)]}",
                id=self.id,
            )
        ]


class rest(Parser):
    """Constructs a parser that matches the rest of the string."""

    def __init__(self, type_name: TokenOrConstructor, id=None):
        self.type_name = type_name
        self.id = id

    def __call__(self, target: str) -> List[TokenResult]:
        return [
            TokenResult(
                target, ensure_token(self.type_name, target), len(target), id=self.id
            )
        ]


class substring_n(Parser):
    """Constructs a parser that matches a substring of length n."""

    def __init__(self, length: int, type_name: TokenOrConstructor, id=None):
        self.length = length
        self.type_name = type_name
        self.id = id

    def __call__(self, target: str) -> List[TokenResult]:
        if len(target) >= self.length:
            value = target[: self.length]
            return [
                TokenResult(
                    value, ensure_token(self.type_name, value), self.length, id=self.id
                )
            ]
        return [
            TokenResult(
                None,
                Null(),
                0,
                f"Expected {self.length} characters, got {target[:self.length]}",
                id=self.id,
            )
        ]


class regex(Parser):
    """Constructs a parser that matches a regular expression."""

    def __init__(self, r: str, type_name: TokenOrConstructor, id=None):
        self.r = r
        self.type_name = type_name
        self.id = id

    def __call__(self, target: str) -> List[TokenResult]:
        match = re.match(self.r, target)
        if match:
            value = match.group()
            return [
                TokenResult(
                    value, ensure_token(self.type_name, value), len(value), id=self.id
                )
            ]
        return [
            TokenResult(
                None,
                Null(),
                0,
                f"Expected {self.r}, got {target[:len(self.r)]}",
                id=self.id,
            )
        ]


class choice(Parser):
    """Constructs a choice combinator of parsers."""

    def __init__(self, *parsers: Parser, id=None):
        self.parsers = parsers
        self.id = id

    def __call__(self, target: str) -> List[TokenResult]:
        errors = []
        for p in self.parsers:
            result = p(target)
            if result and not any(r.error for r in result):
                return result
            if result:
                errors.append(result[0].error)
        return [TokenResult(None, Null(), 0, " | ".join(errors), id=None)]  # type: ignore


class constant(Parser):
    """Matches a constant token."""

    def __init__(self, type_name: Token, id=None):
        self.id = id
        self.type_name = type_name

    def __call__(self, target: str) -> List[TokenResult]:
        return [TokenResult(None, self.type_name, 0, id=self.id)]


class abbreviations(Parser):
    """Constructs a choice combinator of string matching based on a dictionary."""

    def __init__(self, patterns: dict, id=None):
        parsers = [string(s, Constant(URIRef(t))) for s, t in patterns.items()]
        self.choice = choice(*parsers)
        self.id = id

    def __call__(self, target: str):
        return self.choice(target)


class sequence(Parser):
    """Applies parsers in sequence. All parsers must match consecutively."""

    def __init__(self, *parsers: Parser, id=None):
        self.parsers = parsers
        self.id = id

    def __call__(self, target: str) -> List[TokenResult]:
        results = []
        total_length = 0
        for p in self.parsers:
            result = p(target)
            if not result:
                raise Exception("Expected result")
            results.extend(result)
            # if there are any errors, return the results
            if any(r.error for r in result):
                return results
            # TODO: how to handle error?
            consumed_length = sum([r.length for r in result])
            target = target[consumed_length:]
            total_length += sum([r.length for r in result])
        return results


class many(Parser):
    """Applies the given sequence parser repeatedly until it stops matching."""

    def __init__(self, seq_parser: Parser, id=None):
        self.seq_parser = seq_parser
        self.id = id

    def __call__(self, target):
        results = []
        while True:
            part = self.seq_parser(target)
            if not part or part[0].value is None:
                break
            results.extend(part)
            # add up the length of all the tokens
            total_length = sum([r.length for r in part])
            target = target[total_length:]
        return results


class maybe(Parser):
    """Applies the given parser, but does not fail if it does not match."""

    def __init__(self, parser: Parser, id=None):
        self.parser = parser
        self.id = id

    def __call__(self, target):
        result = self.parser(target)
        # if the result is not empty and there are no errors, return the result, otherwise return a null token
        if result and not any(r.error for r in result):
            return result
        return [TokenResult(None, Null(), 0, id=self.id)]


class until(Parser):
    """
    Constructs a parser that matches everything until the given parser matches.
    STarts with a string length of 1 and increments it until the parser matches.
    """

    def __init__(self, parser: Parser, type_name: TokenOrConstructor, id=None):
        self.type_name = type_name
        self.parser = parser
        self.id = id

    def __call__(self, target):
        length = 1
        while length <= len(target):
            result = self.parser(target[length:])
            if result and not any(r.error for r in result):
                return [
                    TokenResult(
                        target[:length],
                        ensure_token(self.type_name, target[:length]),
                        length,
                        id=self.id,
                    )
                ]
            length += 1
        return [
            TokenResult(
                None,
                Null(),
                0,
                f"Expected {self.type_name}, got {target[:length]}",
                id=self.id,
            )
        ]


class extend_if_match(Parser):
    """Adds the type to the token result."""

    def __init__(self, parser: Parser, type_name: Token, id=None):
        self.parser = parser
        self.type_name = type_name
        self.id = id

    def __call__(self, target):
        result = self.parser(target)
        if result and not any(r.error for r in result):
            result.extend([TokenResult(None, self.type_name, 0, id=self.id)])
            return result
        return result


def as_identifier(parser):
    """
    If the parser matches, add a new Identifier token after
    every Constant token in the result. The Identifier token
    has the same string value as the Constant token.
    """

    def as_identifier_parser(target):
        result = parser(target)
        if result and not any(r.error for r in result):
            new_result = []
            for r in result:
                new_result.append(r)
                if isinstance(r.token, Constant):
                    # length of the new token must be given as 0 so that the substring
                    # is not double counted
                    new_result.append(TokenResult(r.value, Identifier(r.value), 0))
            return new_result
        return result

    return as_identifier_parser


class wrap(Parser):
    """Wraps the result of a parser with a token."""

    def __init__(self, parser: Parser, type_name: TokenOrConstructor, id=None):
        self.parser: Parser = parser
        self.type_name: TokenOrConstructor = type_name
        self.id = id

    def __call__(self, target) -> List[TokenResult]:
        result: List[TokenResult] = self.parser(target)
        if result and not any(r.error for r in result):
            # glue the results together
            value = "".join([r.value for r in result])
            return [
                TokenResult(
                    value, ensure_token(self.type_name, value), len(value), id=self.id
                )
            ]
        return result


COMMON_EQUIP_ABBREVIATIONS_BRICK = {
    "AHU": BRICK.Air_Handling_Unit,
    "FCU": BRICK.Fan_Coil_Unit,
    "VAV": BRICK.Variable_Air_Volume_Box,
    "CRAC": BRICK.Computer_Room_Air_Conditioner,
    "HX": BRICK.Heat_Exchanger,
    "PMP": BRICK.Pump,
    "RVAV": BRICK.Variable_Air_Volume_Box_With_Reheat,
    "HP": BRICK.Heat_Pump,
    "RTU": BRICK.Rooftop_Unit,
    "DMP": BRICK.Damper,
    "STS": BRICK.Status,
    "VLV": BRICK.Valve,
    "CHVLV": BRICK.Chilled_Water_Valve,
    "HWVLV": BRICK.Hot_Water_Valve,
    "VFD": BRICK.Variable_Frequency_Drive,
    "CT": BRICK.Cooling_Tower,
    "MAU": BRICK.Makeup_Air_Unit,
    "R": BRICK.Room,
    "A": BRICK.Air_Handling_Unit,
}

COMMON_POINT_ABBREVIATIONS = {
    "ART": BRICK.Room_Temperature_Sensor,
    "TSP": BRICK.Air_Temperature_Setpoint,
    "HSP": BRICK.Air_Temperature_Heating_Setpoint,
    "CSP": BRICK.Air_Temperature_Cooling_Setpoint,
    "SP": BRICK.Setpoint,
    "CHWST": BRICK.Leaving_Chilled_Water_Temperature_Sensor,
    "CHWRT": BRICK.Entering_Chilled_Water_Temperature_Sensor,
    "HWST": BRICK.Leaving_Hot_Water_Temperature_Sensor,
    "HWRT": BRICK.Entering_Hot_Water_Temperature_Sensor,
    "CO": BRICK.CO_Sensor,
    "CO2": BRICK.CO2_Sensor,
    "T": BRICK.Temperature_Sensor,
    "FS": BRICK.Flow_Sensor,
    "PS": BRICK.Pressure_Sensor,
    "DPS": BRICK.Differential_Pressure_Sensor,
}

COMMON_ABBREVIATIONS = abbreviations(
    {**COMMON_EQUIP_ABBREVIATIONS_BRICK, **COMMON_POINT_ABBREVIATIONS}
)


# common parser combinators
equip_abbreviations = abbreviations(COMMON_EQUIP_ABBREVIATIONS_BRICK)
point_abbreviations = abbreviations(COMMON_POINT_ABBREVIATIONS)
delimiters = regex(r"[._:/\- ]", Delimiter)
identifier = regex(r"[a-zA-Z0-9]+", Identifier)
named_equip = sequence(equip_abbreviations, maybe(delimiters), identifier)
named_point = sequence(point_abbreviations, maybe(delimiters), identifier)
