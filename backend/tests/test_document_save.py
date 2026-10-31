"""Storage-boundary regression tests; SQL effects are recorded without a live DB."""
from copy import deepcopy
from unittest.mock import Mock

import pytest

from api.errors import ApiError
from api.store import documents
from api.store.documents import DocumentStore


def metadata_payload():
    return {"mode": "metadata", "document": {"id": "manual"}, "expectedId": "manual-current",
            "expectedMetaRevision": 10, "meta": {"issuer": "New issuer", "scope": "admin"}}


def metadata_store():
    store = DocumentStore()
    store.one = Mock(return_value={"id": "manual-current", "hash": "original-hash"})
    store.all = Mock(return_value=[{"id": "manual-current"}, {"id": "manual-previous"}])
    original = {"revision": 10, "scope": "all", "status": "active", "issuer": "Old issuer",
                "applicability": "Keep this", "customField": "Keep this too"}
    store.document_meta = Mock(side_effect=lambda _id: deepcopy(original))
    store.run = Mock()
    return store


def test_metadata_preserves_revision_chunks_and_files_and_historical_scope(monkeypatch):
    store = metadata_store()
    preprocessing = Mock(side_effect=AssertionError("metadata must never be chunked"))
    monkeypatch.setattr(documents, "preprocess_sections", preprocessing)
    assert store.save_document(metadata_payload()) == {"id": "manual-current", "status": "updated"}
    preprocessing.assert_not_called()
    assert "FOR UPDATE" in store.one.call_args.args[0]
    assert store.run.call_count == 3
    assert "INSERT INTO rag_index_jobs" in store.run.call_args_list[-1].args[0]
    saved = {}
    for call in store.run.call_args_list[:-1]:
        query, (doc_id, body) = call.args
        assert query.startswith("INSERT INTO document_meta")
        saved[doc_id] = body.obj
    assert saved["manual-current"]["issuer"] == "New issuer"
    assert saved["manual-current"]["revision"] > 10
    assert saved["manual-current"]["applicability"] == "Keep this"
    assert saved["manual-current"]["customField"] == "Keep this too"
    assert saved["manual-previous"]["issuer"] == "Old issuer"
    assert saved["manual-previous"]["scope"] == "admin"


def test_unchanged_metadata_only_requests_index_repair():
    store = metadata_store()
    data = metadata_payload()
    data["meta"] = {"issuer": "Old issuer"}
    assert store.save_document(data)["status"] == "unchanged"
    store.run.assert_called_once()
    assert "INSERT INTO rag_index_jobs" in store.run.call_args.args[0]


@pytest.mark.parametrize("key,value", [("expectedId", "stale"), ("expectedMetaRevision", 9)])
def test_stale_metadata_is_rejected_without_writes(key, value):
    store = metadata_store()
    data = metadata_payload()
    data[key] = value
    with pytest.raises(ApiError) as error:
        store.save_document(data)
    assert error.value.status == 409
    store.run.assert_not_called()


@pytest.mark.parametrize("extra", [
    {"document": {"id": "manual", "sections": []}}, {"file": {}},
    {"meta": {"revision": 99}}, {"meta": {"status": "deleted"}},
    {"meta": {"scope": "invalid"}}, {"meta": {"issuer": None}},
    {"meta": {"issuedAt": "2026-02-30"}}, {"expectedMetaRevision": None},
    {"mode": "invalid"},
])
def test_metadata_rejects_body_file_unknown_fields_and_invalid_values(extra):
    store = metadata_store()
    with pytest.raises(ApiError) as error:
        store.save_document({**metadata_payload(), **extra})
    assert error.value.status == 400
    store.run.assert_not_called()


def content_payload():
    return {"document": {"id": "manual", "title": "Manual", "kind": "onboard", "version": "1",
            "reference": "Part 1", "reviewedAt": "2026-10-18", "language": "en",
            "sections": [{"page": 7, "heading": "Part 1", "text": "A real source sentence. " * 100}]},
            "meta": {"scope": "all", "status": "active"}}


def content_store(data, current=None):
    store = DocumentStore()
    revision_id = "manual-" + store._document_hash(data["document"])[:16]
    store.one = Mock(side_effect=lambda sql, params: current if "logical_id=%s AND active=true" in sql else None)
    store.all = Mock(return_value=[{"id": revision_id}])
    store.document_meta = Mock(return_value={"scope": "all", "revision": 0})
    store.run = Mock()
    return store


def test_new_source_is_preprocessed_once_and_saved_with_page_provenance(monkeypatch):
    data = content_payload()
    store = content_store(data)
    spy = Mock(wraps=documents.preprocess_sections)
    monkeypatch.setattr(documents, "preprocess_sections", spy)
    assert store.save_document(data)["status"] == "created"
    spy.assert_called_once_with(data["document"]["sections"])
    chunks = [c.args[1] for c in store.run.call_args_list if c.args[0].startswith("INSERT INTO chunks")]
    pages = [c.args[1] for c in store.run.call_args_list if c.args[0].startswith("INSERT INTO chunk_pages")]
    assert len(chunks) > 1 and len(pages) == len(chunks)
    assert all(len(c[-1]) <= 900 for c in chunks)
    assert all(p[1] == 7 for p in pages)


def test_empty_preprocessing_rejected_before_deactivating_previous_revision():
    data = content_payload()
    data["document"]["sections"] = [
        {"page": page, "heading": "Page", "text": "Part 6 Synthetic Manual"} for page in (1, 2, 3)]
    store = content_store(data, current={"id": "manual-previous", "hash": "previous"})
    with pytest.raises(ApiError) as error:
        store.save_document(data)
    assert error.value.status == 400
    assert "전처리 후" in str(error.value)
    store.run.assert_not_called()


def test_same_hash_keeps_existing_chunks_without_reprocessing(monkeypatch):
    data = content_payload()
    digest = DocumentStore._document_hash(data["document"])
    store = content_store(data, current={"id": "manual-" + digest[:16], "hash": digest})
    spy = Mock(side_effect=AssertionError("same hash must reuse chunks"))
    monkeypatch.setattr(documents, "preprocess_sections", spy)
    assert store.save_document(data)["status"] == "unchanged"
    spy.assert_not_called()
    assert not any("INSERT INTO chunks" in c.args[0] for c in store.run.call_args_list)
