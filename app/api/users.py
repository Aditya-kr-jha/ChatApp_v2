from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth import hash_password, get_current_active_user
from app.db.session import get_session
from app.models.models import User, utc_now
from app.schemas.schemas import UserRead, UserCreate, UserUpdate

router = APIRouter(
    prefix="/users",
    tags=["users"],
    responses={404: {"description": "Not found"}},
)

@router.post("/", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    *,
    session: Session = Depends(get_session),
    user_in: UserCreate
):
    # Check if username or email already exists (optional but recommended)
    existing_user = session.exec(
        select(User).where(
            (User.username == user_in.username) | (User.email == user_in.email)
        )
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered.",
        )

    hashed_password = hash_password(user_in.password)
    # Create a dict excluding the plain password, add hashed password
    user_data = user_in.model_dump(exclude={"password"})
    db_user = User(**user_data, hashed_password=hashed_password)

    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@router.get("/", response_model=List[UserRead])
def read_users(
    *,
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user)
):
    users = session.exec(select(User).offset(skip).limit(limit)).all()
    return users

@router.get("/{user_id}", response_model=UserRead)
def read_user(
    *,
    session: Session = Depends(get_session),
    user_id: int,
    current_user: User = Depends(get_current_active_user)
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return db_user

@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    *,
    session: Session = Depends(get_session),
    user_id: int,
    user_in: UserUpdate,
    current_user: User = Depends(get_current_active_user)
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Authorization: Ensure the current user is the one being updated (or an admin)
    if db_user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this user")

    user_data = user_in.model_dump(exclude_unset=True) # Get only fields that were actually sent

    # Handle password update separately
    if "password" in user_data and user_data["password"]:
        hashed_password = hash_password(user_data["password"])
        db_user.hashed_password = hashed_password
        del user_data["password"] # Don't try to set it again below

    # Update other fields
    for key, value in user_data.items():
        setattr(db_user, key, value)

    db_user.updated_at = utc_now()

    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    *,
    session: Session = Depends(get_session),
    user_id: int,
    current_user: User = Depends(get_current_active_user)
):
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if db_user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this user")

    session.delete(db_user)
    session.commit()

    return {"message": "User deleted successfully"}
