"""Committed JSON Schemas (IMP-04, IMP-09)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from yap.imports import schemas


@pytest.mark.req("IMP-09")
def test_committed_schemas_match_the_models() -> None:
    """Schema drift check: regenerate with `python -m yap.imports.schemas`."""
    assert schemas.drifted() == []


@pytest.mark.req("IMP-04")
@pytest.mark.parametrize("import_type", list(schemas.IMPORT_TYPES))
def test_schemas_are_valid_draft_2020_12(import_type: str) -> None:
    schema = json.loads((schemas.SCHEMAS_DIR / schemas.schema_filename(import_type)).read_text())
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)


@pytest.mark.req("IMP-09")
def test_write_and_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert sorted(schemas.drifted(tmp_path)) == sorted(schemas.IMPORT_TYPES)
    schemas.write(tmp_path)
    assert schemas.drifted(tmp_path) == []
    (tmp_path / schemas.schema_filename("thesis")).write_text("{}")
    assert schemas.drifted(tmp_path) == ["thesis"]
    assert schemas.main(["--check"]) == 0


@pytest.mark.req("IMP-09")
def test_check_reports_drift(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(schemas, "SCHEMAS_DIR", tmp_path)
    monkeypatch.setattr(schemas.drifted, "__defaults__", (tmp_path,))
    monkeypatch.setattr(schemas.write, "__defaults__", (tmp_path,))
    assert schemas.main(["--check"]) == 1
    assert schemas.main([]) == 0
    assert schemas.main(["--check"]) == 0
