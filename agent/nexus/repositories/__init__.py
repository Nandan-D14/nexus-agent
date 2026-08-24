# Proprietary and non-commercial use only.

"""Focused Firestore repositories extracted from the history god object.

Each repository owns one concern and subclasses
:class:`nexus._firestore_base.FirestoreRepoBase`. The
:class:`nexus.history_repository.FirestoreHistoryRepository` facade composes
them and delegates via ``__getattr__`` so existing call sites are unchanged.
"""

from nexus.repositories.audit_repository import AuditRepository
from nexus.repositories.integration_repository import IntegrationRepository
from nexus.repositories.sandbox_state_repository import SandboxStateRepository
from nexus.repositories.user_repository import UserRepository
from nexus.repositories.workflow_template_repository import WorkflowTemplateRepository

__all__ = [
    "AuditRepository",
    "IntegrationRepository",
    "SandboxStateRepository",
    "UserRepository",
    "WorkflowTemplateRepository",
]
