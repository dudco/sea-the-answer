"""Ships and operation records (read), CSV validation, sample data."""

from __future__ import annotations

import json

from .. import config
from ..errors import require
from .. import operation_uploads as uploads


def operations(ctx):
    return {"ships": ctx.db.ships(), "records": ctx.db.operations()}


def validate(ctx):
    ctx.db.permit(ctx.user)
    check = ctx.db.validate_rows(ctx.body.get("rows"))
    return {"valid": not check["errors"], "errors": check["errors"], "count": len(ctx.body["rows"])}


def example(ctx):
    db, user = ctx.db, ctx.user
    db.permit(user)
    require(not db.ships() and not db.operations(), "빈 작업공간에서만 예시를 넣을 수 있습니다.")
    sample = json.loads((config.BACKEND_DIR / "knowledge/sample-data.json").read_text(encoding="utf-8"))
    for ship in sample["ships"]:
        db.change(user, "ship.save", {**ship, "sample": True})
    for row in sample["records"]:
        db.change(user, "operation.save", {**row, "factor": 3.114, "fuelType": "예시 연료", "sample": True, "note": "가상 예시 기록"})
    return {"ok": True}


GET = {"operations": operations}
POST = {"operations/validate": validate, "operations/example": example}
POST.update({'operations/import/'+name:uploads.endpoint(action) for name,action in {
    'start':uploads.start,'chunk':uploads.chunk,'preview':uploads.preview,
    'commit':uploads.commit,'reference':uploads.reference,'cancel':uploads.cancel}.items()})
