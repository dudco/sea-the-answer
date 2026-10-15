"""Skill workflows stay behind the ordinary app security and transaction boundary."""

from .. import workflow_skills
from ..errors import require
from ..web import security


def catalog(_ctx):
    return workflow_skills.catalog()


def run(ctx):
    answer = workflow_skills.run(ctx.db, ctx.user, ctx.body)
    require(
        security.current_user(ctx.db, ctx.request, ctx.guest)["id"] == ctx.user["id"],
        "사용자 상태가 바뀌었습니다. 다시 실행해 주세요.",
        "AUTH_REQUIRED",
        401,
    )
    return answer


GET = {"skills": catalog}
POST = {"skills/run": run}
