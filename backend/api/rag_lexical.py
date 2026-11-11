"""Rebuildable OpenSearch index. PG candidates are the sole access authority.

No model, indexing, or recovery runs on the search path. Network errors never
include the remote response (which may contain document text or credentials).
"""
from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import defaultdict
from functools import lru_cache

import httpx

from .rag_embeddings import content_hash, digest
from .rag_vocabulary import KOREAN_TERMS, SEARCH_SYNONYMS, STOPWORDS

SERVER_VERSION = "3.9.0"
ALIAS = "haedap-lexical"
ANALYSIS_VERSION = "nori-v1"


class LexicalUnavailable(RuntimeError):
    """Static reason codes only."""


def normalize(text):
    return unicodedata.normalize("NFKC", str(text or "")).lower()


def fields(row):
    return normalize("\n".join(str(row.get(k) or "") for k in ("title", "reference", "heading", "text")))


def identifiers(text):
    """Preserve decimal thresholds and numbered clauses split by Nori."""
    return list(dict.fromkeys(re.findall(r"(?<![\w.])\d+(?:[.\-]\d+)+(?![\w.])", normalize(text))))


def analysis():
    # Remove grammar only: Nori defaults also drop adverbs/auxiliaries, which
    # would lose Korean negation. Keep VX/MAG/VA, numbers and foreign words.
    return {"tokenizer": {"maritime_nori": {"type": "nori_tokenizer",
            "decompound_mode": "mixed", "user_dictionary_rules": list(KOREAN_TERMS)}},
            "filter": {"grammar": {"type": "nori_part_of_speech", "stoptags": [
                "EP", "EF", "EC", "ETN", "ETM", "JKS", "JKC", "JKG", "JKO", "JKB", "JKV", "JKQ", "JX", "JC",
                "XSV", "VCP"]},
                       "common": {"type": "stop", "stopwords": sorted(STOPWORDS)}},
            "analyzer": {"maritime": {"type": "custom", "tokenizer": "maritime_nori",
                                     "filter": ["lowercase", "grammar", "common"]}}}


@lru_cache(maxsize=1)
def fingerprint():
    return digest({"version": ANALYSIS_VERSION, "server": SERVER_VERSION,
                   "analysis": analysis(), "normalization": "NFKC-lower",
                   "fields": "title-reference-heading-text-unweighted-v1",
                   "identifiers": "decimal-clause-keyword-v1",
                   "aliases": SEARCH_SYNONYMS})


def record_id(row):
    return digest([fingerprint(), content_hash(row)])


def groups(rows):
    result = defaultdict(list)
    for row in rows:
        result[row["document_id"]].append(row)
    return result


def receipt(rows):
    return {"type": "receipt", "document_id": rows[0]["document_id"],
            "fingerprint": fingerprint(),
            "snapshot": digest(sorted(record_id(r) for r in rows)), "count": len(rows)}


def receipt_id(rows):
    return "ready-" + digest(receipt(rows))


def coverage(rows):
    return {"allowed_documents": len(groups(rows)), "allowed_chunks": len(rows),
            "ready_documents": 0, "ready_chunks": 0, "excluded_documents": 0,
            "excluded_chunks": 0, "reasons": {}, "status": "not_checked"}


