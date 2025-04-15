from typing import List, Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from app.auth import get_current_active_user
from app.db.session import get_session
from app.models.models import Channel, utc_now, User, Membership
from app.schemas.schemas import ChannelCreate, ChannelRead, ChannelUpdate

channel_router = APIRouter(
    prefix="/channels",
    tags=["channels"],
    responses={404: {"description": "Not found"}},
)

@channel_router.post("/", response_model=ChannelRead, status_code=status.HTTP_201_CREATED)
def create_channel(
    *,
    session: Session = Depends(get_session),
    channel_in: ChannelCreate,
    owner_id: Annotated[Optional[int], Query(description="Optional owner id")] = None,
    current_user: User = Depends(get_current_active_user)
):
    db_channel = Channel(
        **channel_in.model_dump(),
        owner_id=owner_id if owner_id is not None else current_user.id
    )
    session.add(db_channel)
    session.commit()
    session.refresh(db_channel)
    return db_channel

@channel_router.get("/", response_model=List[ChannelRead])
def read_channels(
    *,
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user)
):
    channels = session.exec(select(Channel).offset(skip).limit(limit)).all()
    return channels

@channel_router.get("/{channel_id}", response_model=ChannelRead)
def read_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    current_user: User = Depends(get_current_active_user)
):
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return db_channel

@channel_router.patch("/{channel_id}", response_model=ChannelRead)
def update_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    channel_in: ChannelUpdate,
    current_user: User = Depends(get_current_active_user)
):
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    if db_channel.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this channel")
    channel_data = channel_in.model_dump(exclude_unset=True)
    for key, value in channel_data.items():
        setattr(db_channel, key, value)
    db_channel.updated_at = utc_now()
    session.add(db_channel)
    session.commit()
    session.refresh(db_channel)
    return db_channel

@channel_router.delete("/{channel_id}", status_code=status.HTTP_200_OK)
def delete_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    current_user: User = Depends(get_current_active_user)
):
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    if db_channel.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this channel")
    session.delete(db_channel)
    session.commit()
    return {"message": "Channel deleted successfully"}

@channel_router.patch("/{channel_id}/change_owner", response_model=ChannelRead)
def change_channel_owner(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    new_owner_id: Annotated[int, Query(description="ID of the new owner")],
    current_user: User = Depends(get_current_active_user)
):
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found"
        )
    if db_channel.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to change the owner of this channel"
        )
    new_owner = session.get(User, new_owner_id)
    if not new_owner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="New owner not found"
        )
    db_channel.owner_id = new_owner_id
    db_channel.updated_at = utc_now()
    session.add(db_channel)
    session.commit()
    session.refresh(db_channel)
    return db_channel


@channel_router.get("/user/{user_id}/memberships", response_model=List[ChannelRead])
def read_user_channel_memberships(
    *,
    session: Session = Depends(get_session),
    user_id: int, # The user whose channel memberships we want to list
    skip: int = 0,
    limit: int = 100,
    # Note: No current_user dependency needed here as per requirement
):
    """
    Retrieves a list of all channels that the specified user_id is a member of.

    NOTE: This endpoint does NOT check the permissions of the user making the
    request. It reveals channel membership information for the specified user_id.
    Use with caution, potentially restricting access to admins if needed.
    """
    # Optional: Check if the target user exists first
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )

    # Query channels by joining Membership table and filtering by user_id
    statement = (
        select(Channel)
        # Join Channel with Membership table on the channel_id
        .join(Membership, Channel.id == Membership.channel_id)
        # Filter the memberships to only include the target user_id
        .where(Membership.user_id == user_id)
        .offset(skip)
        .limit(limit)
    )
    channels = session.exec(statement).all()
    return channels


@channel_router.get("/user/{user_id}/shared-memberships", response_model=List[ChannelRead])
def read_user_shared_channel_memberships(
    *,
    session: Session = Depends(get_session),
    user_id: int, # The target user whose channel memberships we want to list
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user) # The user making the request
):
    """
    Retrieves a list of channels that the specified user_id is a member of,
    *only if* the current authenticated user (`current_user`) is also a member
    of those same channels.

    This prevents users from seeing channel memberships of others unless they
    share membership in those channels.
    """
    # Optional: Check if the target user exists first
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found."
        )

    statement = (
        select(Channel)
        .join(Membership, Channel.id == Membership.channel_id)
        .where(Membership.user_id == user_id)
        .where(Channel.id.in_(
            select(Membership.channel_id).where(Membership.user_id == current_user.id)
        ))
        .offset(skip)
        .limit(limit)
    )
    channels = session.exec(statement).all()
    return channels

@channel_router.post("/{channel_id}/join", status_code=status.HTTP_201_CREATED, response_model=Membership) # Return membership details
def join_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Allows the current user to join a specified channel."""
    # 1. Check if channel exists
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # 2. Check if user is already a member
    existing_membership = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if existing_membership:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, # 409 Conflict is suitable here
            detail="User is already a member of this channel."
        )

    # 3. Create Membership record
    new_membership = Membership(user_id=current_user.id, channel_id=channel_id)
    session.add(new_membership)
    session.commit()
    session.refresh(new_membership) # Refresh to get DB defaults like joined_at

    return new_membership


@channel_router.delete("/{channel_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    current_user: User = Depends(get_current_active_user)
):
    """Allows the current user to leave a specified channel."""
    # 1. Check if channel exists (optional, FK constraint might handle)
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # 2. Check if user is the owner (prevent owner from leaving)
    if db_channel.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel owner cannot leave the channel. Transfer ownership first."
        )

    # 3. Find the specific Membership record
    membership_to_delete = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()

    # 4. If found, delete it
    if not membership_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, # Or 400 Bad Request
            detail="User is not a member of this channel."
        )

    session.delete(membership_to_delete)
    session.commit()

    # Return No Content status code
    return None # Or return Response(status_code=status.HTTP_204_NO_CONTENT)


@channel_router.get("/{channel_id}/members", response_model=List[UserRead])
def read_channel_members(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user)
):
    """Retrieves a list of members for a specific channel. Requires the current user to be a member."""
    # 1. Authorization: Check if current_user is a member of channel_id
    auth_membership_check = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if not auth_membership_check:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not authorized to view members of this channel."
         )

    # 2. If authorized, SELECT User JOIN Membership WHERE Membership.channel_id == channel_id
    statement = (
        select(User)
        .join(Membership, User.id == Membership.user_id)
        .where(Membership.channel_id == channel_id)
        .offset(skip)
        .limit(limit)
    )
    members = session.exec(statement).all()

    return members


@channel_router.get("/my-memberships", response_model=List[ChannelRead])
def read_my_channels(
    *,
    session: Session = Depends(get_session),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user)
):
    """Retrieves a list of all channels the current user is a member of."""
    statement = (
        select(Channel)
        .join(Membership, Channel.id == Membership.channel_id)
        .where(Membership.user_id == current_user.id)
        .order_by(Channel.name) # Optional: order alphabetically
        .offset(skip)
        .limit(limit)
    )
    channels = session.exec(statement).all()
    return channels