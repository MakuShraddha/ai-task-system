"""
Task Notes Router
Allows both admin and user to add/view notes on tasks.
Stored in activity_logs with action='task_note'.
"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Task, ActivityLog
from app.services.activity_service import log_activity

router = APIRouter(prefix="/tasks", tags=["Task Notes"])


class NoteCreate(BaseModel):
    note: str


class NoteOut(BaseModel):
    id: int
    user_id: int
    username: str
    note: str
    created_at: str

    model_config = {"from_attributes": True}


@router.post("/{task_id}/notes", status_code=201)
def add_note(
    task_id: int,
    payload: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a note to a task. Both admin and user can add notes."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Users can only note tasks assigned to them or created by them
    if current_user.role.name != "admin":
        if task.assigned_to != current_user.id and task.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

    note_text = payload.note.strip()
    if not note_text:
        raise HTTPException(status_code=400, detail="Note cannot be empty")

    entry = log_activity(
        db,
        action="task_note",
        user_id=current_user.id,
        entity_type="task",
        entity_id=task_id,
        detail={"note": note_text, "username": current_user.username},
    )
    return {
        "id": entry.id,
        "user_id": current_user.id,
        "username": current_user.username,
        "note": note_text,
        "created_at": entry.created_at.isoformat() if entry.created_at else "",
    }


@router.get("/{task_id}/notes")
def get_notes(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all notes for a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    logs = (
        db.query(ActivityLog)
        .filter(ActivityLog.action == "task_note", ActivityLog.entity_id == task_id)
        .order_by(ActivityLog.created_at.asc())
        .all()
    )

    notes = []
    for log in logs:
        detail = {}
        if log.detail:
            try:
                detail = json.loads(log.detail)
            except Exception:
                pass
        notes.append({
            "id": log.id,
            "user_id": log.user_id,
            "username": detail.get("username", "Unknown"),
            "note": detail.get("note", ""),
            "created_at": log.created_at.isoformat() if log.created_at else "",
        })
    return notes
