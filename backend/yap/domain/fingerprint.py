"""Fingerprints of a draft's content (REV-09): a review matches its draft as long as the
draft has the fingerprint the review stored. Changing the draft back makes it match
again."""

import hashlib
import json
from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol

LENGTH = 16  # hex characters; part of a prompt ID (REV-19), so kept short


class _Position(Protocol):
    target_pct: Decimal
    buy_threshold_pct: Decimal
    sell_threshold_pct: Decimal
    exit: bool
    rationale_md: str


def _number(value: Decimal) -> str:
    """The same number gives the same text, whatever its scale (10 and 10.00)."""
    normalized = value.normalize()
    return format(normalized, "f")


def fingerprint(title: str, thesis_md: str, positions: Iterable[tuple[str, _Position]]) -> str:
    """Hash of title, thesis and target structure (ticker and every field of each
    position, in their order)."""
    content = {
        "title": title,
        "thesis": thesis_md,
        "positions": [
            [
                ticker,
                _number(p.target_pct),
                _number(p.buy_threshold_pct),
                _number(p.sell_threshold_pct),
                bool(p.exit),
                p.rationale_md,
            ]
            for ticker, p in positions
        ],
    }
    data = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(data.encode()).hexdigest()[:LENGTH]
