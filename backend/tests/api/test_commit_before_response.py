"""A change is committed before its response is sent, so a client acting on the response
at once (e.g. reloading after a password change) sees the new state (NFR-05)."""

import json
import sqlite3
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from tests.fixtures import PASSWORD, Accounts


@pytest.mark.req("NFR-05", "USR-02")
def test_change_is_committed_when_the_response_starts(
    app: Any, db_url: str, accounts_api: Accounts
) -> None:
    accounts_api.create("alice")
    with TestClient(app, base_url="https://testserver") as client:
        login = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
        cookie = login.headers["set-cookie"].split(";")[0]
        body = json.dumps(
            {"current_password": PASSWORD, "new_password": "another password 42"}
        ).encode()
        seen: list[str] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                # What a second client would read the moment the response arrives
                with sqlite3.connect(db_url.removeprefix("sqlite:///")) as db:
                    stored = db.execute(
                        "SELECT password_hash FROM investor WHERE username = 'alice'"
                    ).fetchone()[0]
                seen.append(stored)

        before = (
            sqlite3.connect(db_url.removeprefix("sqlite:///"))
            .execute("SELECT password_hash FROM investor WHERE username = 'alice'")
            .fetchone()[0]
        )
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/api/auth/password",
            "raw_path": b"/api/auth/password",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"testserver"),
                (b"content-type", b"application/json"),
                (b"cookie", cookie.encode()),
            ],
            "client": ("127.0.0.1", 1),
            "server": ("testserver", 443),
            "state": {},
        }
        anyio.run(app, scope, receive, send)
    assert len(seen) == 1
    assert seen[0] != before  # the new password was already stored
