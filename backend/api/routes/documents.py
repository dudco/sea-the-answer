"""Documents, original PDFs, evidence search, integrated answers and question history."""

from __future__ import annotations

import base64

from fastapi import Response

from ..errors import ApiError, require
from ..web import security
from ..question_router import answer as route_answer


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
    conversation_id = ctx.body.get("conversationId")
    if conversation_id is not None:
        db.lock_conversation(user, conversation_id)
    answer = route_answer(ctx)
    require(security.current_user(db, ctx.request, ctx.guest)["id"] == user["id"],
            "사용자 상태가 바뀌었습니다. 다시 연결해 주세요.", "AUTH_REQUIRED", 401)
    require(all(db.can_read_document(user, item["document_id"])
                for item in [*answer["evidence"], *answer.get("relatedEvidence", [])]),
            "문서 권한이 변경되었습니다. 다시 질문해 주세요.", "FORBIDDEN", 403)
    if conversation_id is not None:
        db.attach_conversation(answer, conversation_id)
    return answer


def search(ctx):
    return {"evidence": ctx.db.search(ctx.user, ctx.body.get("question", ""), ctx.body.get("filter", "all"))}


def conversations(ctx):
    return {"history": ctx.db.conversations(ctx.user)}


def conversation(ctx):
    return ctx.db.conversation(ctx.user, ctx.path[len("conversations/"):])


def delete_conversation(ctx):
    return ctx.db.delete_conversation(ctx.user, ctx.body.get("id"))


GET = {"documents": documents, "history": history, "conversations": conversations}
GET_PREFIX = [("documents/", document_pdf), ("conversations/", conversation)]
POST = {"ask": ask, "search": search, "conversations/delete": delete_conversation}
