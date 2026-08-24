# Proprietary and non-commercial use only.

"""Focused components extracted from the SandboxManager god object.

Each component owns one concern (display, input, files, browser) and is bound
to the owning :class:`nexus.sandbox.SandboxManager`. The manager keeps the
sandbox handle, lifecycle, ``run_command`` and ``_require_sandbox``; components
proxy shared state and cross-concern calls back to it via
:class:`SandboxComponent`.
"""

from nexus.sandbox_components.browser import SandboxBrowser
from nexus.sandbox_components.display import SandboxDisplay
from nexus.sandbox_components.files import SandboxFiles
from nexus.sandbox_components.input import SandboxInput

__all__ = [
    "SandboxBrowser",
    "SandboxDisplay",
    "SandboxFiles",
    "SandboxInput",
]
