"""Maps service errors to HTTP responses.

Every error body has `detail` (English), and `code` with `params` so the frontend can show
it in the user's language (NFR-10). Validation errors also have `problems` with a path
and message each (IMP-06), again with code and params.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from yap.messages import Message
from yap.services.accounts import AuthenticationError, LockedError
from yap.services.common import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
    ValidationError,
)

STATUS: list[tuple[type[ServiceError], int]] = [
    (AuthenticationError, 401),
    (LockedError, 429),
    (ForbiddenError, 403),
    (NotFoundError, 404),
    (ConflictError, 409),
    (ValidationError, 422),
]


async def _service_error(request: Request, exc: Exception) -> JSONResponse:
    status = next((code for cls, code in STATUS if isinstance(exc, cls)), 400)
    message: Message | None = getattr(exc, "message", None)
    body: dict[str, object] = {
        "detail": str(exc),
        "code": message.code if message else None,
        "params": message.params if message else {},
    }
    if isinstance(exc, ValidationError):
        body["problems"] = [
            {"path": p, "message": str(m), "code": m.code, "params": m.params}
            for p, m in exc.problems
        ]
    headers = {}
    if isinstance(exc, LockedError):
        retry = max(1, int((exc.until - request.app.state.clock.now()).total_seconds()))
        headers["Retry-After"] = str(retry)
    return JSONResponse(body, status_code=status, headers=headers)


def register(app: FastAPI) -> None:
    app.add_exception_handler(ServiceError, _service_error)
