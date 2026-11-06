"""Deletes images built from main that are older than 30 days (spec 5.3).

Only versions whose tags are all build tags (`X.Y.Z_build.N`) are deleted. Images tagged
`main`, release candidates, releases and untagged versions are kept.

    GITHUB_TOKEN=... python scripts/cleanup_images.py [--dry-run]
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

PACKAGE = "https://api.github.com/users/gravity981/packages/container/yap"
KEEP_FOR = timedelta(days=30)
BUILD_TAG = re.compile(r"^\d+\.\d+\.\d+_build\.\d+$")


def expired(versions: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """The package versions to delete."""
    result = []
    for version in versions:
        tags = version["metadata"]["container"]["tags"]
        created = datetime.fromisoformat(version["created_at"].replace("Z", "+00:00"))
        if tags and all(BUILD_TAG.match(t) for t in tags) and now - created > KEEP_FOR:
            result.append(version)
    return result


def _request(url: str, token: str, method: str = "GET") -> Any:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def _versions(token: str) -> list[dict[str, Any]]:
    versions: list[dict[str, Any]] = []
    page = 1
    while batch := _request(f"{PACKAGE}/versions?per_page=100&page={page}", token):
        versions.extend(batch)
        page += 1
    return versions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="only list what would go")
    args = parser.parse_args(argv)
    token = os.environ["GITHUB_TOKEN"]
    for version in expired(_versions(token), datetime.now(UTC)):
        tags = ", ".join(version["metadata"]["container"]["tags"])
        print(f"{'Would delete' if args.dry_run else 'Deleting'} {tags} ({version['created_at']})")
        if not args.dry_run:
            _request(f"{PACKAGE}/versions/{version['id']}", token, method="DELETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
