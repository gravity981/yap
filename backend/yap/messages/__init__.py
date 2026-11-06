"""Messages shown to users, each with a stable code (NFR-10).

A message is a code with parameters; its English template is in the catalog of its group
(general, accounts, investments, reviews, prices). The API sends the code and the parameters next to
the English text, so the frontend shows the message in the user's language. The catalog is
exported to frontend/src/api/messages.json (npm run gen:api), where the German texts are
checked against it.
"""

import string
from dataclasses import dataclass, field

from yap.messages import accounts, general, investments, prices, reviews

Param = str | int | float


def _merge(*groups: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for group in groups:
        for code, template in group.items():
            if code in merged:
                raise ValueError(f"Message code {code} is defined twice")
            merged[code] = template
    return merged


CATALOG: dict[str, str] = _merge(
    general.MESSAGES, accounts.MESSAGES, investments.MESSAGES, reviews.MESSAGES, prices.MESSAGES
)


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


@dataclass(frozen=True)
class Message:
    """A user-visible message: its code and the values of its placeholders."""

    code: str
    params: dict[str, Param] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.code not in CATALOG:
            raise ValueError(f"Unknown message code {self.code}")
        missing = placeholders(CATALOG[self.code]) - set(self.params)
        if missing:
            raise ValueError(f"Message {self.code} needs {', '.join(sorted(missing))}")

    def __str__(self) -> str:
        """The English text."""
        return CATALOG[self.code].format(**self.params)


def msg(code: str, **params: Param) -> Message:
    return Message(code, params)
