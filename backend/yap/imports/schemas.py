"""JSON Schemas for the import files (IMP-04, IMP-09).

Generated from the models in `models.py` and committed to schemas. CI checks
that the committed files equal the generated ones (schema drift check).

    python -m yap.imports.schemas          # write schemas
    python -m yap.imports.schemas --check  # exit 1 on drift
"""

import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from yap.imports.models import (
    SCHEMA_MAJOR,
    CurrentStructureFile,
    TargetStructureFile,
    ThesisFile,
)

SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"
REGENERATE = "python -m yap.imports.schemas"
DIALECT = "https://json-schema.org/draft/2020-12/schema"

IMPORT_TYPES: dict[str, type[BaseModel]] = {
    "thesis": ThesisFile,
    "target-structure": TargetStructureFile,
    "current-structure": CurrentStructureFile,
}


def schema_filename(import_type: str) -> str:
    return f"{import_type}.v{SCHEMA_MAJOR}.schema.json"


def generate(import_type: str) -> dict[str, Any]:
    schema = IMPORT_TYPES[import_type].model_json_schema(by_alias=True)
    return {"$schema": DIALECT, "$id": schema_filename(import_type), **schema}


def render(import_type: str) -> str:
    return json.dumps(generate(import_type), indent=2) + "\n"


def drifted(directory: Path = SCHEMAS_DIR) -> list[str]:
    """Import types whose committed schema differs from the generated one."""
    return [
        t
        for t in IMPORT_TYPES
        if not (directory / schema_filename(t)).exists()
        or (directory / schema_filename(t)).read_text() != render(t)
    ]


def write(directory: Path = SCHEMAS_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for import_type in IMPORT_TYPES:
        (directory / schema_filename(import_type)).write_text(render(import_type))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if "--check" in args:
        stale = drifted()
        for t in stale:
            print(f"{schema_filename(t)} is out of date; regenerate with: {REGENERATE}")
        return 1 if stale else 0
    write()
    return 0


if __name__ == "__main__":
    sys.exit(main())
