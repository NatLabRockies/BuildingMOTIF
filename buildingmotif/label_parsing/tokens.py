from abc import ABC
from dataclasses import dataclass
from typing import Any, Optional, Type, Union

from rdflib import URIRef


@dataclass(frozen=True)
class Token(ABC):
    value: Any


# Token is a union of the different types of tokens
TokenOrConstructor = Union[Token, Type[Token]]


def ensure_token(token_or_constructor: TokenOrConstructor, value):
    """Ensure a value is a token or constructs one from a given value."""
    if isinstance(token_or_constructor, type):
        return token_or_constructor(value)
    return token_or_constructor


@dataclass(frozen=True)
class Identifier(Token):
    """An identifier token. Contains a string."""

    value: str


@dataclass(frozen=True)
class Constant(Token):
    """A constant token. Contains a URI, probably some sort of Class"""

    value: URIRef


@dataclass(frozen=True)
class Delimiter(Token):
    """A delimiter token."""

    value: str


@dataclass(frozen=True)
class Null(Token):
    """A null token."""

    value: None = None


@dataclass(frozen=True)
class TokenResult:
    """A token result. Contains a token, the type of the token, the length of the token, and a possible error."""

    value: Optional[str]
    token: Token
    length: int
    error: Optional[str] = None
    id: Optional[str] = None
    slot: Optional[str] = None

    def __eq__(self, other):
        """
        Compare two token results on every
        field except for the error field.
        """
        if not isinstance(other, TokenResult):
            return False
        return (
            self.value == other.value
            and self.token == other.token
            and self.length == other.length
        )


# null token result
ErrorTokenResult = TokenResult(None, Null(), 0, None)
