# Copyright (c) 2026 nandan-d14. All rights reserved.
# Proprietary and non-commercial use only.

"""Pinned ADK capability probes used for migration decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import importlib.util
from importlib.metadata import version


@dataclass(frozen=True)
class AdkTaskApiAssessment:
    adk_version: str
    available: bool
    task_mode_available: bool
    task_package_exports: tuple[str, ...]
    public_module: str
    public_symbols: tuple[str, ...]
    decision: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def assess_adk_task_api() -> AdkTaskApiAssessment:
    """Detect a public durable Task API without relying on private symbols."""
    installed_version = version("google-adk")
    try:
        from google.adk.agents import LlmAgent

        mode_annotation = str(LlmAgent.model_fields["mode"].annotation)
        task_mode_available = "task" in mode_annotation
    except (ImportError, KeyError, AttributeError):
        task_mode_available = False
    try:
        task_package = importlib.import_module(
            "google.adk.agents.llm.task"
        )
        task_package_exports = tuple(
            sorted(
                name
                for name in dir(task_package)
                if not name.startswith("_")
            )
        )
    except ImportError:
        task_package_exports = ()
    candidates = (
        "google.adk.tasks",
        "google.adk.task",
        "google.adk.task_api",
    )
    required_symbol_sets = (
        {"Task", "TaskService"},
        {"Task", "TaskManager"},
        {"TaskHandle", "TaskService"},
    )
    for module_name in candidates:
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, ModuleNotFoundError, AttributeError):
            spec = None
        if spec is None:
            continue
        module = importlib.import_module(module_name)
        public_symbols = tuple(
            sorted(name for name in dir(module) if not name.startswith("_"))
        )
        symbol_set = set(public_symbols)
        if any(required <= symbol_set for required in required_symbol_sets):
            return AdkTaskApiAssessment(
                adk_version=installed_version,
                available=True,
                task_mode_available=task_mode_available,
                task_package_exports=task_package_exports,
                public_module=module_name,
                public_symbols=public_symbols,
                decision="evaluate_behind_adapter",
                reason=(
                    "A public task lifecycle surface is present; evaluate it "
                    "against repository leases, approvals, checkpoints, and "
                    "Cloud Tasks semantics before migration."
                ),
            )
    return AdkTaskApiAssessment(
        adk_version=installed_version,
        available=False,
        task_mode_available=task_mode_available,
        task_package_exports=task_package_exports,
        public_module="",
        public_symbols=(),
        decision="defer",
        reason=(
            f"google-adk {installed_version} exposes Workflow nodes and "
            "in-session LlmAgent task mode, but no public durable "
            "Task/TaskService lifecycle API. Keep repository-owned durable "
            "execution and reassess on an explicitly tested ADK upgrade."
        ),
    )


__all__ = ["AdkTaskApiAssessment", "assess_adk_task_api"]
