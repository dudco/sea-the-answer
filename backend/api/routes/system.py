"""Health check (also hands out the CSRF token) and calculation tools."""

from __future__ import annotations

from .. import config
from ..store import TOOL_DEFINITIONS
from ..web import security


def health(ctx):
    user = ctx.user
    return {"ok": True, "storage": "postgresql", "retrieval": "bm25-ko-en", "llmConfigured": config.llm_configured(),
            "csrfToken": security.csrf_token, "user": user, "setupRequired": False,
            "documents": len(ctx.db.allowed_document_ids(user)), "version": config.VERSION,
            "authenticated": user["role"] == "admin", "publicAccess": True}


def tools(_ctx):
    return {"tools": TOOL_DEFINITIONS}


def calculate_emissions(ctx):
    result = ctx.db.calculate_emissions(ctx.body)
    ctx.db.audit(ctx.user, "tool", "계산 실행", "calculate_emissions", {"id": result["id"]})
    return {"result": result}


def voyage_time(ctx):
    result = ctx.db.voyage_time(ctx.body)
    ctx.db.audit(ctx.user, "tool", "계산 실행", "voyage_time", {"id": result["id"]})
    return {"result": result}


GET = {"health": health, "tools": tools}
POST = {"tools/calculate_emissions": calculate_emissions, "tools/voyage_time": voyage_time}
