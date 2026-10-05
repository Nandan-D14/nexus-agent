"""Regression tests for backend performance / resource-bound fixes (Phase 4)."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@dataclass
class _Decision:
    index: int


@pytest.mark.asyncio
async def test_guarded_write_releases_per_key_locks(monkeypatch) -> None:
    from nexus import firestore_concurrency

    monkeypatch.setattr(firestore_concurrency.settings, "serialize_session_writes", True)
    for i in range(100):
        async with firestore_concurrency.guarded_write(f"session-{i}"):
            pass
    assert firestore_concurrency._write_locks == {}


def test_ledger_serialization_can_be_capped() -> None:
    from nexus.control_loop import ActionLedger

    ledger = ActionLedger()
    ledger.records = [
        SimpleNamespace(turn_index=i, decision=_Decision(i), observation=None) for i in range(120)
    ]
    capped = ledger.to_dict(max_records=50)
    assert len(capped["records"]) == 50
    assert capped["records"][-1]["turn_index"] == 119
    assert capped["truncated_records"] == 70
    assert "truncated_records" not in ledger.to_dict()


def test_export_redacts_credentials() -> None:
    from nexus.repositories.audit_repository import _redact

    exported = _redact(
        {
            "userPrivate": {"byok": {"llmApiKey": "enc"}, "googleDriveRefreshToken": "t", "name": "keep"},
            "sessions": [{"runs": [{"artifacts": [{"token": "x", "title": "ok"}]}]}],
        }
    )
    assert exported["userPrivate"]["byok"] == "[redacted]"
    assert exported["userPrivate"]["googleDriveRefreshToken"] == "[redacted]"
    assert exported["userPrivate"]["name"] == "keep"
    assert exported["sessions"][0]["runs"][0]["artifacts"][0] == {"token": "[redacted]", "title": "ok"}


def test_run_id_query_param_rejects_traversal() -> None:
    from nexus.routers import files

    assert files._validated_run_id("run_abc-123") == "run_abc-123"
    assert files._validated_run_id(None) is None
    for bad in ("../../etc", "a/b", "", "x" * 65):
        with pytest.raises(HTTPException):
            files._validated_run_id(bad)


def test_unicode_filenames_survive_and_header_is_encoded() -> None:
    from nexus.routers import files

    assert files._safe_workspace_relative_path("outputs/résumé.pdf") == "outputs/résumé.pdf"
    header = files._content_disposition("inline", "résumé.pdf")
    assert 'filename="rsum.pdf"' in header
    assert "filename*=UTF-8''r%C3%A9sum%C3%A9.pdf" in header


def test_artifact_content_header_is_latin1_safe() -> None:
    """Artifact titles like 'Alex Chen — Product Designer' crashed the preview."""
    from starlette.responses import Response

    from nexus.http_headers import content_disposition

    header = content_disposition("inline", 'Alex Chen — "Designer".html')
    header.encode("latin-1")  # Starlette's header encoding; must not raise
    assert 'filename="Alex Chen  Designer.html"' in header
    assert "filename*=UTF-8''Alex%20Chen%20%E2%80%94%20%22Designer%22.html" in header
    Response(content=b"x", headers={"Content-Disposition": header})


@pytest.mark.asyncio
async def test_upload_read_is_capped() -> None:
    from nexus.routers import files

    class FakeUpload:
        def __init__(self, size: int) -> None:
            self._remaining = size

        async def read(self, n: int) -> bytes:
            chunk = min(n, self._remaining)
            self._remaining -= chunk
            return b"x" * chunk

    assert len(await files._read_upload_capped(FakeUpload(10), max_bytes=100)) == 10
    with pytest.raises(HTTPException) as exc:
        await files._read_upload_capped(FakeUpload(5 * 1024 * 1024), max_bytes=1024 * 1024)
    assert exc.value.status_code == 413


def test_session_listing_stops_at_limit(monkeypatch) -> None:
    from nexus.history_repository import FirestoreHistoryRepository

    repo = FirestoreHistoryRepository.__new__(FirestoreHistoryRepository)
    yielded: list[str] = []

    def fake_iter(owner_id):
        for i in range(1000):
            yielded.append(f"s{i}")
            yield f"s{i}", {"status": "ended", "title": f"t{i}"}

    monkeypatch.setattr(repo, "_iter_owner_sessions_by_recency_sync", fake_iter, raising=False)
    monkeypatch.setattr(repo, "_build_stored_session", lambda sid, data: SimpleNamespace(session_id=sid), raising=False)

    sessions = repo._list_sessions_sync("owner", 10, None, None)

    assert [s.session_id for s in sessions] == [f"s{i}" for i in range(10)]
    assert len(yielded) == 10
