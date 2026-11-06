"""App session/CSRF adapter; browser callers never receive the service Bearer."""
import os

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from tools.navigation_references import catalog_summary, load_catalog
from tools.navigation_readiness import Scenario
from .. import navigation_service
from ..operation_uploads import reference_path
from ..errors import ApiError, require
from ..web import security


class ScreenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ship: str = Field(min_length=1, max_length=80)
    port_id: str = Field(pattern=r"^WPI:[0-9]+$")
    berth_id: str | None = Field(default=None, pattern=r"^WPI:[0-9]+:BERTH:[0-9A-Z-]+$")
    scenario: Scenario | None = None


def actor_unchanged(ctx):
    current = security.current_user(ctx.db, ctx.request, ctx.guest)
    require(current["id"] == ctx.user["id"] and current["role"] in ("admin", "operator", "viewer")
            and not current.get("must_change_password"),
            "사용자 상태가 바뀌었습니다. 다시 로그인해 주세요.", "AUTH_REQUIRED", 401)


def unavailable(exc):
    return navigation_service.unavailable(exc)


def catalog(ctx):
    try:
        data, sha256 = load_catalog(reference_path())
        result = catalog_summary(data, sha256)
        actor_unchanged(ctx)
        return result
    except HTTPException as exc:
        raise unavailable(exc) from None


def screen(ctx):
    try:
        request = ScreenRequest.model_validate(ctx.body)
        require(not request.berth_id or request.berth_id.startswith(request.port_id + ":BERTH:"),
                "선석이 선택한 항구에 속하지 않습니다.")
    except ValidationError:
        raise ApiError(400, "INVALID_INPUT", "앱 선박·항구·선석 입력을 확인해 주세요.") from None
    reply = navigation_service.compare_ship(ctx.db, request.ship, port_ids=[request.port_id], berth_id=request.berth_id,
        **({"scenario":request.scenario} if request.scenario is not None else {}))
    actor_unchanged(ctx)
    results = reply.pop("results")
    return {**reply, "result": results[0] if results else None}


GET = {"operations/port-references": catalog}
POST = {"operations/port-reference-screen": screen}
