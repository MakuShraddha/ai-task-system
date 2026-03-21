from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
from app.models.user import TaskStatus, TaskPriority


# ─────────────────────────────────────────
# Auth Schemas
# ─────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    username: str
    role: str


# ─────────────────────────────────────────
# User Schemas
# ─────────────────────────────────────────

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: str = "user"   # "admin" | "user"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "user"):
            raise ValueError("role must be 'admin' or 'user'")
        return v


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str]
    is_active: bool
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserOutNested(BaseModel):
    """Minimal user info used inside other responses."""
    id: int
    username: str
    full_name: Optional[str]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────
# Task Schemas
# ─────────────────────────────────────────

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.medium
    due_date: Optional[datetime] = None
    assigned_to: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    assigned_to: Optional[int] = None


class TaskOut(BaseModel):
    id: int
    title: str
    description: Optional[str]
    status: TaskStatus
    priority: TaskPriority
    due_date: Optional[datetime]
    assigned_to: Optional[int]
    created_by: int
    assignee: Optional[UserOutNested]
    creator: Optional[UserOutNested]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────
# Document Schemas
# ─────────────────────────────────────────

class DocumentOut(BaseModel):
    id: int
    title: str
    filename: str
    file_type: str
    file_size: int
    content_preview: Optional[str]
    chunk_count: int
    is_indexed: bool
    uploaded_by: int
    uploader: Optional[UserOutNested]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────
# Search Schemas
# ─────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5

    @field_validator("top_k")
    @classmethod
    def validate_top_k(cls, v):
        return max(1, min(v, 20))


class SearchResult(BaseModel):
    document_id: int
    document_title: str
    chunk_index: int
    chunk_text: str
    score: float


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_results: int


# ─────────────────────────────────────────
# Activity Log Schemas
# ─────────────────────────────────────────

class ActivityLogOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    detail: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────
# Analytics Schemas
# ─────────────────────────────────────────

class TaskStats(BaseModel):
    total: int
    pending: int
    in_progress: int
    completed: int


class SearchQueryStat(BaseModel):
    query: str
    count: int


class AnalyticsResponse(BaseModel):
    task_stats: TaskStats
    total_documents: int
    total_users: int
    top_search_queries: List[SearchQueryStat]
    recent_activity_count: int
