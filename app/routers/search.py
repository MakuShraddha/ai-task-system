from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, DocumentChunk, Document
from app.schemas.schemas import SearchRequest, SearchResponse, SearchResult
from app.services.activity_service import log_activity
from app.services.search_service import get_search_service, VectorSearchService

router = APIRouter(prefix="/search", tags=["Search"])


@router.post("", response_model=SearchResponse)
def semantic_search(
    payload: SearchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    search_svc: VectorSearchService = Depends(get_search_service),
):
    """
    Semantic search over the knowledge base.

    1. Embeds the query using sentence-transformers.
    2. Queries FAISS for top-k similar chunks.
    3. Retrieves chunk text + document metadata from MySQL.
    4. Returns ranked results.
    """
    raw_results = search_svc.search(payload.query, top_k=payload.top_k)

    results: list[SearchResult] = []
    for hit in raw_results:
        chunk = db.query(DocumentChunk).filter(
            DocumentChunk.id == hit["chunk_db_id"]
        ).first()
        if not chunk:
            continue

        doc = db.query(Document).filter(Document.id == hit["document_id"]).first()
        if not doc:
            continue

        results.append(
            SearchResult(
                document_id=doc.id,
                document_title=doc.title,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                score=round(hit["score"], 4),
            )
        )

    # Log the search action (tracks query for analytics)
    log_activity(
        db,
        action="search",
        user_id=current_user.id,
        detail={"query": payload.query, "results_count": len(results)},
        ip_address=request.client.host,
    )

    return SearchResponse(
        query=payload.query,
        results=results,
        total_results=len(results),
    )
