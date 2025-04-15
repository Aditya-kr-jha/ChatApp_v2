from contextlib import asynccontextmanager
from datetime import timedelta

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from api.channels import channel_router
from api.messages import messages_router
from api.users import router
from app.auth import create_access_token, authenticate_user
from app.config import settings
from app.db.session import create_db_and_tables, get_session
from app.schemas.token import Token

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up the FastAPI application...")
    create_db_and_tables()
    yield
    print("Shutting down the FastAPI application...")

app = FastAPI(lifespan=lifespan, title="Chat Application", version="0.1.2")
app.include_router(router)
app.include_router(channel_router)
app.include_router(messages_router)
@app.get("/")
async def root():
    return {"message": "Welcome to the Chat API"}

@app.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), session = Depends(get_session)
):
    user = authenticate_user(form_data.username, form_data.password, session)
    if not user:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Incorrect username or password",
            headers = {"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)