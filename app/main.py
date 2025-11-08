import logging
from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select, Session
from starlette.concurrency import run_in_threadpool

from starlette import status as ws_status
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketState

from app.api.channels import channel_router
from app.api.messages import messages_router
from app.api.users import router as user_router
from app.auth import create_access_token, authenticate_user, get_current_user_from_query
from app.config import settings
from app.db.session import create_db_and_tables, get_session
from app.schemas.token import Token
from app.models.models import Membership, User
from app.websockets_manger import manager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up the FastAPI application...")
    # This synchronous call might block if DB init is slow,threadpool is needed
    await run_in_threadpool(create_db_and_tables)
    yield
    print("Shutting down the FastAPI application...")


app = FastAPI(lifespan=lifespan, title="Chat Application", version="0.1.2")

# Include Routers
app.include_router(user_router)
app.include_router(channel_router)
app.include_router(messages_router)

allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://dlp2zfvdxkrys.cloudfront.net",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"message": "Welcome to the Chat API"}


# --- WebSocket Endpoint ---
@app.websocket("/ws/{channel_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: int,
    current_user: User = Depends(get_current_user_from_query),
    session: Session = Depends(get_session),
):
    """Handles WebSocket connections for real-time chat in a channel."""
    logger.info(
        f"WS connection attempt by user '{current_user.username}' (ID: {current_user.id}) for channel {channel_id}"
    )

    # --- Authorization Check ---
    def check_membership_sync():
        return session.exec(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.channel_id == channel_id,
            )
        ).first()

    try:
        membership_check = await run_in_threadpool(check_membership_sync)
    except Exception as db_err:
        logger.error(
            f"Database error during WS auth for user '{current_user.username}', channel {channel_id}: {db_err}",
            exc_info=True,
        )
        await websocket.close(
            code=ws_status.WS_1011_INTERNAL_ERROR, reason="Authorization check failed"
        )
        return

    if not membership_check:
        logger.warning(
            f"WS auth failed: User '{current_user.username}' not member of channel {channel_id}"
        )
        await websocket.close(
            code=ws_status.WS_1008_POLICY_VIOLATION,
            reason="Not authorized for this channel",
        )
        return

    # --- Connect user to the manager ---
    await manager.connect(channel_id, websocket)

    try:
        # --- Keep connection alive and listen for messages ---
        while True:
            data = await websocket.receive_text()
            logger.debug(
                f"Received WS text from user '{current_user.username}' on channel {channel_id}: {data}"
            )

    except WebSocketDisconnect as e:
        logger.info(
            f"WS disconnected gracefully: user '{current_user.username}', channel {channel_id}. Code: {e.code}"
        )
    except Exception as e:
        # Catch unexpected errors during the receive loop
        logger.error(
            f"Unexpected error in WS connection for user '{current_user.username}', channel {channel_id}: {e}",
            exc_info=True,
        )
        try:
            # Attempt to close with an error code if not already closed
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close(code=ws_status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
            logger.warning(
                f"WS already closed for user '{current_user.username}', channel {channel_id} during error handling."
            )
            pass  # WebSocket might already be closed
    finally:
        # --- Clean up connection ---
        manager.disconnect(channel_id, websocket)
        logger.info(
            f"Cleaned up WS connection for user '{current_user.username}', channel {channel_id}"
        )


# --- Token Endpoint ---
@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),  # Ensure Session type hint is correct
):
    """Handles user login and returns JWT access token."""
    # --- Run synchronous authentication in threadpool ---
    user = await run_in_threadpool(
        authenticate_user, form_data.username, form_data.password, session
    )
    # --- End threadpool execution ---

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # Use status from fastapi
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


if __name__ == "__main__":
    # Use reload=True for development, remove for production
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
