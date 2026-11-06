"""JSON import of theses, target structures and current structures (IMP-01 to IMP-08).

Each file goes through three checks, all reporting JSON paths (IMP-06):
  1. valid JSON,
  2. the JSON Schema of its type (IMP-04),
  3. business rules the schema cannot express (IMP-05, IMP-08).
Writes happen inside a savepoint: if anything fails, nothing is stored (IMP-06).
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from functools import cache

from jsonschema import Draft202012Validator
from pydantic import BaseModel
from sqlalchemy.orm import Session

from yap.db.models import (
    Asset,
    Investor,
    PolicyPosition,
    PolicyVersion,
    Portfolio,
    Snapshot,
    Thesis,
    ThesisRevision,
)
from yap.domain.types import HUNDRED, TARGET_SUM_TOLERANCE, AssetType
from yap.imports.models import (
    SCHEMA_MAJOR,
    UNITS_SINCE_MINOR,
    CurrentStructureFile,
    ImportFile,
    TargetStructureFile,
    ThesisFile,
)
from yap.imports.schemas import generate
from yap.messages import Message, msg
from yap.services import policies, snapshots, theses
from yap.services.assets import find_asset, normalize_ticker
from yap.services.common import Clock, ValidationError, get_owned
from yap.services.policies import PositionSpec, VersionDiff
from yap.services.snapshots import ValueSpec

_IMPORT_TYPE: dict[type[BaseModel], str] = {
    ThesisFile: "thesis",
    TargetStructureFile: "target-structure",
    CurrentStructureFile: "current-structure",
}


@cache
def _validator(import_type: str) -> Draft202012Validator:
    return Draft202012Validator(generate(import_type))


def _json_path(path: str) -> str:
    """Service paths like `positions[0].ticker` become `$.positions[0].ticker`."""
    if path.startswith("$"):
        return path
    return f"$.{path}" if path else "$"


def parse[FileT: BaseModel](text: str, model: type[FileT]) -> FileT:
    """Steps 1 and 2: JSON syntax and JSON Schema."""
    try:
        data = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as err:
        raise ValidationError.single(
            msg("invalid_json", message=err.msg, line=err.lineno, column=err.colno), "$"
        ) from None
    problems: list[tuple[str, Message]] = []
    for error in sorted(
        _validator(_IMPORT_TYPE[model]).iter_errors(data),
        key=lambda e: e.json_path,
    ):
        if error.json_path == "$.schema_version" and error.validator == "pattern":
            message = msg(
                "schema_version_unsupported", version=str(error.instance), major=SCHEMA_MAJOR
            )
        else:
            # The library's own English text, inside a translated frame
            message = msg("schema_error", detail=error.message)
        problems.append((error.json_path, message))
    if problems:
        raise ValidationError(problems)
    return model.model_validate(data)


def _check_catalog(
    session: Session, ticker: str, name: str | None, asset_type: str | None, path: str
) -> list[tuple[str, Message]]:
    """IMP-08: unknown tickers need name and type; known ones must keep their type."""
    asset = find_asset(session, ticker)
    if asset is None:
        if not name or asset_type is None:
            unknown = normalize_ticker(ticker)
            return [(f"{path}.ticker", msg("import_ticker_unknown", ticker=unknown))]
        return []
    if asset_type is not None and asset.type != asset_type:
        mismatch = msg(
            "asset_type_mismatch", ticker=asset.ticker, catalog_type=asset.type, type=asset_type
        )
        return [(f"{path}.type", mismatch)]
    return []


def _duplicate_tickers(tickers: list[str]) -> list[tuple[str, Message]]:
    seen: set[str] = set()
    problems = []
    for i, ticker in enumerate(tickers):
        normalized = normalize_ticker(ticker)
        if normalized in seen:
            problems.append(
                (f"$.positions[{i}].ticker", msg("ticker_duplicate", ticker=normalized))
            )
        seen.add(normalized)
    return problems


def check_target_structure(session: Session, file: TargetStructureFile) -> None:
    """IMP-05: sum 100 %, unique tickers, at most one cash buffer, catalog consistency."""
    problems = _duplicate_tickers([p.ticker for p in file.positions])
    total = sum((p.target_pct for p in file.positions), Decimal(0))
    if abs(total - HUNDRED) > TARGET_SUM_TOLERANCE:
        problems.append(("$.positions", msg("import_target_sum", sum=str(total))))
    if sum(1 for p in file.positions if p.type == AssetType.CASH_BUFFER.value) > 1:
        problems.append(("$.positions", msg("one_cash_buffer")))
    for i, p in enumerate(file.positions):
        problems += _check_catalog(session, p.ticker, p.name, p.type, f"$.positions[{i}]")
    if problems:
        raise ValidationError(problems)


def check_current_structure(session: Session, file: CurrentStructureFile) -> None:
    problems = _duplicate_tickers([p.ticker for p in file.positions])
    for i, p in enumerate(file.positions):
        problems += _check_catalog(session, p.ticker, p.name, p.type, f"$.positions[{i}]")
        if p.units is None and p.value is None:
            problems.append((f"$.positions[{i}]", msg("position_units_or_value")))
    if problems:
        raise ValidationError(problems)


def _with_units(file: ImportFile) -> bool:
    """IMP-03: from 1.3 on every position has units; older files have only values."""
    return int(file.schema_version.split(".")[1]) >= UNITS_SINCE_MINOR


def _atomically[ResultT](session: Session, action: Callable[[], ResultT]) -> ResultT:
    """Runs `action` in a savepoint; on any error nothing of it is stored (IMP-06)."""
    savepoint = session.begin_nested()
    try:
        result = action()
    except ValidationError as err:
        savepoint.rollback()
        raise ValidationError([(_json_path(p), m) for p, m in err.problems]) from None
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    return result


def import_thesis(
    session: Session,
    actor: Investor,
    clock: Clock,
    text: str,
    selected_thesis_id: int | None = None,
) -> ThesisRevision:
    """IMP-01: the draft of the selected thesis (created if there is none), otherwise a
    new thesis. Never activates a revision."""
    file = parse(text, ThesisFile)

    def run() -> ThesisRevision:
        if selected_thesis_id is not None:
            thesis = get_owned(session, Thesis, selected_thesis_id, actor)
            if theses.get_draft(thesis) is None:
                theses.create_draft(session, actor, clock, selected_thesis_id)
            return theses.update_draft(
                session,
                actor,
                clock,
                selected_thesis_id,
                title=file.title,
                content_md=file.content_md,
                status=file.status,
                change_note=file.change_note,
            )
        thesis = theses.create_thesis(
            session,
            actor,
            clock,
            title=file.title,
            content_md=file.content_md,
            visibility=file.visibility,
            status=file.status,
        )
        return thesis.revisions[0]

    return _atomically(session, run)


def _position_specs(file: TargetStructureFile) -> list[PositionSpec]:
    return [
        PositionSpec(
            ticker=p.ticker,
            name=p.name,
            type=p.type,
            target_pct=p.target_pct,
            buy_threshold_pct=p.buy_threshold_pct,
            sell_threshold_pct=p.sell_threshold_pct,
            exit=p.exit,
            rationale_md=p.rationale_md,
        )
        for p in file.positions
    ]


def import_target_structure(
    session: Session, actor: Investor, clock: Clock, text: str, policy_id: int
) -> PolicyVersion:
    """IMP-02: into the selected policy's draft (created if missing, replaced otherwise)."""
    file = parse(text, TargetStructureFile)

    def run() -> PolicyVersion:
        policy = policies.get_policy(session, actor, policy_id)
        check_target_structure(session, file)
        if policies.get_draft(policy) is None:
            policies.create_draft(session, actor, clock, policy.id)
        return policies.update_draft(
            session,
            actor,
            clock,
            policy.id,
            positions=_position_specs(file),
        )

    return _atomically(session, run)


