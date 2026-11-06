"""Shared asset catalog and import schemas (IMP-09)."""

import re
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import select

from yap.api.deps import CurrentUser, DbSession
from yap.api.schemas import AssetOut
from yap.db.models import Asset
from yap.imports import exporter
from yap.imports.schemas import IMPORT_TYPES, generate
from yap.messages import msg
from yap.services import policies, snapshots, theses
from yap.services.common import NotFoundError, require_investor

router = APIRouter(tags=["catalog"])


@router.get("/assets")
def list_assets(session: DbSession, user: CurrentUser) -> list[AssetOut]:
    require_investor(user)
    return [AssetOut.of(a) for a in session.scalars(select(Asset).order_by(Asset.ticker))]


@router.get("/schemas/{import_type}")
def get_schema(import_type: str, user: CurrentUser) -> dict[str, Any]:
    """IMP-09: the JSON Schema of an import type, for download."""
    if import_type not in IMPORT_TYPES:
        raise NotFoundError(msg("schema_not_found", type=import_type))
    return generate(import_type)


# --- Export (IMP-10) ------------------------------------------------------------


def _download(text: str, filename: str) -> Response:
    # policy names are user input: keep the header value plain
    filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
    return Response(
        text,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/theses/{thesis_id}/revisions/{revision_no}/export")
def export_thesis(
    thesis_id: int, revision_no: int, session: DbSession, user: CurrentUser
) -> Response:
    thesis = theses.get_readable_thesis(session, user, thesis_id)
    revision = next(
        (
            r
            for r in theses.readable_revisions(session, user, thesis)
            if r.revision_no == revision_no
        ),
        None,
    )
    if revision is None:
        raise NotFoundError(msg("thesis_revision_no_not_found", number=revision_no, id=thesis_id))
    return _download(exporter.thesis(revision), f"thesis-{thesis_id}-r{revision_no}.json")


@router.get("/policies/{policy_id}/versions/{version_no}/export")
def export_target_structure(
    policy_id: int, version_no: int, session: DbSession, user: CurrentUser
) -> Response:
    policy = policies.get_policy(session, user, policy_id)
    version = next((v for v in policy.versions if v.version_no == version_no), None)
    if version is None:
        raise NotFoundError(msg("policy_version_no_not_found", number=version_no, name=policy.name))
    return _download(exporter.target_structure(version), f"{version.label}.json")


@router.get("/snapshots/{snapshot_id}/export")
def export_current_structure(snapshot_id: int, session: DbSession, user: CurrentUser) -> Response:
    snapshot = snapshots.get_snapshot(session, user, snapshot_id)
    return _download(exporter.current_structure(snapshot), f"snapshot-{snapshot_id}.json")
