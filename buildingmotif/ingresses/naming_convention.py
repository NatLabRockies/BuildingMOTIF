from functools import cached_property
from typing import List

from buildingmotif.ingresses.base import Record, RecordIngressHandler
from buildingmotif.label_parsing import (
    Parser,
    analyze_failures,
    parse_list,
    results_to_tokens,
)


class NamingConventionIngress(RecordIngressHandler):
    """
    Ingress handler that parses labels using a naming convention parser.
    This returns a Record for each input label, with the parsed tokens as a field.
    You will need to attach this to a GraphIngressHandler to turn the tokens into a graph.
    """

    def __init__(
        self,
        upstream: RecordIngressHandler,
        naming_convention: Parser,
    ):
        """
        Create a new NamingConventionIngress.

        :param upstream: The upstream ingress handler to get records from. This should return records with a "label" field.
        :type upstream: RecordIngressHandler
        :param naming_convention: The naming convention parser to use.
        :type naming_convention: Parser
        """
        self.upstream = upstream
        self.naming_convention = naming_convention

    def dump_failed_labels(self):
        for group, failures in self.sorted_failures:
            print(f"Unparsed label: {group} ({len(failures)} failures)")
            for failure in failures:
                print(f"\t{failure}")
            print()

    @property
    def sorted_failures(self) -> list:
        return sorted(
            analyze_failures(self.failures).items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

    @cached_property
    def records(self) -> List[Record]:
        results, failures = parse_list(
            self.naming_convention, [x.fields["label"] for x in self.upstream.records]
        )
        self.failures = failures
        self.results = results
        tokens = results_to_tokens(results)
        return [
            Record(
                rtype="token",
                fields={
                    "label": t["label"],
                    "tokens": t["tokens"],
                },
            )
            for t in tokens
        ]
