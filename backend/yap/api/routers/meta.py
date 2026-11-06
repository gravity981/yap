"""Version and health (section 5.7); no login needed."""

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from yap.api.deps import DbSession
from yap.version import version_info

router = APIRouter(tags=["meta"])


class Version(BaseModel):
    version: str
    commit: str


class Health(BaseModel):
    status: str
    version: str


@router.get("/version")
def version() -> Version:
    info = version_info()
    return Version(version=info.version, commit=info.commit)


@router.get("/health")
def health(session: DbSession) -> Health:
    session.execute(text("SELECT 1"))
    return Health(status="ok", version=version_info().version)
