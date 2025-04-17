import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlmodel import Session, select
from starlette.concurrency import run_in_threadpool

from app.auth import get_current_active_user
from app.db.session import get_session
from app.models.models import Message, Channel, User, utc_now, Membership
from app.schemas.schemas import (
    MessageCreate,
    MessageRead,
    MessageUpdate,
    MessageCreatePayload,
    FileAccessResponse,
)
from app.websockets_manger import manager
from models_enums.enums import MessageTypeEnum
from services.s3_client import S3Service, get_s3_service

logger = logging.getLogger(__name__)

# Create an API router for message operations.
messages_router = APIRouter(
    prefix="/messages",
    tags=["messages"],
    responses={404: {"description": "Not found"}},
)


def get_message_type_from_content(content_type: Optional[str]) -> MessageTypeEnum:
    if not content_type:
        return MessageTypeEnum.FILE
    mime_type = content_type.lower()
    if mime_type.startswith("image/"):
        return MessageTypeEnum.IMAGE
    elif mime_type.startswith("video/"):
        return MessageTypeEnum.VIDEO
    elif mime_type.startswith("audio/"):
        return MessageTypeEnum.AUDIO
    else:
        return MessageTypeEnum.FILE


# --- Create Text Message Endpoint ---
@messages_router.post(
    "/channels/{channel_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_text_message_in_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    message_in: MessageCreatePayload,
    current_user: User = Depends(get_current_active_user),
):
    """
    Creates a **text** message in a specific channel and broadcasts it.
    """
    if message_in.message_type != MessageTypeEnum.TEXT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This endpoint is only for text messages. Use POST /channels/{channel_id}/files for file uploads.",
        )
    if not message_in.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text messages must include 'content'.",
        )

    db_channel = await run_in_threadpool(session.get, Channel, channel_id)
    if not db_channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    membership_check = await run_in_threadpool(
        session.exec(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.channel_id == channel_id,
            )
        ).first
    )
    if not membership_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to post messages in this channel.",
        )

    db_message = Message(
        content=message_in.content,
        message_type=MessageTypeEnum.TEXT,
        channel_id=channel_id,
        author_id=current_user.id,
    )

    def sync_db_operations():
        session.add(db_message)
        session.commit()
        session.refresh(db_message)
        session.refresh(db_message, attribute_names=["author"])
        return db_message

    refreshed_message = await run_in_threadpool(sync_db_operations)

    message_read = MessageRead.model_validate(refreshed_message)
    message_broadcast_data = message_read.model_dump(mode="json")

    logger.info(
        f"Broadcasting TEXT message ID {message_read.id} to channel {channel_id}"
    )
    await manager.broadcast(channel_id, message_broadcast_data)

    return refreshed_message


# --- File Upload and Message Creation Endpoint ---
@messages_router.post(
    "/channels/{channel_id}/files",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file_and_create_message(
    *,
    channel_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_active_user),
    s3_service: S3Service = Depends(get_s3_service),  # Use the provided dependency
):
    """
    Uploads a file to S3, creates a file message record in the database,
    and broadcasts the message via WebSocket. Uses the injected S3Service.
    """
    # --- Authorization and Channel Check ---
    db_channel = await run_in_threadpool(session.get, Channel, channel_id)
    if not db_channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    membership_check = await run_in_threadpool(
        session.exec(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.channel_id == channel_id,
            )
        ).first
    )
    if not membership_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to upload files to this channel.",
        )

    # --- Upload file to S3 ---
    if not file.filename or not file.content_type:
        logger.warning(
            f"File upload attempt missing filename or content_type for channel {channel_id}"
        )
        raise HTTPException(
            status_code=400, detail="File is missing filename or content type."
        )

    try:
        s3_key = await s3_service.upload_file(
            file=file, filename=file.filename, content_type=file.content_type
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(
            f"Unexpected error calling S3 upload for {file.filename}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="File upload initiation failed.")

    # --- Create Message Record in DB ---
    message_type = get_message_type_from_content(file.content_type)

    db_message = Message(
        message_type=message_type,
        s3_key=s3_key,
        original_filename=file.filename,
        content_type=file.content_type,
        channel_id=channel_id,
        author_id=current_user.id,
    )

    # --- Run synchronous DB operations in threadpool ---
    def sync_db_operations():
        session.add(db_message)
        session.commit()
        session.refresh(db_message)
        session.refresh(db_message, attribute_names=["author"])
        return db_message

    try:
        refreshed_message = await run_in_threadpool(sync_db_operations)
    except Exception as e:
        logger.error(
            f"Database error after S3 upload for key {s3_key}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500, detail="Failed to save message after file upload."
        )

    # --- Broadcast via WebSocket ---
    message_read = MessageRead.model_validate(refreshed_message)
    message_broadcast_data = message_read.model_dump(mode="json")

    logger.info(
        f"Broadcasting FILE message ID {message_read.id} (key: {s3_key}) to channel {channel_id}"
    )
    await manager.broadcast(channel_id, message_broadcast_data)

    return refreshed_message


# --- Get File Access URL Endpoint (Using S3Service) ---
@messages_router.get("/{message_id}/access-url", response_model=FileAccessResponse)
async def get_file_access_url(
    *,
    session: Session = Depends(get_session),
    message_id: int,
    current_user: User = Depends(get_current_active_user),
    s3_service: S3Service = Depends(get_s3_service),  # Use the provided dependency
):
    """
    Generates a pre-signed GET URL to access a file associated with a message.
    Uses the injected S3Service.
    """
    # Fetch the message
    db_message = await run_in_threadpool(session.get, Message, message_id)
    if not db_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )
    if db_message.message_type == MessageTypeEnum.TEXT or not db_message.s3_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message does not have an associated file.",
        )

    # Authorization check
    if not db_message.channel_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message channel information missing.",
        )
    membership_check = await run_in_threadpool(
        session.exec(
            select(Membership).where(
                Membership.user_id == current_user.id,
                Membership.channel_id == db_message.channel_id,
            )
        ).first
    )
    if not membership_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access files in this channel.",
        )

    try:
        access_url = await run_in_threadpool(
            s3_service.get_presigned_url, db_message.s3_key
        )
        return FileAccessResponse(access_url=access_url)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(
            f"Unexpected error calling S3 get_presigned_url for {db_message.s3_key}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail="Failed to generate file access URL."
        )


