# Proprietary and non-commercial use only.

"""Workflow template persistence."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from firebase_admin import firestore

from nexus._firestore_base import FirestoreRepoBase
from nexus.history_models import StoredWorkflowTemplate, utcnow


class WorkflowTemplateRepository(FirestoreRepoBase):
    """CRUD for reusable workflow templates under ``users/{uid}/workflowTemplates``."""

    async def create_workflow_template(
        self,
        *,
        owner_id: str,
        source_session_id: str | None,
        source_run_id: str | None,
        name: str,
        description: str,
        instructions: str,
        input_fields: list[dict[str, Any]],
        source_artifacts: list[str],
        status: str = "published",
    ) -> StoredWorkflowTemplate:
        return await asyncio.to_thread(
            self._create_workflow_template_sync,
            owner_id,
            source_session_id,
            source_run_id,
            name,
            description,
            instructions,
            input_fields,
            source_artifacts,
            status,
        )

    async def list_workflow_templates(
        self,
        owner_id: str,
        *,
        limit: int = 100,
        search: str | None = None,
    ) -> list[StoredWorkflowTemplate]:
        return await asyncio.to_thread(
            self._list_workflow_templates_sync,
            owner_id,
            limit,
            search,
        )

    async def get_workflow_template(
        self,
        owner_id: str,
        template_id: str,
    ) -> StoredWorkflowTemplate | None:
        return await asyncio.to_thread(
            self._get_workflow_template_sync,
            owner_id,
            template_id,
        )

    async def update_workflow_template(
        self,
        *,
        owner_id: str,
        template_id: str,
        name: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        input_fields: list[dict[str, Any]] | None = None,
        status: str | None = None,
    ) -> StoredWorkflowTemplate | None:
        return await asyncio.to_thread(
            self._update_workflow_template_sync,
            owner_id,
            template_id,
            name,
            description,
            instructions,
            input_fields,
            status,
        )

    async def delete_workflow_template(
        self,
        owner_id: str,
        template_id: str,
    ) -> bool:
        return await asyncio.to_thread(
            self._delete_workflow_template_sync,
            owner_id,
            template_id,
        )

    async def mark_workflow_template_used(
        self,
        owner_id: str,
        template_id: str,
    ) -> StoredWorkflowTemplate | None:
        return await asyncio.to_thread(
            self._mark_workflow_template_used_sync,
            owner_id,
            template_id,
        )

    def _workflow_templates_collection_ref(self, owner_id: str):
        return self._db.collection("users").document(owner_id).collection("workflowTemplates")

    def _create_workflow_template_sync(
        self,
        owner_id: str,
        source_session_id: str | None,
        source_run_id: str | None,
        name: str,
        description: str,
        instructions: str,
        input_fields: list[dict[str, Any]],
        source_artifacts: list[str],
        status: str = "published",
    ) -> StoredWorkflowTemplate:
        now = utcnow()
        template_id = uuid.uuid4().hex[:12]
        payload: dict[str, Any] = {
            "ownerId": owner_id,
            "name": name,
            "description": description,
            "instructions": instructions,
            "inputFields": input_fields,
            "sourceArtifacts": source_artifacts,
            "status": "draft" if status == "draft" else "published",
            "createdAt": now,
            "updatedAt": now,
        }
        if source_session_id:
            payload["sourceSessionId"] = source_session_id
        if source_run_id:
            payload["sourceRunId"] = source_run_id
        self._workflow_templates_collection_ref(owner_id).document(template_id).set(payload)
        return self._build_stored_workflow_template(template_id, payload)

    def _list_workflow_templates_sync(
        self,
        owner_id: str,
        limit: int,
        search: str | None,
    ) -> list[StoredWorkflowTemplate]:
        docs = (
            self._workflow_templates_collection_ref(owner_id)
            .order_by("updatedAt", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        templates = [
            self._build_stored_workflow_template(doc.id, doc.to_dict() or {})
            for doc in docs
        ]
        if search:
            search_lower = search.strip().lower()
            if search_lower:
                templates = [
                    template
                    for template in templates
                    if search_lower in template.name.lower()
                    or search_lower in template.description.lower()
                    or search_lower in template.instructions.lower()
                ]
        return templates

    def _get_workflow_template_sync(
        self,
        owner_id: str,
        template_id: str,
    ) -> StoredWorkflowTemplate | None:
        doc = self._workflow_templates_collection_ref(owner_id).document(template_id).get()
        if not doc.exists:
            return None
        return self._build_stored_workflow_template(doc.id, doc.to_dict() or {})

    def _update_workflow_template_sync(
        self,
        owner_id: str,
        template_id: str,
        name: str | None,
        description: str | None,
        instructions: str | None,
        input_fields: list[dict[str, Any]] | None,
        status: str | None,
    ) -> StoredWorkflowTemplate | None:
        ref = self._workflow_templates_collection_ref(owner_id).document(template_id)
        doc = ref.get()
        if not doc.exists:
            return None
        updates: dict[str, Any] = {
            "updatedAt": utcnow(),
        }
        if name is not None:
            updates["name"] = name
        if description is not None:
            updates["description"] = description
        if instructions is not None:
            updates["instructions"] = instructions
        if input_fields is not None:
            updates["inputFields"] = input_fields
        if status is not None:
            updates["status"] = "draft" if status == "draft" else "published"
        ref.set(updates, merge=True)
        merged = {**(doc.to_dict() or {}), **updates}
        return self._build_stored_workflow_template(template_id, merged)

    def _delete_workflow_template_sync(
        self,
        owner_id: str,
        template_id: str,
    ) -> bool:
        ref = self._workflow_templates_collection_ref(owner_id).document(template_id)
        doc = ref.get()
        if not doc.exists:
            return False
        before_data = doc.to_dict()
        ref.delete()
        self._create_audit_log_sync(
            actor_uid=owner_id,
            action="template_delete",
            target_uid=owner_id,
            before=before_data,
            after=None
        )
        return True

    def _mark_workflow_template_used_sync(
        self,
        owner_id: str,
        template_id: str,
    ) -> StoredWorkflowTemplate | None:
        ref = self._workflow_templates_collection_ref(owner_id).document(template_id)
        doc = ref.get()
        if not doc.exists:
            return None
        now = utcnow()
        ref.set({"lastUsedAt": now, "updatedAt": now}, merge=True)
        merged = {**(doc.to_dict() or {}), "lastUsedAt": now, "updatedAt": now}
        return self._build_stored_workflow_template(template_id, merged)
