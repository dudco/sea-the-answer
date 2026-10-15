"""Route table for /api/{path}. Each domain module declares GET / POST (exact paths) and GET_PREFIX.

Handlers take a RequestContext and return a JSON-serializable value or a Response.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Request, Response

from ..errors import ApiError


@dataclass
class RequestContext:
    db: Any
    user: dict
    guest: dict
    path: str
    method: str
    body: dict
    request: Request
    response: Response


Handler = Callable[[RequestContext], Any]

from . import admin, auth, changes, documents, operations, reports, skills, system  # noqa: E402

GET: dict[str, Handler] = {}
POST: dict[str, Handler] = {}
GET_PREFIX: list[tuple[str, Handler]] = []
for _module in (system, auth, documents, operations, changes, reports, admin, skills):
    for _table, _routes in ((GET, getattr(_module, "GET", {})), (POST, getattr(_module, "POST", {}))):
        _duplicate = _table.keys() & _routes.keys()
        assert not _duplicate, f"duplicate route {_duplicate} in {_module.__name__}"
        _table.update(_routes)
    GET_PREFIX.extend(getattr(_module, "GET_PREFIX", ()))


def dispatch(ctx: RequestContext):
    handler = (GET if ctx.method == "GET" else POST).get(ctx.path)
    if handler is None and ctx.method == "GET":
        handler = next((h for prefix, h in GET_PREFIX if ctx.path.startswith(prefix)), None)
    if handler is None:
        raise ApiError(404, "NOT_FOUND", "API 경로를 찾을 수 없습니다.")
    return handler(ctx)
