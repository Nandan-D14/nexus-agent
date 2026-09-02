# Copyright (c) 2026 Agentic Company. All rights reserved.
# Proprietary and non-commercial use only.

from nexus.history_repository import slim_message_attachments


def test_slim_message_attachments_keeps_stable_fields_only() -> None:
    slim = slim_message_attachments(
        [
            {
                "name": "brief.docx",
                "path": "sources/uploads/brief.docx",
                "artifact_id": "art_1",
                "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size": 12,
                "previewUrl": "blob:http://localhost/abc",
                "drive_file_id": "drive-1",
            },
            {"foo": "bar"},
            "nope",
        ]
    )
    assert slim == [
        {
            "name": "brief.docx",
            "path": "sources/uploads/brief.docx",
            "artifact_id": "art_1",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": 12,
        }
    ]


def test_slim_message_attachments_empty_and_limit() -> None:
    assert slim_message_attachments(None) == []
    assert slim_message_attachments([]) == []
    items = slim_message_attachments(
        [{"name": f"f{i}.txt", "path": f"p{i}"} for i in range(20)],
        limit=3,
    )
    assert len(items) == 3
    assert items[0]["name"] == "f0.txt"
