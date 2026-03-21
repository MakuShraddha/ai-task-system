from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, create_access_token, get_current_user
from app.models.user import User
from app.schemas.schemas import LoginRequest, TokenResponse
from app.services.activity_service import log_activity

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """Authenticate a user and return a JWT access token."""
    user = db.query(User).filter(
        (User.username == payload.username) | (User.email == payload.username)
    ).first()

    if not user or not verify_password(payload.password, user.hashed_password):
        log_activity(
            db,
            action="login_failed",
            detail={"username": payload.username},
            ip_address=request.client.host,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    token = create_access_token({"sub": str(user.id), "role": user.role.name})

    log_activity(
        db,
        action="login",
        user_id=user.id,
        detail={"username": user.username},
        ip_address=request.client.host,
    )

    return TokenResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        role=user.role.name,
    )


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    """Return information about the currently authenticated user."""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.name,
        "is_active": current_user.is_active,
    }
