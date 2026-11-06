"""Messages with codes (NFR-10): the catalog, and how the API sends them."""

import re
import string

import pytest

from tests.fixtures import Accounts
from yap.messages import CATALOG, Message, msg, placeholders


def test_codes_are_snake_case_and_templates_valid() -> None:
    for code, template in CATALOG.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code
        list(string.Formatter().parse(template))  # raises on broken braces
        assert template.strip() == template and template, code


def test_a_message_needs_a_known_code_and_all_its_values() -> None:
    assert str(msg("thesis_not_found", id=7)) == "Thesis 7 not found"
    with pytest.raises(ValueError, match="Unknown message code"):
        msg("no_such_code")
    with pytest.raises(ValueError, match="needs id"):
        msg("thesis_not_found")
    assert placeholders(CATALOG["thesis_not_found"]) == {"id"}
    assert Message("not_logged_in").params == {}


@pytest.mark.req("NFR-10")
def test_errors_carry_code_and_params_next_to_the_english_text(
    client, accounts_api: Accounts
) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not logged in", "code": "not_logged_in", "params": {}}
    accounts_api.create("alice")
    alice = accounts_api.client("alice")
    missing = alice.get("/api/theses/999")
    assert missing.json() == {
        "detail": "Thesis 999 not found",
        "code": "thesis_not_found",
        "params": {"id": 999},
    }
