from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, require_admin
from app.models.user import User, Task, TaskStatus, TaskPriority
from app.schemas.schemas import TaskCreate, TaskUpdate, TaskOut
from app.services.activity_service import log_activity

router = APIRouter(prefix="/tasks", tags=["Tasks"])


# ─────────────────────────────────────────
# GET /tasks  (with dynamic filtering)
# ─────────────────────────────────────────

@router.get("", response_model=List[TaskOut])
def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority"),
    assigned_to: Optional[int] = Query(None, description="Filter by assignee user ID"),
    created_by: Optional[int] = Query(None, description="Filter by creator user ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List tasks with optional dynamic filters.

    Examples:
      GET /tasks?status=completed
      GET /tasks?assigned_to=1
      GET /tasks?status=pending&priority=high
    """
    query = db.query(Task)

    # Regular users only see tasks assigned to them OR created by them
    if current_user.role.name != "admin":
        query = query.filter(
            (Task.assigned_to == current_user.id) | (Task.created_by == current_user.id)
        )

    if status:
        query = query.filter(Task.status == status)
    if priority:
        query = query.filter(Task.priority == priority)
    if assigned_to is not None:
        query = query.filter(Task.assigned_to == assigned_to)
    if created_by is not None:
        query = query.filter(Task.created_by == created_by)

    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return tasks


# ─────────────────────────────────────────
# GET /tasks/{id}
# ─────────────────────────────────────────

@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _get_task_or_404(task_id, db)
    _check_task_access(task, current_user)

    log_activity(
        db,
        action="task_view",
        user_id=current_user.id,
        entity_type="task",
        entity_id=task.id,
        ip_address=request.client.host,
    )
    return task


# ─────────────────────────────────────────
# POST /tasks  (admin only)
# ─────────────────────────────────────────

@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskCreate,
    request: Request,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Admin creates a task and optionally assigns it to a user."""
    if payload.assigned_to:
        assignee = db.query(User).filter(User.id == payload.assigned_to).first()
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee user not found")

    task = Task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_date=payload.due_date,
        assigned_to=payload.assigned_to,
        created_by=current_user.id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    log_activity(
        db,
        action="task_create",
        user_id=current_user.id,
        entity_type="task",
        entity_id=task.id,
        detail={"title": task.title, "assigned_to": payload.assigned_to},
        ip_address=request.client.host,
    )
    return task


# ─────────────────────────────────────────
# PATCH /tasks/{id}
# ─────────────────────────────────────────

@router.patch("/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update task fields.
    - Admin can update anything.
    - Regular users can ONLY update status (e.g. pending → completed).
    """
    task = _get_task_or_404(task_id, db)
    _check_task_access(task, current_user)

    if current_user.role.name != "admin":
        # Users may only flip the status on their own assigned tasks
        if task.assigned_to != current_user.id:
            raise HTTPException(status_code=403, detail="You can only update tasks assigned to you")
        allowed = {"status"}
        provided = {k for k, v in payload.model_dump().items() if v is not None}
        forbidden = provided - allowed
        if forbidden:
            raise HTTPException(
                status_code=403,
                detail=f"Users can only update: {allowed}. Forbidden fields: {forbidden}",
            )

    changes = {}
    for field, value in payload.model_dump(exclude_none=True).items():
        if hasattr(task, field):
            setattr(task, field, value)
            changes[field] = str(value)

    db.commit()
    db.refresh(task)

    log_activity(
        db,
        action="task_update",
        user_id=current_user.id,
        entity_type="task",
        entity_id=task.id,
        detail={"changes": changes},
        ip_address=request.client.host,
    )
    return task


# ─────────────────────────────────────────
# DELETE /tasks/{id}  (admin only)
# ─────────────────────────────────────────

@router.delete("/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    task = _get_task_or_404(task_id, db)
    db.delete(task)
    db.commit()


# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def _get_task_or_404(task_id: int, db: Session) -> Task:
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _check_task_access(task: Task, user: User):
    if user.role.name == "admin":
        return
    if task.assigned_to != user.id and task.created_by != user.id:
        raise HTTPException(status_code=403, detail="Access denied to this task")
