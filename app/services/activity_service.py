"""
Activity Logging Service
Tracks: login, task_update, document_upload, search
"""
import json
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import ActivityLog


def log_activity(
    db: Session,
    action: str,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> ActivityLog:
    """
    Persist an activity log entry to the database.

    Actions used in this system:
        login, logout, task_create, task_update, task_view,
        document_upload, document_view, search
    """
    entry = ActivityLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        detail=json.dumps(detail) if detail else None,
        ip_address=ip_address,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
