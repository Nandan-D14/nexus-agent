# Proprietary and non-commercial use only.

"""Base for sandbox components bound to an owning SandboxManager.

Components share the manager's mutable state (``_sandbox``, ``_stream_url``,
``_e2b_api_key``, ``_chromium_cdp_lock``) via property proxies so writes (e.g.
the dead-sandbox reset in ``screenshot``) land on the manager, and forward any
other missing attribute (methods like ``run_command`` / ``_require_sandbox``)
to the manager through ``__getattr__``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from nexus.sandbox import SandboxManager


class SandboxComponent:
    """A concern extracted from SandboxManager, bound to the owning manager."""

    def __init__(self, owner: "SandboxManager") -> None:
        self._owner = owner

    # --- shared mutable state (read/write proxied to the owner) -----------
    @property
    def _sandbox(self):
        return self._owner._sandbox

    @_sandbox.setter
    def _sandbox(self, value) -> None:
        self._owner._sandbox = value

    @property
    def _stream_url(self) -> Optional[str]:
        return self._owner._stream_url

    @_stream_url.setter
    def _stream_url(self, value: Optional[str]) -> None:
        self._owner._stream_url = value

    @property
    def _e2b_api_key(self):
        return self._owner._e2b_api_key

    @property
    def _chromium_cdp_lock(self):
        return self._owner._chromium_cdp_lock

    # --- forward everything else (methods) to the owning manager ----------
    def __getattr__(self, name: str):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        owner = self.__dict__.get("_owner")
        if owner is None:
            raise AttributeError(name)
        return getattr(owner, name)