@messages_router.get("/{message_id}", response_model=MessageRead)
def read_message(
    *,
    session: Session = Depends(get_session),
    message_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """
    Retrieve a message by its unique identifier.

    This endpoint fetches a message based on the provided message_id.
    If no message is found in the database, it responds with a 404 error.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )
    return db_message


@messages_router.patch("/{message_id}", response_model=MessageRead)
def update_message(
    *,
    session: Session = Depends(get_session),
    message_id: int,
    message_in: MessageUpdate,
    current_user: User = Depends(get_current_active_user),
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )

    # Ensure the current user is the author of the message.
    if db_message.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this message",
        )

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
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete a message by its unique identifier.

    Only the message author is allowed to delete the message.
    If the message does not exist or the current user is not the author,
    an appropriate HTTP error is returned.
    """
    db_message = session.get(Message, message_id)
    if not db_message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
        )

    # Check authorization: the current user must own the message.
    if db_message.author_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this message",
        )

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
    current_user: User = Depends(get_current_active_user),
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
        .where(
            Message.author_id == user_id
        )  # Ensure messages are from the desired author.
        .where(
            Membership.user_id == current_user.id
        )  # Confirm current user is a member of the channel.
        .order_by(
            Message.created_at.asc()
        )  # Order messages by creation date ascending (oldest first).
        .offset(skip)  # Support pagination by skipping records.
        .limit(limit)  # Limit the number of records returned.
    )
    messages = session.exec(statement).all()
    return messages


@messages_router.get(
    "/channel/{channel_id}/user/{user_id}", response_model=List[MessageRead]
)
def read_all_messages_of_user_in_channel(
    *,
    session: Session = Depends(get_session),
    channel_id: int,  # The channel to filter messages.
    user_id: int,  # The author whose messages are queried.
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_active_user),
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
            Membership.user_id == current_user.id, Membership.channel_id == channel_id
        )
    ).first()
    if not membership_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view messages in this channel.",
        )

    # Retrieve messages in the channel from the specified author.
    statement = (
        select(Message)
        .where(Message.author_id == user_id)
        .where(Message.channel_id == channel_id)
        .order_by(Message.created_at.asc())
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
    current_user: User = Depends(get_current_active_user),
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
            Membership.user_id == current_user.id, Membership.channel_id == channel_id
        )
    ).first()
    if not membership_check:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view messages in this channel.",
        )

    # Retrieve messages for the channel with pagination.
    statement = (
        select(Message)
        .where(Message.channel_id == channel_id)
        .order_by(Message.created_at.asc())
        .offset(skip)
        .limit(limit)
    )
    messages = session.exec(statement).all()
    return messages


@messages_router.delete(
    "/channel/{channel_id}/messages", status_code=status.HTTP_200_OK
)
def delete_all_channel_messages(
    *,
    session: Session = Depends(get_session),
    channel_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """
    Delete all messages in a specific channel.

    Only the channel owner can delete all messages in the channel.
    Returns the count of deleted messages.
    """
    # Verify the channel exists
    db_channel = session.get(Channel, channel_id)
    if not db_channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found"
        )

    # Verify the current user is the channel owner
    if db_channel.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only channel owner can delete all messages",
        )

    # Get all messages to delete
    statement = select(Message).where(Message.channel_id == channel_id)
    messages = session.exec(statement).all()
    count = len(messages)

    # Delete all messages
    for message in messages:
        session.delete(message)

    session.commit()

    return {"message": f"{count} messages deleted successfully from channel"}
