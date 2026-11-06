"""Documents, original PDFs, evidence search, integrated answers and question history."""

from __future__ import annotations

import base64

from fastapi import Response

from ..errors import ApiError, require
from ..web import security
from ..navigation_query import try_answer as navigation_answer
from ..question_workflows import try_answer as workflow_answer


def documents(ctx):
    return {"documents": ctx.db.documents(ctx.user)}


def document_pdf(ctx):
    # GET documents/{id}/pdf
    if not ctx.path.endswith("/pdf"):
        raise ApiError(404, "NOT_FOUND", "API 경로를 찾을 수 없습니다.")
    doc_id = ctx.path[len("documents/"):-len("/pdf")]
    require(ctx.db.can_read_document(ctx.user, doc_id), "문서 열람 권한이 없습니다.", "FORBIDDEN", 403)
    file = ctx.db.one("SELECT name,base64 FROM document_files WHERE id=%s", (doc_id,))
    require(file, "저장된 PDF가 없습니다.", "NOT_FOUND", 404)
    return Response(content=base64.b64decode(file["base64"]), media_type="application/pdf",
                    headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})


def history(ctx):
    return {"history": ctx.db.history(ctx.user)}


def ask(ctx):
    db, user = ctx.db, ctx.user
    answer = navigation_answer(ctx)
    if answer is None:
        answer = workflow_answer(ctx)
    if answer is None:
        answer = db.answer(user, ctx.body)
    require(security.current_user(db, ctx.request, ctx.guest)["id"] == user["id"],
            "사용자 상태가 바뀌었습니다. 다시 연결해 주세요.", "AUTH_REQUIRED", 401)
    require(all(db.can_read_document(user, item["document_id"]) for item in answer["evidence"]),
            "문서 권한이 변경되었습니다. 다시 질문해 주세요.", "FORBIDDEN", 403)
    return answer


def search(ctx):
    return {"evidence": ctx.db.search(ctx.user, ctx.body.get("question", ""), ctx.body.get("filter", "all"))}


GET = {"documents": documents, "history": history}
GET_PREFIX = [("documents/", document_pdf)]
POST = {"ask": ask, "search": search}
