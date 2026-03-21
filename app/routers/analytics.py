import json
from collections import Counter
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, Task, Document, ActivityLog, TaskStatus
from app.schemas.schemas import AnalyticsResponse, TaskStats, SearchQueryStat

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("", response_model=AnalyticsResponse)
def get_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns:
    - Task stats (total, pending, in_progress, completed)
    - Total documents
    - Total users
    - Top 10 search queries
    - Activity count in the last 24 hours
    """
    # ── Task stats ─────────────────────────────────────────────────────────
    task_counts = (
        db.query(Task.status, func.count(Task.id))
        .group_by(Task.status)
        .all()
    )
    status_map = {row[0]: row[1] for row in task_counts}
    task_stats = TaskStats(
        total=sum(status_map.values()),
        pending=status_map.get(TaskStatus.pending, 0),
        in_progress=status_map.get(TaskStatus.in_progress, 0),
        completed=status_map.get(TaskStatus.completed, 0),
    )

    # ── Document & user counts ─────────────────────────────────────────────
    total_docs = db.query(func.count(Document.id)).scalar()
    total_users = db.query(func.count(User.id)).scalar()

    # ── Top search queries ─────────────────────────────────────────────────
    search_logs = (
        db.query(ActivityLog.detail)
        .filter(ActivityLog.action == "search")
        .order_by(ActivityLog.created_at.desc())
        .limit(500)
        .all()
    )
    query_counter: Counter = Counter()
    for (detail_str,) in search_logs:
        if detail_str:
            try:
                detail = json.loads(detail_str)
                q = detail.get("query", "").strip()
                if q:
                    query_counter[q] += 1
            except (json.JSONDecodeError, AttributeError):
                pass

    top_queries = [
        SearchQueryStat(query=q, count=c)
        for q, c in query_counter.most_common(10)
    ]

    # ── Recent activity (last 24 h) ────────────────────────────────────────
    since = datetime.utcnow() - timedelta(hours=24)
    recent_count = (
        db.query(func.count(ActivityLog.id))
        .filter(ActivityLog.created_at >= since)
        .scalar()
    )

    return AnalyticsResponse(
        task_stats=task_stats,
        total_documents=total_docs,
        total_users=total_users,
        top_search_queries=top_queries,
        recent_activity_count=recent_count,
    )
