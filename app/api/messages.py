from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.auth import get_current_active_user
from app.db.session import get_session
from app.models.models import Message, Channel, User, utc_now, Membership
from app.schemas.schemas import MessageCreate, MessageRead, MessageUpdate
from websockets_manger import manager

# Create an API router for message operations.
messages_router = APIRouter(
    prefix="/messages",
    tags=["messages"],
    responses={404: {"description": "Not found"}},
)


# Make the function async
@messages_router.post("/channels/{channel_id}/messages", response_model=MessageRead, status_code=status.HTTP_201_CREATED)
async def create_message_in_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,
        message_in: MessageCreate,
        current_user: User = Depends(get_current_active_user)
):
    """
    Creates a new message in a specific channel and broadcasts it via WebSocket.

    - Requires the user making the request (`current_user`) to be a member
      of the specified channel.
    - The author of the message is automatically set to the `current_user`.
    """
    # --- Run synchronous DB/Auth checks in threadpool ---
    db_channel = await run_in_threadpool(session.get, Channel, channel_id)
    if not db_channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    membership_check = await run_in_threadpool(
        session.exec(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.channel_id == channel_id
            )
        ).first
    )
    # --- End threadpool execution ---

    if not membership_check:
         raise HTTPException(
             status_code=status.HTTP_403_FORBIDDEN,
             detail="Not authorized to post messages in this channel."
         )

    # Create the message instance (this part is usually quick)
    db_message = Message.model_validate(
        message_in,
        update={
            "channel_id": channel_id,
            "author_id": current_user.id
        }
    )

    # --- Run synchronous DB operations in threadpool ---
    def sync_db_operations():
        session.add(db_message)
        session.commit()
        session.refresh(db_message)
        return db_message

    refreshed_message = await run_in_threadpool(sync_db_operations)
    # --- Broadcast via WebSocket ---
    message_read = MessageRead.model_validate(refreshed_message)
    # Convert to dict suitable for JSON broadcasting
    message_data = message_read.model_dump(mode='json') # Use mode='json' for datetime serialization
    await manager.broadcast(channel_id, message_data)
    return refreshed_message



@messages_router.get("/{message_id}", response_model=MessageRead)
def read_message(
        *,
        session: Session = Depends(get_session),
        message_id: int,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a message by its unique identifier.

    This endpoint fetches a message based on the provided message_id.
    If no message is found in the database, it responds with a 404 error.
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

    This endpoint allows the author of a message to perform a partial update.
    It validates that:
      - The message exists.
      - The current user is the author of the message.

    Only the fields provided in the request are updated and the modification
    timestamp is updated.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    # Ensure the current user is the author of the message.
    if db_message.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this message")

    # Perform a partial update only on provided fields.
    message_data = message_in.model_dump(exclude_unset=True)
    for key, value in message_data.items():
        setattr(db_message, key, value)

    # Update the last-modified timestamp.
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
    Delete a message by its unique identifier.

    Only the message author is allowed to delete the message.
    If the message does not exist or the current user is not the author,
    an appropriate HTTP error is returned.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    # Check authorization: the current user must own the message.
    if db_message.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to delete this message")

    # Delete the message from the database.
    session.delete(db_message)
    session.commit()
    return {"message": "Message deleted successfully"}


@messages_router.get("/user/{user_id}", response_model=List[MessageRead])
def read_all_messages_of_user(
        *,
        session: Session = Depends(get_session),
        user_id: int,  # The author whose messages are being queried.
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve messages posted by a specific user.

    This endpoint returns messages that are authored by 'user_id' and belong
    to channels in which the current user has membership. It uses a join
    operation between messages and memberships to enforce this restriction.

    Pagination is supported through 'skip' and 'limit' parameters.
    """
    statement = (
        select(Message)
        .join(Membership, Message.channel_id == Membership.channel_id)
        .where(Message.author_id == user_id)  # Ensure messages are from the desired author.
        .where(Membership.user_id == current_user.id)  # Confirm current user is a member of the channel.
        .order_by(Message.created_at.desc())  # Order messages by creation date descending.
        .offset(skip)  # Support pagination by skipping records.
        .limit(limit)  # Limit the number of records returned.
    )
    messages = session.exec(statement).all()
    return messages


@messages_router.get("/channel/{channel_id}/user/{user_id}", response_model=List[MessageRead])
def read_all_messages_of_user_in_channel(
        *,
        session: Session = Depends(get_session),
        channel_id: int,  # The channel to filter messages.
        user_id: int,  # The author whose messages are queried.
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve messages by a specific user within a given channel.

    This endpoint first checks that the current user is a member of the specified
    channel and then returns messages authored by 'user_id' within the channel,
    applying pagination as needed.
    """
    # Verify that the current user is a member of the channel.
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

    # Retrieve messages in the channel from the specified author.
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
        channel_id: int,  # The channel from which to retrieve messages.
        skip: int = 0,
        limit: int = 100,
        current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve all messages in a specific channel.

    This endpoint lists all messages within a channel, ordering them by creation date.
    It enforces that the current user is a member of the channel through an authorization check.

    Pagination is supported through 'skip' and 'limit' parameters.
    """
    # Authorization Check: Verify current user membership.
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

    # Retrieve messages for the channel with pagination.
    statement = (
        select(Message)
        .where(Message.channel_id == channel_id)
        .order_by(Message.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    messages = session.exec(statement).all()
    return messages