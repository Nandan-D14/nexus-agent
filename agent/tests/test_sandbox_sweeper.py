from datetime import datetime, timedelta, timezone

import pytest

import nexus.sandbox as sandbox_module
from nexus.sandbox import SandboxSweeper


class _FakeSandbox:
    killed: list[str] = []

    def __init__(self, sid: str) -> None:
        self.sid = sid

    @classmethod
    def connect(cls, sid, api_key=None):
        return cls(sid)

    def kill(self) -> None:
        _FakeSandbox.killed.append(self.sid)


@pytest.fixture(autouse=True)
def _fake_e2b(monkeypatch):
    import e2b_desktop

    _FakeSandbox.killed = []
    monkeypatch.setattr(e2b_desktop, "Sandbox", _FakeSandbox)


def _running(**ages_minutes):
    now = datetime.now(timezone.utc)

    async def fake(e2b_api_key=""):
        return {
            sid: (None if age is None else now - timedelta(minutes=age))
            for sid, age in ages_minutes.items()
        }

    return fake


@pytest.mark.asyncio
async def test_sweep_aborts_when_active_ids_cannot_be_loaded(monkeypatch) -> None:
    class FailingRepo:
        async def list_all_active_sandbox_ids(self):
            raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(sandbox_module, "list_running_e2b_sandboxes", _running(orphan=120))

    killed = await SandboxSweeper(FailingRepo(), e2b_api_key="k").sweep()

    assert killed == 0
    assert _FakeSandbox.killed == []


@pytest.mark.asyncio
async def test_sweep_only_kills_old_unowned_sandboxes(monkeypatch) -> None:
    class Repo:
        async def list_all_active_sandbox_ids(self):
            return ["owned"]

    monkeypatch.setattr(
        sandbox_module,
        "list_running_e2b_sandboxes",
        _running(owned=120, orphan=120, provisioning=2, undated=None),
    )

    killed = await SandboxSweeper(Repo(), e2b_api_key="k").sweep()

    assert killed == 1
    assert _FakeSandbox.killed == ["orphan"]