def import_current_structure(
    session: Session, actor: Investor, clock: Clock, text: str, portfolio_id: int
) -> Snapshot:
    """IMP-03: a snapshot of the selected portfolio, same rules as manual entry."""
    file = parse(text, CurrentStructureFile)

    def run() -> Snapshot:
        check_current_structure(session, file)
        return snapshots.create_snapshot(
            session,
            actor,
            clock,
            portfolio_id,
            [
                ValueSpec(p.ticker, p.value, p.name, p.type, p.units, p.price)
                for p in file.positions
            ],
            source="import",
            path="positions",
            require_units=_with_units(file),
        )

    return _atomically(session, run)


# --- Preview (IMP-07) ---------------------------------------------------------


@dataclass(frozen=True)
class ThesisPreview:
    creates_new_thesis: bool
    revision_no: int
    title: str
    status: str
    visibility: str | None  # None: unchanged (revision of an existing thesis)


def preview_thesis(
    session: Session, actor: Investor, text: str, selected_thesis_id: int | None = None
) -> ThesisPreview:
    file = parse(text, ThesisFile)
    if selected_thesis_id is None:
        return ThesisPreview(True, 1, file.title, file.status, file.visibility)
    thesis = get_owned(session, Thesis, selected_thesis_id, actor)
    draft = theses.get_draft(thesis)
    revision_no = draft.revision_no if draft else theses.latest_revision(thesis).revision_no + 1
    return ThesisPreview(False, revision_no, file.title, file.status, None)


def preview_target_structure(
    session: Session, actor: Investor, text: str, policy_id: int
) -> VersionDiff:
    """Difference between the file and the policy's latest version, nothing is stored."""
    file = parse(text, TargetStructureFile)
    policy = policies.get_policy(session, actor, policy_id)
    check_target_structure(session, file)
    latest = policy.versions[-1]
    candidate = PolicyVersion(thesis_revision_id=latest.thesis_revision_id)
    candidate.thesis_revision = latest.thesis_revision
    for i, p in enumerate(file.positions):
        asset = find_asset(session, p.ticker) or Asset(
            ticker=normalize_ticker(p.ticker), name=p.name, type=p.type
        )
        position = PolicyPosition(
            target_pct=p.target_pct,
            buy_threshold_pct=p.buy_threshold_pct,
            sell_threshold_pct=p.sell_threshold_pct,
            exit=p.exit,
            rationale_md=p.rationale_md,
            sort_order=i,
        )
        position.asset = asset
        candidate.positions.append(position)
    return policies.compare_versions(latest, candidate)


@dataclass(frozen=True)
class CurrentStructurePreview:
    values: list[tuple[str, Decimal | None]]  # value, if the file gives one
    new_tickers: list[str]


def preview_current_structure(
    session: Session, actor: Investor, text: str, portfolio_id: int
) -> CurrentStructurePreview:
    file = parse(text, CurrentStructureFile)
    get_owned(session, Portfolio, portfolio_id, actor)
    check_current_structure(session, file)
    return CurrentStructurePreview(
        values=[(normalize_ticker(p.ticker), p.value) for p in file.positions],
        new_tickers=[
            normalize_ticker(p.ticker)
            for p in file.positions
            if find_asset(session, p.ticker) is None
        ],
    )
