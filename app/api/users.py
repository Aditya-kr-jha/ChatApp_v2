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
    """
    Create a new user.

    This endpoint creates a new user from the provided data, after checking if
    the username or email is already registered. The plain password is hashed,
    and then the new user record is saved in the database.
    """
    # Verify if username or email already exists.
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

    # Hash the provided password.
    hashed_password = hash_password(user_in.password)
    # Remove the plain password and add the hashed password to user data.
    user_data = user_in.model_dump(exclude={"password"})
    db_user = User(**user_data, hashed_password=hashed_password)

    # Persist the new user record.
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
    """
    Retrieve a list of users.

    This endpoint returns a paginated list of users from the database. The
    current authenticated user is required for authorization.
    """
    users = session.exec(select(User).offset(skip).limit(limit)).all()
    return users

@router.get("/{user_id}", response_model=UserRead)
def read_user(
    *,
    session: Session = Depends(get_session),
    user_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a user by ID.

    This endpoint fetches the user record matching the given user_id. If the
    user does not exist, a 404 error is returned.
    """
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
    """
    Update an existing user.

    This endpoint allows updating fields of the user record. It ensures that the
    current user is authorized to update the record. If the password is updated,
    it is automatically hashed.
    """
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Authorization check: only allow the user himself (or an admin) to update.
    if db_user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this user")

    # Retrieve only the fields provided in the request.
    user_data = user_in.model_dump(exclude_unset=True)

    # Process password separately to hash it.
    if "password" in user_data and user_data["password"]:
        hashed_password = hash_password(user_data["password"])
        db_user.hashed_password = hashed_password
        del user_data["password"]

    # Update remaining fields.
    for key, value in user_data.items():
        setattr(db_user, key, value)

    # Update modification timestamp.
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
    """
    Delete a user.

    This endpoint deletes the user matching user_id. Only the current user can
    delete his own user record.
    """
    db_user = session.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Authorization: only the owner of the record can delete it.
    if db_user.id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this user")

    session.delete(db_user)
    session.commit()

    return {"message": "User deleted successfully"}