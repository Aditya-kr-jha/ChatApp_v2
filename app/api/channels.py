from typing import List, Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import aliased
from sqlmodel import Session, select

from app.auth import get_current_active_user
from app.db.session import get_session
from app.models.models import Channel, utc_now, User, Membership
from app.schemas.schemas import ChannelCreate, ChannelRead, ChannelUpdate, UserRead

# Define a router for channel-related operations.
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
    """
    Create a new channel.

    This endpoint creates a new channel using the data from channel_in. If an owner_id is not provided,
    the current authenticated user is set as the owner.
    """
    # Create a new channel instance with the provided data and owner information.
    db_channel = Channel(
        **channel_in.model_dump(),
        owner_id=owner_id if owner_id is not None else current_user.id
    )
    session.add(db_channel)
    session.commit()  # Save the new channel to the database.
    session.refresh(db_channel)  # Refresh the instance to load any DB-generated fields.
    return db_channel


@channel_router.get("/", response_model=List[ChannelRead])
def read_channels(
        *,
        session: Session = Depends(get_session),
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a list of channels.

    Returns a paginated list of all channels.
    """
    # Execute a query to retrieve channels with pagination.
    channels = session.exec(select(Channel).offset(skip).limit(limit)).all()
    return channels


@channel_router.get("/{channel_id}", response_model=ChannelRead)
def read_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a single channel by its ID.

    If the channel is not found, a 404 error is raised.
    """
    # Retrieve the channel using the channel ID.
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
    """
    Update an existing channel.

    Only the channel owner may update the channel. The endpoint applies partial updates.
    """
    # Retrieve the channel from the DB.
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # Authorization: Only the channel owner can perform an update.
    if db_channel.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this channel")

    # Update only provided fields.
    channel_data = channel_in.model_dump(exclude_unset=True)
    for key, value in channel_data.items():
        setattr(db_channel, key, value)

    # Set updated_at timestamp.
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
    """
    Delete a channel.

    Only the owner of the channel is authorized to delete it.
    """
    # Retrieve the channel to be deleted.
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # Verify the current user is the owner.
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
    """
    Change the owner of a channel.

    Only the current owner is allowed to change the ownership of the channel.
    """
    # Retrieve the channel.
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # Check ownership authorization.
    if db_channel.owner_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized to change the owner of this channel")

    # Retrieve the new owner user.
    new_owner = session.get(User, new_owner_id)
    if not new_owner:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New owner not found")

    # Update owner and set the updated_at timestamp.
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
        user_id: int,  # The user whose channel memberships we want to list.
        skip: int = 0,
        limit: int = 100,
):
    """
    Retrieve all channels that a given user is a member of.

    NOTE: This endpoint does NOT check the permissions of the requestor.
    """
    # Check if the target user exists.
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")

    # Query channels through a join on Membership.
    statement = (
        select(Channel)
        .join(Membership, Channel.id == Membership.channel_id)
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
        user_id: int,  # The target user whose memberships need to be filtered.
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve channels that the target user is a member of, only if the
    current user is also a member of those channels.
    """
    # Check if the target user exists.
    target_user = session.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User with ID {user_id} not found.")

    # Query channels ensuring both the target and current user share the membership.
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


@channel_router.post("/{channel_id}/join", status_code=status.HTTP_201_CREATED, response_model=Membership)
def join_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,
        current_user: User = Depends(get_current_active_user)
):
    """
    Join a channel.

    This endpoint allows the current user to join the specified channel.
    """
    # Check if the channel exists.
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # Verify that the user is not already a member.
    existing_membership = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if existing_membership:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member of this channel.")

    # Create a new membership record.
    new_membership = Membership(user_id=current_user.id, channel_id=channel_id)
    session.add(new_membership)
    session.commit()
    session.refresh(new_membership)  # Refresh to load DB-generated defaults.
    return new_membership


@channel_router.delete("/{channel_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
def leave_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,
        current_user: User = Depends(get_current_active_user)
):
    """
    Leave a channel.

    This endpoint allows the current user to leave the specified channel.
    """
    # Verify that the channel exists.
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # Prevent channel owner from leaving without transferring ownership.
    if db_channel.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel owner cannot leave the channel. Transfer ownership first."
        )

    # Locate the membership record for deletion.
    membership_to_delete = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if not membership_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User is not a member of this channel.")

    session.delete(membership_to_delete)
    session.commit()
    # A 204 No Content response is returned.
    return None


@channel_router.get("/{channel_id}/members", response_model=List[UserRead])
def read_channel_members(
        *,
        session: Session = Depends(get_session),
        channel_id: int,
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve channel members.

    This endpoint returns a paginated list of members for the specified channel.
    The current user must be a member of the channel to view its members.
    """
    # Verify current user's membership in the channel.
    auth_membership_check = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if not auth_membership_check:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Not authorized to view members of this channel.")

    # Query for users by joining with the membership table.
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
    """
    Retrieve channels the current user belongs to.

    Returns a paginated list of channels, ordered alphabetically by channel name.
    """
    statement = (
        select(Channel)
        .join(Membership, Channel.id == Membership.channel_id)
        .where(Membership.user_id == current_user.id)
        .order_by(Channel.name)
        .offset(skip)
        .limit(limit)
    )
    channels = session.exec(statement).all()
    return channels