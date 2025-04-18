from datetime import timedelta, datetime, timezone
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status, Query, WebSocketException
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError, ExpiredSignatureError, PyJWTError
from passlib.context import CryptContext
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool
from starlette import status as ws_status

from app.config import settings
from app.db.session import get_session
from app.models.models import get_user, User
from app.schemas.token import TokenData
from app.models_enums.enums import UserStatus

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme for token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# Function to hash a password
def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# Function to verify a password
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def authenticate_user(username: str, password: str, session) -> User | bool:
    user = get_user(username, session)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: int | timedelta = None) -> str:
    """
    Create an access token with the given data and expiration time.

    Args:
        data (dict): The data to include in the token.
        expires_delta (int or timedelta, optional): The expiration time in seconds or as a timedelta. Defaults to None.

    Returns:
        str: The generated access token.
    """
    to_encode = data.copy()
    if expires_delta:
        if isinstance(expires_delta, timedelta):
            expires = datetime.now(timezone.utc) + expires_delta
        else:
            expires = datetime.now(timezone.utc) + timedelta(seconds=expires_delta)
    else:
        expires = datetime.now(timezone.utc) + timedelta(minutes=150)
    to_encode.update({"exp": expires})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Session = Depends(get_session),
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user(token_data.username, session)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(current_user: User = Depends(get_current_user)):
    return current_user


# --- NEW FUNCTION for WebSocket Auth  ---
async def get_current_user_from_query(
    token: str = Query(..., description="WebSocket authentication token"),
    session: Session = Depends(get_session),  # Still using sync session via Depends
) -> User:
    """
    Dependency to authenticate a user based on a JWT token passed as a query parameter using PyJWT.
    Handles synchronous database calls using run_in_threadpool.
    """
    credentials_exception = WebSocketException(
        code=ws_status.WS_1008_POLICY_VIOLATION,
        reason="Could not validate credentials",
    )
    token_expired_exception = WebSocketException(
        code=ws_status.WS_1008_POLICY_VIOLATION,
        reason="Token has expired",
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            print("Token payload missing 'sub' (username)")
            raise credentials_exception
    except ExpiredSignatureError:
        print("Token validation failed: ExpiredSignatureError")
        raise token_expired_exception  # Raise specific exception for expired token
    except (
        PyJWTError
    ) as e:  # Catch other PyJWT errors (InvalidTokenError, DecodeError, etc.)
        print(f"Token validation failed: {e}")
        raise credentials_exception  # Raise generic credentials exception

    # --- Run synchronous DB lookup in threadpool ---
    def get_user_sync(uname: str):
        return session.exec(select(User).where(User.username == uname)).first()

    # Await the result from the threadpool
    user = await run_in_threadpool(get_user_sync, username)
    # --- End threadpool execution ---

    if user is None:
        print(f"User '{username}' not found in database")
        raise credentials_exception

    print(f"Successfully authenticated user '{username}' for WebSocket")
    return user
