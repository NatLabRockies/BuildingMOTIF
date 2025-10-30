from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from inspect import Parameter, signature
from typing import Dict, List, Tuple

from buildingmotif.label_parsing.tokens import Constant, Identifier, Null, TokenResult

# TODO: programming by example?
# TODO: get LLM to write a parser for the point labels, given a human description


# type definition for the output of a parser function
@dataclass(frozen=True)
class ParseResult:
    tokens: List[TokenResult]
    success: bool
    _errors: List[str] = field(default_factory=list)

    @property
    def errors(self):
        """Return a list of errors and the offset into the string
        where the error occurred."""
        errors = []
        offset = 0
        for t in self.tokens:
            if t.error:
                errors.append((t.error, offset))
            offset += t.length
        return errors


# type definition for the parser functions.
# A parser function takes a string and returns a list of tuples
# each tuple is a token, the type of the token, and the length of the token
# the length of the token is used to keep track of how much of the string
# has been parsed
class Parser(ABC):
    __args__: dict

    def __new__(mcls, *args, **kwargs):
        """When a parser is constructed, save its arguments into a dictionary __args__.
        This allows parsers to be serialized later without requiring bespoke (de)serialization code
        for every parser type."""
        cls = super().__new__(mcls)
        sig = signature(mcls.__init__)
        parameters = sig.parameters
        arguments = sig.bind(cls, *args, **kwargs).arguments

        cls.__args__ = {}
        for name, value in arguments.items():
            if name != "self":
                kind = parameters[name].kind
                if kind in [
                    Parameter.POSITIONAL_ONLY,
                    Parameter.POSITIONAL_OR_KEYWORD,
                    Parameter.KEYWORD_ONLY,
                ]:
                    cls.__args__[name] = value
                elif kind == Parameter.VAR_POSITIONAL:
                    cls.__args__[name] = list(value)
                elif kind == Parameter.VAR_KEYWORD:
                    cls.__args__.update(value)

        return cls

    @abstractmethod
    def __call__(self, target: str) -> List[TokenResult]:
        pass


# function which takes the results of parse_list and turns all of the
# results (not failures) into token dictionaries.
# A token dictionary has an 'identifier' key which is the label (the keys
# of the results dictionary), and then a list of tokens. A token is a dictionary
# with 'identifier' (the substring part of the result) and 'type' (the type of
# the result if it is a constant)
def results_to_tokens(results):
    tokens = []
    for r in results:
        res = {"label": r, "tokens": []}
        parts = iter(results[r])
        first = None
        while True:
            try:
                # get first constant or identifier token using itertools
                first = first_true(
                    parts, pred=lambda x: isinstance(x.token, (Constant, Identifier))
                )
                # get the next constant or identifier token
                second = first_true(
                    parts, pred=lambda x: isinstance(x.token, (Constant, Identifier))
                )
                if not first or not second:
                    break
                # add the constant and identifier to the token dictionary
                identifier = first if isinstance(first.token, Identifier) else second
                constant = first if isinstance(first.token, Constant) else second
                res["tokens"].append(
                    {
                        "identifier": identifier.token.value,
                        "type": constant.token.value.toPython(),
                    }
                )
            except StopIteration:
                break
        if first is None:
            # if there are any constants left, add them to the token dictionary with the label
            first = first_true(parts, pred=lambda x: isinstance(x.token, Constant))
        # need to check this is a Constant because during the while True loop, the first
        # token could be an Identifier
        if first and isinstance(first.token, Constant):
            res["tokens"].append(
                {"identifier": r, "type": first.token.value.toPython()}
            )
        tokens.append(res)

    return tokens


# Analyzes the failures of a parser to capture all point labels.
# For each label in the failures, compute the length of the found tokens.
# Create a dictionary keyed with the label. The value should have two keys.
# The first key is the remaining "unparsed" part of the string, the second key
# is the set of tokens that were found.
def analyze_failures(failures: Dict[str, List[TokenResult]]):
    """Analyze the failures of a parser."""
    analyzed = {}
    for failure in failures:
        tokens = failures[failure]
        length = sum([t.length for t in tokens])
        analyzed[failure] = {
            "unparsed": failure[length:],
            "tokens": [
                {"identifier": t.token.value, "type": t.token.value} for t in tokens
            ],
        }
    # group the points by the unparsed portion
    grouped = defaultdict(list)
    for f in analyzed:
        grouped[analyzed[f]["unparsed"]].append(f)
    # for each group, add the tokens to the first point in the group
    return grouped


# wrapper function for reading a list of strings
# applies a given parser to each string in the list
# returns a dictionary of the input strings to the result of the parser
# Keep track of all strings that fail to parse and return them in a list
def parse_list(
    parser, target_list
) -> Tuple[Dict[str, List[TokenResult]], Dict[str, List[TokenResult]]]:
    """
    Parse a list of strings using the given parser.

    :param parser: the parsing combinator function
    :type parser: Parser
    :param target_list: the list of strings to parse
    :type target_list: List[str]
    :return: a tuple of the results and failures
    """
    results = {}
    failed = {}
    for target in target_list:
        result = parse(parser, target)
        if result.success:
            results[target] = result.tokens
        else:
            failed[target] = result.tokens
    return results, failed


# wrapper function for a parser that does the following:
# - apply the parser to the target
# - if the parser does not consume all the target, raise an error
# - return the result of the parser
def parse(parser: Parser, target: str) -> ParseResult:
    """
    Parse the given target string using the given parser.

    :param parser: the parsing combinator function
    :type parser: Parser
    :param target: the target string to parse
    :type target: str
    :return: the result of the parser
    :rtype: ParseResult
    """
    result = parser(target)
    # remove empty Null tokens from result
    result = [r for r in result if r.error or (not isinstance(r.token, Null))]
    # check length of target vs length of all results
    total_length = sum([r.length for r in result])
    return ParseResult(
        result, total_length == len(target), [r.error for r in result if r.error]
    )


# from itertools documentation
def first_true(iterable, default=None, pred=None):
    """Returns the first true value in the iterable.

    If no true value is found, returns *default*

    If *pred* is not None, returns the first item
    for which pred(item) is true.

    """
    # first_true([a,b,c], x) --> a or b or c or x
    # first_true([a,b], x, f) --> a if f(a) else b if f(b) else x
    return next(filter(pred, iterable), default)
