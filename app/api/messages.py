# python
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.auth import get_current_active_user
from app.db.session import get_session
from app.models.models import Message, Channel, User, utc_now, Membership
from app.schemas.schemas import MessageCreate, MessageRead, MessageUpdate

# Create an API router for message operations.
messages_router = APIRouter(
    prefix="/messages",
    tags=["messages"],
    responses={404: {"description": "Not found"}},
)


@messages_router.post("/channels/{channel_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
def create_message_in_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,
        message_in: MessageCreate,
        current_user: User = Depends(get_current_active_user)
):
    """
    Creates a new message in a specific channel.

    - Requires the user making the request (`current_user`) to be a member
      of the specified channel.
    - The author of the message is automatically set to the `current_user`.
    """
    # Validate that the channel exists
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    # Authorization: Check if the current user is a member of the channel
    membership_check = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if not membership_check:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not authorized to post messages in this channel."
         )

    # Create the message instance, setting author_id from current_user
    db_message = Message.model_validate(
        message_in,
        update={
            "channel_id": channel_id,
            "author_id": current_user.id # Set author automatically
        }
    )

    session.add(db_message)
    session.commit()
    session.refresh(db_message)
    return db_message


@messages_router.get("/{message_id}", response_model=MessageRead)
def read_message(
        *,
        session: Session = Depends(get_session),
        message_id: int,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a message by its ID.

    Returns the requested message; raises an HTTP error if not found.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return db_message


@messages_router.patch("/{message_id}", response_model=MessageRead)
def update_message(
        *,
        session: Session = Depends(get_session),
        message_id: int,
        message_in: MessageUpdate,
        current_user: User = Depends(get_current_active_user)
):
    """
    Update an existing message.

    Validates that the message exists and that the current user is the author.
    Only updates fields provided in the request.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    # Check if the message belongs to the current user.
    if db_message.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this message")

    # Update only the provided fields.
    message_data = message_in.model_dump(exclude_unset=True)
    for key, value in message_data.items():
        setattr(db_message, key, value)

    # Update the modification timestamp.
    db_message.updated_at = utc_now()
    session.add(db_message)
    session.commit()
    session.refresh(db_message)
    return db_message


@messages_router.delete("/{message_id}", status_code=status.HTTP_200_OK)
def delete_message(
        *,
        session: Session = Depends(get_session),
        message_id: int,
        current_user: User = Depends(get_current_active_user)
):
    """
    Delete a message by its ID.

    Only the author of the message can delete it.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    # Ensure the current user is authorized to delete the message.
    if db_message.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this message")

    session.delete(db_message)
    session.commit()
    return {"message": "Message deleted successfully"}


@messages_router.get("/user/{user_id}", response_model=List[MessageRead])
def read_all_messages_of_user(
        *,
        session: Session = Depends(get_session),
        user_id: int,  # The author whose messages we want.
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)  # The user making the request.
):
    """
    Retrieve messages authored by 'user_id' that are posted in channels
    where the current user is a member.

    Uses a SQL join with the Membership table to enforce membership restrictions.
    """
    statement = (
        select(Message)
        .join(Membership, Message.channel_id == Membership.channel_id)
        .where(Message.author_id == user_id)  # Filter by the desired author.
        .where(Membership.user_id == current_user.id)  # Ensure the current user is a member.
        .order_by(Message.created_at.desc())  # Order messages by creation date.
        .offset(skip)  # Skip a number of results for pagination.
        .limit(limit)  # Limit the number of results for pagination.
    )
    messages = session.exec(statement).all()
    return messages


@messages_router.get("/channel/{channel_id}/user/{user_id}", response_model=List[MessageRead])
def read_all_messages_of_user_in_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,  # The specific channel to filter messages.
        user_id: int,  # The author whose messages we want.
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)  # The user making the request.
):
    """
    Retrieve messages authored by 'user_id' in a specific channel.

    First validates that the current user is a member of the requested channel,
    then retrieves the messages if authorized.
    """
    # Perform an authorization check using Membership table.
    membership_check = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()
    if not membership_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view messages in this channel."
        )

    # Query for messages in the specific channel.
    statement = (
        select(Message)
        .where(Message.author_id == user_id)
        .where(Message.channel_id == channel_id)
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    messages = session.exec(statement).all()
    return messages

@messages_router.get("/channel/{channel_id}", response_model=List[MessageRead])
def read_messages_in_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int, # The channel whose messages we want
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user) # The user making the request
):
    """
    Retrieves all messages within a specific channel, ordered by creation date.

    Requires the user making the request (`current_user`) to be a member
    of the specified channel.
    """
    # --- Authorization Check ---
    # Efficiently check if the current user is a member of the requested channel.
    # This query is fast as it directly checks the link table.
    membership_check = session.exec(
        select(Membership).where(
            Membership.user_id == current_user.id,
            Membership.channel_id == channel_id
        )
    ).first()

    # If no membership record is found, the user is not authorized.
    if not membership_check:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN, # Use 403 Forbidden for authorization errors
             detail="Not authorized to view messages in this channel."
         )
    # --- End Authorization Check ---

    # If authorized, proceed to query the messages for the specified channel
    statement = (
        select(Message)
        .where(Message.channel_id == channel_id) # Filter messages by the channel_id
        .order_by(Message.created_at.desc()) # Order by most recent first (descending)
        .offset(skip) # Apply pagination offset
        .limit(limit) # Apply pagination limit
    )

    # Execute the query and retrieve all matching messages
    messages = session.exec(statement).all()

    # Return the list of messages (will be empty if the channel has no messages)
    return messages