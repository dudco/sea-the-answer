"""Documents: revisions, chunks, access scope and BM25 search."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timezone

from psycopg.types.json import Jsonb

from ..errors import ApiError, require
from ..rag_preprocessing import preprocess_sections
from ..rag_search import retrieve
from ..rag_embeddings import content_hash
from ..rag_jobs import enqueue
from ..validation import iso_date, sha256, stamp, text


class DocumentStore:
    def document_meta(self, doc_id: str) -> dict:
        row = self.one("SELECT body FROM document_meta WHERE id=%s", (doc_id,))
        return row["body"] if row else {"scope": "all", "status": "active", "revision": 0}

    def can_read_document(self, user: dict, doc_id: str) -> bool:
        row = self.one("SELECT id FROM documents WHERE id=%s", (doc_id,))
        if not row:
            return False
        meta = self.document_meta(doc_id)
        return meta.get("status") != "deleted" and (
            user["role"] == "admin" or meta.get("scope", "all") == "all"
            or meta.get("scope") == "operator" and user["role"] == "operator"
        )

    def documents(self, user: dict) -> list[dict]:
        rows = self.all("SELECT * FROM documents ORDER BY active DESC,title,imported_at DESC")
        result = []
        for row in rows:
            if not self.can_read_document(user, row["id"]):
                continue
            meta = self.document_meta(row["id"])
            sections = self.all("""SELECT c.id,c.heading,c.text,c.position,p.page FROM chunks c
                LEFT JOIN chunk_pages p ON p.id=c.id WHERE c.document_id=%s ORDER BY c.position""", (row["id"],))
            result.append({**{key: stamp(value) for key, value in row.items()}, "meta": meta,
                           "currentRevision": row["active"],
                           "active": row["active"] and meta.get("status", "active") == "active",
                           "hasPdf": bool(self.one("SELECT 1 FROM document_files WHERE id=%s", (row["id"],))),
                           "sections": sections})
        return result

    def allowed_document_ids(self, user: dict) -> list[str]:
        return [doc["id"] for doc in self.documents(user) if doc["active"]]

    @staticmethod
    def _document_hash(raw: dict) -> str:
        normalized = {"id": raw["id"], "title": raw["title"], "kind": raw["kind"],
                      "url": raw.get("url"), "reference": raw["reference"], "version": raw["version"],
                      "reviewedAt": raw["reviewedAt"], "language": raw.get("language", "ko"),
                      "sections": raw["sections"]}
        payload = "haedap-chunk-v1\n" + json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
        return sha256(payload.encode("utf-8"))

    def save_document(self, payload: dict) -> dict:
        mode = payload.get("mode", "content")
        require(mode in ("content", "metadata"), "문서 저장 방식을 확인해 주세요.")
        if mode == "metadata":
            result = self._save_document_metadata(payload)
            # Keep source chunks intact, but repair missing/cancelled/model-stale
            # indexing after metadata-only saves (including reactivation).
            enqueue(self, result["id"])
            return result
        raw = payload.get("document")
        require(isinstance(raw, dict), "문서가 필요합니다.")
        logical_id = text(raw.get("id"), "문서 ID", 80)
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", logical_id)), "문서 ID가 올바르지 않습니다.")
        require(raw.get("kind") in ("official-summary", "onboard", "sample"), "문서 종류를 확인해 주세요.")
        require(isinstance(raw.get("sections"), list) and 0 < len(raw["sections"]) <= 1500, "문서 절이 필요합니다.")
        for section in raw["sections"]:
            text(section.get("heading"), "절 제목", 200)
            text(section.get("text"), "본문", 20000)
        reviewed = iso_date(raw.get("reviewedAt"), "확인일")
        title = text(raw.get("title"), "문서 제목", 200)
        reference = text(raw.get("reference"), "출처 조항", 200)
        version = text(raw.get("version"), "버전", 100)
        meta = payload.get("meta") or {}
        require(meta.get("scope", "all") in ("all", "operator", "admin"), "문서 열람 범위를 확인해 주세요.")
        require(meta.get("status", "active") in ("active", "retired"), "문서 상태를 확인해 주세요.")
        current = self.one("SELECT id,hash FROM documents WHERE logical_id=%s AND active=true FOR UPDATE", (logical_id,))
        if "expectedId" in payload:
            require((current or {}).get("id", "") == payload["expectedId"], "문서가 변경되었습니다.", "VERSION_CONFLICT", 409)
        if current and "expectedMetaRevision" in payload:
            require(self.document_meta(current["id"]).get("revision") == payload["expectedMetaRevision"],
                    "문서 정보가 변경되었습니다.", "VERSION_CONFLICT", 409)
        digest = self._document_hash(raw)
        revision_id = logical_id + "-" + digest[:16]
        unchanged = bool(current and current["hash"] == digest)
        existing_revision = self.one("SELECT id FROM documents WHERE id=%s", (revision_id,)) if not unchanged else None
        chunks = None
        if not unchanged and not existing_revision:
            chunks = preprocess_sections(raw["sections"])
            require(bool(chunks), "전처리 후 검색할 본문이 없습니다. 원문을 확인해 주세요.")
        if not unchanged:
            self.run("UPDATE documents SET active=false WHERE logical_id=%s", (logical_id,))
        if not unchanged and existing_revision:
            self.run("UPDATE documents SET active=true WHERE id=%s", (revision_id,))
        elif not unchanged:
            self.run("""INSERT INTO documents(id,logical_id,hash,title,kind,url,reference,version,
                reviewed_at,language,active) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true)""",
                (revision_id, logical_id, digest, title, raw["kind"], raw.get("url"), reference,
                 version, reviewed, raw.get("language", "ko")))
            for position, chunk in enumerate(chunks, 1):
                chunk_id = f"{revision_id}-{position}"
                self.run("INSERT INTO chunks VALUES(%s,%s,%s,%s,%s)",
                         (chunk_id, revision_id, position, chunk["heading"], chunk["text"]))
                self.run("INSERT INTO chunk_pages VALUES(%s,%s)", (chunk_id, chunk["page"]))
        next_meta = {"scope": meta.get("scope", "all"), "status": meta.get("status", "active"),
                     "issuer": meta.get("issuer", ""), "issuedAt": meta.get("issuedAt", ""),
                     "revisedAt": meta.get("revisedAt", ""), "applicability": meta.get("applicability", ""),
                     "revision": int(datetime.now(timezone.utc).timestamp() * 1000)}
        for old in self.all("SELECT id FROM documents WHERE logical_id=%s", (logical_id,)):
            old_meta = self.document_meta(old["id"])
            old_meta["scope"] = next_meta["scope"]
            self.run("INSERT INTO document_meta VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                     (old["id"], Jsonb(next_meta if old["id"] == revision_id else old_meta)))
        file = payload.get("file")
        if file:
            try:
                raw_bytes = base64.b64decode(file["base64"], validate=True)
            except (ValueError, KeyError) as exc:
                raise ApiError(400, "INVALID_INPUT", "PDF 형식을 확인해 주세요.") from exc
            require(len(raw_bytes) <= 25 * 1024 * 1024 and raw_bytes.startswith(b"%PDF-"), "PDF는 25MB 이하의 유효한 파일이어야 합니다.")
            self.run("INSERT INTO document_files VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name,base64=excluded.base64",
                     (revision_id, str(file.get("name", "document.pdf"))[:200], file["base64"]))
        elif current:
            old_file = self.one("SELECT name,base64 FROM document_files WHERE id=%s", (current["id"],))
            if old_file:
                self.run("INSERT INTO document_files VALUES(%s,%s,%s) ON CONFLICT(id) DO NOTHING",
                         (revision_id, old_file["name"], old_file["base64"]))
        enqueue(self, revision_id)
        return {"id": revision_id, "status": "unchanged" if unchanged else "updated" if current else "created"}

    def _save_document_metadata(self, payload: dict) -> dict:
        """Update only metadata; stored chunks must never be treated as source text."""
        raw = payload.get("document")
        require(isinstance(raw, dict) and set(raw) == {"id"}, "정보 수정에는 문서 ID만 전달해 주세요.")
        require("file" not in payload, "PDF 교체는 본문·버전 개정을 이용해 주세요.")
        logical_id = text(raw.get("id"), "문서 ID", 80)
        require(bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", logical_id)), "문서 ID가 올바르지 않습니다.")
        require(isinstance(payload.get("expectedId"), str) and bool(payload["expectedId"])
                and type(payload.get("expectedMetaRevision")) is int, "현재 문서 버전 정보가 필요합니다.")
        patch = payload.get("meta")
        allowed = {"scope", "status", "issuer", "issuedAt", "revisedAt", "applicability"}
        require(isinstance(patch, dict) and bool(patch) and set(patch) <= allowed, "수정할 문서 정보를 확인해 주세요.")
        if "scope" in patch:
            require(patch["scope"] in ("all", "operator", "admin"), "문서 열람 범위를 확인해 주세요.")
        if "status" in patch:
            require(patch["status"] in ("active", "retired"), "문서 상태를 확인해 주세요.")
        for key, maximum in (("issuer", 200), ("applicability", 1000)):
            if key in patch:
                require(isinstance(patch[key], str) and len(patch[key]) <= maximum, "문서 정보 길이를 확인해 주세요.")
        for key in ("issuedAt", "revisedAt"):
            if key in patch and patch[key] != "":
                iso_date(patch[key], "문서 일자")
        current = self.one("SELECT id,hash FROM documents WHERE logical_id=%s AND active=true FOR UPDATE", (logical_id,))
        require(current and current["id"] == payload["expectedId"], "문서가 변경되었습니다.", "VERSION_CONFLICT", 409)
        old_meta = self.document_meta(current["id"])
        require(old_meta.get("revision", 0) == payload["expectedMetaRevision"],
                "문서 정보가 변경되었습니다.", "VERSION_CONFLICT", 409)
        if all(old_meta.get(key, "") == value for key, value in patch.items()):
            return {"id": current["id"], "status": "unchanged"}
        next_meta = {**old_meta, **patch,
                     "revision": max(int(datetime.now(timezone.utc).timestamp() * 1000),
                                     old_meta.get("revision", 0) + 1)}
        # Preserve the existing policy: access scope applies to historical revisions too.
        for row in self.all("SELECT id FROM documents WHERE logical_id=%s", (logical_id,)):
            meta = self.document_meta(row["id"])
            meta["scope"] = next_meta.get("scope", "all")
            self.run("INSERT INTO document_meta VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                     (row["id"], Jsonb(next_meta if row["id"] == current["id"] else meta)))
        return {"id": current["id"], "status": "updated"}

    def delete_document(self, doc_id: str) -> dict:
        row = self.one("SELECT id,logical_id,active FROM documents WHERE id=%s", (doc_id,))
        require(row and row["active"], "문서를 찾을 수 없습니다.", "VERSION_CONFLICT", 409)
        for item in self.all("SELECT id FROM documents WHERE logical_id=%s", (row["logical_id"],)):
            meta = self.document_meta(item["id"])
            meta["status"] = "deleted"
            self.run("INSERT INTO document_meta VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET body=excluded.body",
                     (item["id"], Jsonb(meta)))
        self.run("UPDATE documents SET active=false WHERE logical_id=%s", (row["logical_id"],))
        return {"id": doc_id}

    def search(self, user: dict, question: str, kind: str = "all", document_ids: list[str] | None = None) -> list[dict]:
        text(question, "질문", 2000)
        candidates = self.search_candidates(user, kind, document_ids)
        # Filter before either retriever so inaccessible chunks cannot affect ranking.
        # Keep scores internal; /search and /ask retain their evidence contract.
        results = retrieve(question, candidates, top_k=5)
        # Re-read current PG state after potentially slow embedding/remote IO,
        # including requests that fell back to BM25.
        current = {row["id"]: row for row in self.search_candidates(user, kind, document_ids)}
        results = [current[row["id"]] for row in results if row["id"] in current
                   and content_hash(row) == content_hash(current[row["id"]])]
        return [{key: value for key, value in row.items() if key != "score"}
                for row in results]

    def search_candidates(self, user: dict, kind: str = "all", document_ids: list[str] | None = None) -> list[dict]:
        """Shared read-only candidate selection for API search and diagnostics."""
        require(kind in ("all", "imo", "manual"), "문서 필터가 올바르지 않습니다.")
        if document_ids is not None:
            require(isinstance(document_ids, list) and 0 < len(document_ids) <= 20
                    and all(isinstance(i, str) and 0 < len(i) <= 200 for i in document_ids)
                    and len(set(document_ids)) == len(document_ids), "선택 문서를 확인해 주세요.")
            allowed = set(self.allowed_document_ids(user))
            require(set(document_ids) <= allowed, "선택 문서를 사용할 수 없습니다. 문서 상태와 열람 권한을 확인해 주세요.",
                    "DOCUMENT_SCOPE_UNAVAILABLE", 403)
        scope_sql = " AND d.id = ANY(%s)" if document_ids is not None else ""
        sql = """SELECT c.id,c.document_id,c.heading,c.text,p.page,d.title,d.kind,d.url,
            d.reference,d.version,d.reviewed_at,d.hash,m.body AS meta
            FROM chunks c JOIN documents d ON d.id=c.document_id
            LEFT JOIN chunk_pages p ON p.id=c.id LEFT JOIN document_meta m ON m.id=d.id
            WHERE d.active=true""" + scope_sql + " ORDER BY d.id,c.position"
        rows = self.all(sql, (document_ids,)) if document_ids is not None else self.all(sql)
        candidates = []
        for row in rows:
            meta = row["meta"] or {"scope": "all", "status": "active"}
            if meta.get("status") != "active":
                continue
            scope = meta.get("scope", "all")
            if user["role"] != "admin" and scope != "all" and not (scope == "operator" and user["role"] == "operator"):
                continue
            if kind == "imo" and row["kind"] != "official-summary" or kind == "manual" and row["kind"] == "official-summary":
                continue
            candidates.append({**row, "reviewed_at": stamp(row["reviewed_at"]), "meta": meta})
        return candidates
