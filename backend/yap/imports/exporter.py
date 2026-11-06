"""Export in the import formats, so an export can be imported again (IMP-10)."""

import json
from decimal import Decimal
from typing import Any

from yap.db.models import PolicyVersion, Snapshot, ThesisRevision
from yap.imports.importer import parse
from yap.imports.models import (
    SCHEMA_MAJOR,
    SCHEMA_VERSION,
    UNITS_SINCE_MINOR,
    CurrentStructureFile,
    TargetStructureFile,
    ThesisFile,
)
from yap.imports.schemas import schema_filename


def dumps(data: Any) -> str:
    """JSON with decimals written as plain numbers, exactly as stored (NFR-04).

    The json module can only write numbers via float, so decimals are replaced by
    unique placeholders first and the placeholders by the decimal text afterwards.
    """
    numbers: list[str] = []

    def mark(value: Any) -> Any:
        if isinstance(value, Decimal):
            numbers.append(format(value.normalize(), "f"))
            return f"\x00decimal{len(numbers) - 1}\x00"
        if isinstance(value, dict):
            return {k: mark(v) for k, v in value.items()}
        if isinstance(value, list):
            return [mark(v) for v in value]
        return value

    text = json.dumps(mark(data), indent=2, ensure_ascii=False)
    for i, number in enumerate(numbers):
        text = text.replace(f'"\\u0000decimal{i}\\u0000"', number)
    return text + "\n"


def thesis(revision: ThesisRevision) -> str:
    data = {
        "$schema": schema_filename("thesis"),
        "schema_version": SCHEMA_VERSION,
        "title": revision.title,
        "visibility": revision.thesis.visibility,
        "status": revision.status,
        "content_md": revision.content_md,
        "change_note": revision.change_note,
    }
    return _checked(data, ThesisFile)


def target_structure(version: PolicyVersion) -> str:
    data = {
        "$schema": schema_filename("target-structure"),
        "schema_version": SCHEMA_VERSION,
        "positions": [
            {
                "ticker": p.asset.ticker,
                "name": p.asset.name,
                "type": p.asset.type,
                "target_pct": p.target_pct,
                "buy_threshold_pct": p.buy_threshold_pct,
                "sell_threshold_pct": p.sell_threshold_pct,
                "exit": p.exit,
                "rationale_md": p.rationale_md,
            }
            for p in version.positions
        ],
    }
    return _checked(data, TargetStructureFile)


def current_structure(snapshot: Snapshot) -> str:
    # A snapshot with rows from before price tracking (CMP-10) is written in the last
    # version without units, which imports positions with only a value (IMP-03)
    without_units = any(v.units is None for v in snapshot.values)
    data = {
        "$schema": schema_filename("current-structure"),
        "schema_version": (
            f"{SCHEMA_MAJOR}.{UNITS_SINCE_MINOR - 1}" if without_units else SCHEMA_VERSION
        ),
        "positions": [
            {
                "ticker": v.asset.ticker,
                # Rows from before price tracking have only a value (CMP-10)
                **({"units": v.units} if v.units is not None else {}),
                **({"price": v.price} if v.price is not None else {}),
                "value": v.value,
                "name": v.asset.name,
                "type": v.asset.type,
            }
            for v in snapshot.values
        ],
    }
    return _checked(data, CurrentStructureFile)


def _checked(data: dict[str, Any], model: type[Any]) -> str:
    """Every export passes the import's schema check, so it can be imported again."""
    if data.get("change_note") is None:
        data.pop("change_note", None)
    text = dumps(data)
    parse(text, model)
    return text
