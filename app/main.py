from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import select, Session
from starlette.concurrency import run_in_threadpool

from starlette import status as ws_status

from app.api.channels import channel_router
from app.api.messages import messages_router
from app.api.users import router as user_router
from app.auth import create_access_token, authenticate_user, get_current_user_from_query
from app.config import settings
from app.db.session import create_db_and_tables, get_session
from app.schemas.token import Token
from app.models.models import Membership, User
from app.websockets_manger import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up the FastAPI application...")
    # This synchronous call might block if DB init is slow,threadpool is needed
    await run_in_threadpool(create_db_and_tables)
    yield
    print("Shutting down the FastAPI application...")

app = FastAPI(lifespan=lifespan, title="Chat Application", version="0.1.2")

# Include Routers
app.include_router(user_router, prefix="/users", tags=["users"]) # Add prefix/tags
app.include_router(channel_router, prefix="/channels", tags=["channels"])
app.include_router(messages_router, prefix="/messages", tags=["messages"])

@app.get("/")
async def root():
    return {"message": "Welcome to the Chat API"}


# --- WebSocket Endpoint ---
@app.websocket("/ws/{channel_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: int,
    current_user: User = Depends(get_current_user_from_query), # Auth via query token
    session: Session = Depends(get_session)
):
    """Handles WebSocket connections for real-time chat in a channel."""

    # --- Authorization Check (using threadpool for sync DB call) ---
    def check_membership_sync():
        return session.exec(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.channel_id == channel_id
            )
        ).first()

    membership_check = await run_in_threadpool(check_membership_sync)

    if not membership_check:
        print(f"Auth failed for WS connection: User '{current_user.username}' not member of channel {channel_id}")
        await websocket.close(code=ws_status.WS_1008_POLICY_VIOLATION, reason="Not authorized for this channel")
        return

    # Connect user to the manager
    await manager.connect(channel_id, websocket)
    print(f"User '{current_user.username}' (ID: {current_user.id}) connected via WebSocket to channel {channel_id}")

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Process incoming data if needed (e.g., ping/pong, typing indicators)
            print(f"Received text via WS from {current_user.username} on channel {channel_id}: {data} (discarding)")

    except WebSocketDisconnect as e:
        print(f"WebSocket disconnected for user '{current_user.username}' on channel {channel_id}. Code: {e.code}")
    except Exception as e:
        print(f"Error in WebSocket connection for user '{current_user.username}' on channel {channel_id}: {e}")
        try:
             await websocket.close(code=ws_status.WS_1011_INTERNAL_ERROR)
        except RuntimeError:
             # WebSocket might already be closed
             pass
    finally:
        manager.disconnect(channel_id, websocket)
        print(f"Cleaned up connection for user '{current_user.username}' on channel {channel_id}")


# --- Token Endpoint ---
@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session) # Ensure Session type hint is correct
):
    """Handles user login and returns JWT access token."""
    # --- Run synchronous authentication in threadpool ---
    user = await run_in_threadpool(authenticate_user, form_data.username, form_data.password, session)
    # --- End threadpool execution ---

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, # Use status from fastapi
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