class LexicalIndex:
    def __init__(self, *, index=None, client=None):
        self.fingerprint = fingerprint()
        self.name = index or ALIAS
        if not re.fullmatch(r"haedap-lexical(?:-[a-z0-9-]+)?", self.name):
            raise LexicalUnavailable("invalid_lexical_configuration")
        self._owned = client is None
        # Optional credentials are never embedded in emitted errors.
        user, password = os.getenv("HAEDAP_OPENSEARCH_USERNAME"), os.getenv("HAEDAP_OPENSEARCH_PASSWORD", "")
        self.client = client or httpx.Client(base_url=os.getenv("HAEDAP_OPENSEARCH_URL", "http://opensearch:9200"),
            timeout=30, trust_env=False, auth=(user, password) if user else None)

    def close(self):
        if self._owned:
            self.client.close()

    def request(self, method, path, body=None, *, missing=False, ndjson=None):
        try:
            kwargs = {"content": ndjson, "headers": {"Content-Type": "application/x-ndjson"}} if ndjson is not None else {"json": body}
            response = self.client.request(method, path, **kwargs)
            if missing and response.status_code == 404:
                return None
            response.raise_for_status()
            result = response.json()
            if result.get("errors"):
                raise LexicalUnavailable("lexical_bulk_failure")
            return result
        except LexicalUnavailable:
            raise
        except Exception:
            raise LexicalUnavailable("lexical_backend_failure") from None

    def resolve(self):
        mapping = self.request("GET", f"/{self.name}/_mapping", missing=True)
        if not mapping:
            raise LexicalUnavailable("lexical_index_missing")
        if len(mapping) != 1:
            raise LexicalUnavailable("lexical_contract_mismatch")
        name, info = next(iter(mapping.items()))
        if info["mappings"].get("_meta", {}).get("fingerprint") != self.fingerprint:
            raise LexicalUnavailable("lexical_contract_mismatch")
        return name

    def create(self):
        """Explicit worker/CLI only. Never called by search or analyze."""
        if self.name == ALIAS:
            active = self.request("GET", f"/{ALIAS}/_mapping", missing=True)
            if active and len(active) != 1:
                raise LexicalUnavailable("lexical_contract_mismatch")
            if active and len(active) == 1:
                target, mapping = next(iter(active.items()))
                if mapping["mappings"].get("_meta", {}).get("fingerprint") == self.fingerprint:
                    self.name = target
                    return target
        name = f"haedap-lexical-{self.fingerprint[:24]}" if self.name == ALIAS else self.name
        old = self.request("GET", f"/{name}/_mapping", missing=True)
        if not old:
            properties = {k: {"type": "keyword"} for k in
                          ("type", "chunk_id", "document_id", "content_hash", "fingerprint", "snapshot", "identifiers")}
            properties.update({"search_text": {"type": "text", "analyzer": "maritime"},
                               "count": {"type": "integer"}, "page": {"type": "integer"},
                               "title": {"type": "keyword", "index": False},
                               "heading": {"type": "keyword", "index": False}})
            try:
                self.request("PUT", f"/{name}", {"settings": {"number_of_shards": 1, "number_of_replicas": 0,
                    "analysis": analysis()}, "mappings": {"dynamic": "strict",
                    "_meta": {"fingerprint": self.fingerprint}, "properties": properties}})
            except LexicalUnavailable:
                # Another worker may have created the same contract concurrently.
                if not self.request("GET", f"/{name}/_mapping", missing=True):
                    raise
        original = self.name
        self.name = name
        self.resolve()
        if original == ALIAS and not self.request("GET", f"/_alias/{ALIAS}", missing=True):
            # Initial installation only; existing aliases require explicit promotion.
            self.request("POST", "/_aliases", {"actions": [{"add": {"index": name, "alias": ALIAS}}]})
        return name

    def promote(self):
        name = self.resolve()
        old = self.request("GET", f"/_alias/{ALIAS}", missing=True) or {}
        self.request("POST", "/_aliases", {"actions":
            [{"remove": {"index": key, "alias": ALIAS}} for key in old]
            + [{"add": {"index": name, "alias": ALIAS}}]})

    def analyze(self, text):
        name = self.resolve()
        result = self.request("POST", f"/{name}/_analyze", {"analyzer": "maritime", "text": normalize(text)})
        return [entry["token"] for entry in result["tokens"]] + identifiers(text)

    def query_tokens(self, query):
        original = self.analyze(query)
        # Match token phrases against ORIGINAL analysis only. No recursive or
        # substring expansion, no synonyms applied when indexing documents.
        additions = []
        original_text = " " + " ".join(original) + " "
        # Vocabulary is small; analyze all aliases in one remote request and
        # cache per analyzer fingerprint, not per user/corpus/query.
        aliases = self.alias_tokens()
        for group in aliases:
            if any(" " + " ".join(tokens) + " " in original_text for tokens in group if tokens):
                additions.extend(token for tokens in group for token in tokens)
        return list(dict.fromkeys(original + additions))[:128]

    def alias_tokens(self):
        # No Nori locally. Cache only the fixed, public vocabulary. The mapping
        # fingerprint was checked by analyze() before reaching this method.
        if self.fingerprint not in _ALIASES:
            name = self.resolve()
            marker = "zzhaedapaliasboundaryzz"
            flat = [normalize(a) for group in SEARCH_SYNONYMS for a in group]
            result = self.request("POST", f"/{name}/_analyze", {
                "analyzer": "maritime", "text": (" " + marker + " ").join(flat)})
            phrases = [[]]
            for item in result["tokens"]:
                if item["token"] == marker:
                    phrases.append([])
                else:
                    phrases[-1].append(item["token"])
            if len(phrases) != len(flat):
                raise LexicalUnavailable("lexical_analysis_mismatch")
            offset, grouped = 0, []
            for group in SEARCH_SYNONYMS:
                grouped.append(phrases[offset:offset+len(group)])
                offset += len(group)
            _ALIASES[self.fingerprint] = grouped
        return _ALIASES[self.fingerprint]

    def mget(self, name, ids):
        found = {}
        for start in range(0, len(ids), 256):
            result = self.request("POST", f"/{name}/_mget", {"ids": ids[start:start+256]})
            for doc in result["docs"]:
                if doc.get("error"):
                    raise LexicalUnavailable("lexical_verification_failed")
                if doc.get("found"):
                    found[doc["_id"]] = doc["_source"]
        return found

    def index(self, rows, batch_size=100):
        name = self.resolve()
        stored = self.mget(name, [record_id(r) for r in rows])
        pending = [r for r in rows if not self.valid_record(stored.get(record_id(r)), r)]
        for start in range(0, len(pending), batch_size):
            lines = []
            for row in pending[start:start+batch_size]:
                lines.extend([{"index": {"_id": record_id(row)}}, self.record(row)])
            self.request("POST", f"/{name}/_bulk?refresh=wait_for",
                         ndjson="".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines))
        return len(pending)

    def record(self, row):
        return {"type": "chunk", "chunk_id": row["id"], "document_id": row["document_id"],
                "content_hash": content_hash(row), "fingerprint": self.fingerprint,
                "title": row.get("title") or "", "heading": row.get("heading") or "",
                "page": row.get("page"), "search_text": fields(row), "identifiers": identifiers(fields(row))}

    def valid_record(self, stored, row):
        return stored == self.record(row)

    def verify(self, rows, *, publish=False):
        name = self.resolve()
        stored = self.mget(name, [record_id(r) for r in rows])
        missing = sum(not self.valid_record(stored.get(record_id(r)), r) for r in rows)
        if publish and missing == 0:
            subsets = list(groups(rows).values())
            for start in range(0, len(subsets), 100):
                lines = []
                for subset in subsets[start:start+100]:
                    lines.extend([{"index": {"_id": receipt_id(subset)}}, receipt(subset)])
                self.request("POST", f"/{name}/_bulk?refresh=wait_for",
                             ndjson="".join(json.dumps(line) + "\n" for line in lines))
        elif publish and missing:
            # Remove existing certification as soon as explicit verification
            # discovers corruption; searching never performs full scans.
            for subset in groups(rows).values():
                self.request("DELETE", f"/{name}/_doc/{receipt_id(subset)}?refresh=wait_for", missing=True)
        return {"chunks": len(rows), "missing_chunks": missing}

    def purge(self, document_id, keep=()):
        name = self.resolve()
        query = {"bool": {"filter": [{"term": {"document_id": document_id}}]}}
        if keep:
            query["bool"]["must_not"] = [{"ids": {"values": list(keep)}}]
        self.request("POST", f"/{name}/_delete_by_query?refresh=true&conflicts=proceed", {"query": query})

    def search(self, query, rows, top_k=5, *, diagnostics=None, complete_chunks=None):
        if type(top_k) is not int or not 1 <= top_k <= 1000:
            raise ValueError("top_k must be 1..1000")
        if not rows or not query.strip():
            return []
        name = self.resolve()  # Pin physical index throughout this request.
        report = diagnostics if diagnostics is not None else {}
        report.update(coverage(rows))
        full = groups(complete_chunks if complete_chunks is not None else rows)
        selected = groups(rows)
        descriptors = {doc: full.get(doc, []) for doc in selected}
        ready = self.mget(name, [receipt_id(rs) for rs in descriptors.values() if rs])
        allowed = []
        for doc, subset in selected.items():
            source = descriptors[doc]
            if source and ready.get(receipt_id(source)) == receipt(source):
                current = {r["id"]: content_hash(r) for r in source}
                if any(current.get(r["id"]) != content_hash(r) for r in subset):
                    raise LexicalUnavailable("lexical_snapshot_mismatch")
                allowed.extend(subset)
                report["ready_documents"] += 1
        report["ready_chunks"] = len(allowed)
        report["excluded_documents"] = len(selected) - report["ready_documents"]
        report["excluded_chunks"] = len(rows) - len(allowed)
        report["reasons"] = {"unverified_or_changed": report["excluded_documents"]} if report["excluded_documents"] else {}
        report["status"] = "partial" if report["excluded_documents"] else "complete"
        if not allowed:
            raise LexicalUnavailable("lexical_no_ready_documents")
        terms = self.query_tokens(query)
        if not terms:
            return []
        by_id = {record_id(row): row for row in allowed}
        identities = list(by_id)
        results = []
        # Disjoint ID partitions avoid terms-query size limits. The same single
        # physical shard provides global BM25 statistics in every partition.
        for start in range(0, len(identities), 5000):
            result = self.request("POST", f"/{name}/_search", {"size": top_k,
                "query": {"bool": {"filter": [{"ids": {"values": identities[start:start+5000]}}],
                    "must": [{"bool": {"should": [{"term": {field: token}} for token in terms
                                                   for field in ("search_text", "identifiers")],
                                       "minimum_should_match": 1}}]}},
                "sort": [{"_score": "desc"}, {"chunk_id": "asc"}]})
            if result.get("timed_out") or result.get("_shards", {}).get("failed", 0):
                raise LexicalUnavailable("lexical_partial_failure")
            for hit in result["hits"]["hits"]:
                row = by_id.get(hit["_id"])
                if row is None or not self.valid_record(hit["_source"], row):
                    raise LexicalUnavailable("lexical_verification_failed")
                score = float(hit["_score"])
                if not math.isfinite(score):
                    raise LexicalUnavailable("lexical_verification_failed")
                results.append({**row, "score": score})
        return sorted(results, key=lambda r: (-r["score"], r["id"]))[:top_k]


_ALIASES: dict[str, list] = {}
