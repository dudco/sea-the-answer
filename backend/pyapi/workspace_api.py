"""FastAPI replacement for the existing /api/* surface, backed by PostgreSQL."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from secrets import token_hex

import psycopg
from fastapi import FastAPI, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .workspace_store import ApiError, ROOT, Workspace, public_user, require


app = FastAPI(title="SEA THE ANSWER API", version="1.4.0")
csrf_token = token_hex(32)
sessions: dict[str, dict] = {}
login_attempts: dict[str, dict] = {}
initialize_lock = threading.Lock()
initialized = False
busy = threading.BoundedSemaphore(4)


def backup_directory() -> Path:
    value = os.getenv("HAEDAP_BACKUP_DIR")
    return Path(value).resolve() if value else ROOT / "backend/data/backups"


def initialize(db: Workspace) -> None:
    global initialized
    if initialized:
        return
    with initialize_lock:
        if not initialized:
            db.bootstrap()
            db.db.commit()
            initialized = True


def guest_identity(request: Request, response: Response) -> dict:
    cookie = request.cookies.get("haedap_guest")
    if not cookie or not re.fullmatch(r"[a-f0-9]{64}", cookie):
        cookie = token_hex(32)
        response.set_cookie("haedap_guest", cookie, max_age=31536000, httponly=True, samesite="strict")
    guest_id = "guest_" + hashlib.sha256(cookie.encode()).hexdigest()
    return {"id": guest_id, "username": "", "name": "일반 사용자 · " + guest_id[6:14],
            "role": "guest", "active": True, "version": 1}


def current_user(db: Workspace, request: Request, guest: dict) -> dict:
    cookie = request.cookies.get("haedap_session")
    if not cookie:
        return guest
    session = sessions.get(hashlib.sha256(cookie.encode()).hexdigest())
    if not session or session["expires"] < time.time():
        return guest
    user = db.user_by_id(session["id"])
    return public_user(user) if user and user["version"] == session["version"] else guest


def validate_origin(request: Request) -> None:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    require(bool(re.fullmatch(r"(?:127\.0\.0\.1|localhost|[A-Za-z0-9.-]+)(?::\d+)?", host)),
            "접속 주소를 확인해 주세요.", "HOST_DENIED", 403)
    origin = request.headers.get("origin")
    require(not origin or origin == "http://" + host, "동일 출처 요청만 허용합니다.", "ORIGIN_DENIED", 403)
    require(request.headers.get("sec-fetch-site") not in ("cross-site", "same-site"),
            "동일 출처 요청만 허용합니다.", "ORIGIN_DENIED", 403)


def authenticate_request(db: Workspace, request: Request, response: Response) -> tuple[dict, dict]:
    validate_origin(request)
    guest = guest_identity(request, response)
    user = current_user(db, request, guest)
    identity = request.headers.get("x-haedap-identity")
    if request.url.path != "/api/health" and not request.url.path.startswith("/api/auth/") and identity:
        require(identity == user["id"], "사용자 상태가 바뀌었습니다.", "AUTH_REQUIRED", 401)
    return user, guest


def get_route(db: Workspace, user: dict, path: str):
    if path == "health":
        return {"ok": True, "storage": "postgresql", "retrieval": "literal-ko-en", "llmConfigured": bool(os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_MODEL")),
                "csrfToken": csrf_token, "user": user, "setupRequired": False,
                "documents": len(db.allowed_document_ids(user)), "version": "1.4.0",
                "authenticated": user["role"] == "admin", "publicAccess": True}
    if path == "documents":
        return {"documents": db.documents(user)}
    if path == "operations":
        return {"ships": db.ships(), "records": db.operations()}
    if path == "reports":
        return {"reports": db.reports(user)}
    if path == "history":
        return {"history": db.history(user)}
    if path == "users":
        db.permit(user)
        return {"users": [public_user(row) for row in db.all("SELECT * FROM users ORDER BY username")]}
    if path == "logs":
        db.permit(user)
        return {"logs": [{**row, "at": row["at"].isoformat()} for row in db.all("SELECT * FROM audit ORDER BY at DESC LIMIT 500")]}
    if path == "changes":
        return {"changes": db.list_changes(user)}
    if path == "backups":
        setting = db.one("SELECT value FROM settings WHERE key='autoBackup'")
        return {"backups": db.list_backups(user, backup_directory()), "autoBackup": setting["value"] if setting else "off"}
    if path.startswith("backups/"):
        return db.read_backup(user, backup_directory(), path[len("backups/"):])
    if path == "tools":
        return {"tools": [{"name": "calculate_emissions"}, {"name": "voyage_time"}]}
    if path.startswith("reports/"):
        report_id = path[len("reports/"):]
        if report_id == "current" and not db.report("current"):
            return {"report": None}
        return {"report": db.load_report(user, report_id)}
    raise ApiError(404, "NOT_FOUND", "API 경로를 찾을 수 없습니다.")


def post_route(db: Workspace, user: dict, guest: dict, path: str, body: dict, request: Request, response: Response):
    if path == "auth/setup":
        raise ApiError(410, "SETUP_DISABLED", "초기 설정은 필요하지 않습니다.")
    if path == "auth/login":
        remote = request.client.host if request.client else "local"
        attempts = login_attempts.get(remote, {"count": 0, "until": 0})
        if attempts["until"] < time.time():
            attempts = {"count": 0, "until": time.time() + 60}
        require(attempts["count"] < 10, "로그인 시도가 많습니다.", "LOGIN_LIMIT", 429)
        attempts["count"] += 1
        login_attempts[remote] = attempts
        admin = db.authenticate(body.get("username", ""), body.get("password", ""))
        require(admin["role"] == "admin", "관리자 계정으로 로그인해 주세요.", "FORBIDDEN", 403)
        login_attempts.pop(remote, None)
        old_cookie = request.cookies.get("haedap_session")
        if old_cookie:
            sessions.pop(hashlib.sha256(old_cookie.encode()).hexdigest(), None)
        token = token_hex(32)
        sessions[hashlib.sha256(token.encode()).hexdigest()] = {"id": admin["id"], "version": admin["version"], "expires": time.time() + 43200}
        response.set_cookie("haedap_session", token, max_age=43200, httponly=True, samesite="strict")
        return {"user": admin}
    if path == "auth/logout":
        cookie = request.cookies.get("haedap_session")
        if cookie:
            sessions.pop(hashlib.sha256(cookie.encode()).hexdigest(), None)
        response.delete_cookie("haedap_session")
        if user["role"] == "admin":
            db.audit(user, "auth", "로그아웃", user["username"])
        return {"ok": True, "user": guest}
    if path == "ask":
        return db.answer(user, body)
    if path == "search":
        return {"evidence": db.search(user, body.get("question", ""), body.get("filter", "all"))}
    if path == "users":
        return {"user": db.save_user(user, body)}
    if path == "changes":
        return db.change(user, body.get("kind", ""), body.get("payload"))
    if path == "changes/review":
        return db.review_change(user, body)
    if path == "operations/validate":
        db.permit(user)
        check = db.validate_rows(body.get("rows"))
        return {"valid": not check["errors"], "errors": check["errors"], "count": len(body["rows"])}
    if path == "operations/example":
        db.permit(user)
        require(not db.ships() and not db.operations(), "빈 작업공간에서만 예시를 넣을 수 있습니다.")
        content = (ROOT / "backend/sample-data.mjs").read_text(encoding="utf-8")
        sample = json.loads(content.split("=", 1)[1].strip().rstrip(";"))
        for ship in sample["ships"]:
            db.change(user, "ship.save", {**ship, "sample": True})
        for row in sample["records"]:
            db.change(user, "operation.save", {**row, "factor": 3.114, "fuelType": "예시 연료", "sample": True, "note": "가상 예시 기록"})
        return {"ok": True}
    if path in ("reports", "reports/current"):
        return {"report": db.save_report(user, {**body, "id": "current"} if path.endswith("current") else body)}
    if path == "reports/generate":
        return {"report": db.generate_report(user, body)}
    if path == "reports/submit":
        return db.submit_report(user, body)
    if path == "backups":
        return {"backup": db.create_backup(user, backup_directory())}
    if path == "backups/settings":
        db.permit(user)
        require(body.get("autoBackup") in ("daily", "off"), "자동 백업 설정을 확인해 주세요.")
        db.run("INSERT INTO settings VALUES('autoBackup',%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (body["autoBackup"],))
        db.audit(user, "backup", "자동 백업 설정", body["autoBackup"])
        return {"ok": True}
    if path == "backups/import":
        return {"backup": db.import_backup(user, backup_directory(), body)}
    if path == "backups/restore":
        result = db.restore_backup(user, backup_directory(), body)
        sessions.clear()
        return result
    if path == "tools/calculate_emissions":
        result = db.calculate_emissions(body)
        db.audit(user, "tool", "계산 실행", "calculate_emissions", {"id": result["id"]})
        return {"result": result}
    if path == "tools/voyage_time":
        result = db.voyage_time(body)
        db.audit(user, "tool", "계산 실행", "voyage_time", {"id": result["id"]})
        return {"result": result}
    raise ApiError(404, "NOT_FOUND", "API 경로를 찾을 수 없습니다.")


def handle(request: Request, response: Response, path: str, body: dict | None):
    with Workspace(os.getenv("DATABASE_URL", "")) as db:
        initialize(db)
        user, guest = authenticate_request(db, request, response)
        if request.method == "GET":
            if path.startswith("documents/") and path.endswith("/pdf"):
                doc_id = path[len("documents/"):-len("/pdf")]
                require(db.can_read_document(user, doc_id), "문서 열람 권한이 없습니다.", "FORBIDDEN", 403)
                file = db.one("SELECT name,base64 FROM document_files WHERE id=%s", (doc_id,))
                require(file, "저장된 PDF가 없습니다.", "NOT_FOUND", 404)
                return Response(content=base64.b64decode(file["base64"]), media_type="application/pdf",
                                headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
            return get_route(db, user, path)
        require(request.headers.get("x-haedap-token") == csrf_token,
                "연결을 새로고침한 뒤 다시 시도하세요.", "SESSION_EXPIRED", 403)
        require(isinstance(body, dict), "JSON 객체가 필요합니다.")
        return post_route(db, user, guest, path, body, request, response)


@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def api(request: Request, response: Response, path: str):
    if not busy.acquire(blocking=False):
        raise ApiError(429, "BUSY", "처리 중인 요청이 많습니다.")
    try:
        body = None
        if request.method == "POST":
            require(request.headers.get("content-type", "").split(";", 1)[0].strip() == "application/json",
                    "application/json 요청이 필요합니다.", "CONTENT_TYPE", 415)
            raw = await request.body()
            limit = 100 * 1024 * 1024 if path == "backups/import" else 38 * 1024 * 1024 if path == "changes" else 1024 * 1024
            require(len(raw) <= limit, "요청이 너무 큽니다.", "BODY_TOO_LARGE", 413)
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ApiError(400, "INVALID_JSON", "올바른 JSON이 필요합니다.") from exc
        result = await run_in_threadpool(handle, request, response, path, body)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return result
    finally:
        busy.release()


@app.exception_handler(ApiError)
async def api_error(_request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}},
                        headers={"Cache-Control": "no-store"})


@app.exception_handler(psycopg.Error)
async def database_error(_request: Request, _exc: psycopg.Error):
    return JSONResponse(status_code=503, content={"error": {"code": "DATA_SOURCE_UNAVAILABLE", "message": "PostgreSQL 요청에 실패했습니다."}},
                        headers={"Cache-Control": "no-store"})


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, _exc: Exception):
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", "message": "요청을 처리하지 못했습니다."}},
                        headers={"Cache-Control": "no-store"})
