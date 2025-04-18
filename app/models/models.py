from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship, select

from app.models_enums.enums import UserStatus, MessageTypeEnum


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    channel_id: int = Field(foreign_key="channels.id", primary_key=True)
    joined_at: datetime = Field(default_factory=utc_now)

    user: "User" = Relationship(
        back_populates="memberships",
        sa_relationship_kwargs={"overlaps": "channels,members"},
    )
    channel: "Channel" = Relationship(
        back_populates="memberships",
        sa_relationship_kwargs={"overlaps": "members,channels"},
    )


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    first_name: Optional[str] = Field(default=None, nullable=True)
    last_name: Optional[str] = Field(default=None, nullable=True)
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: UserStatus = Field(default=UserStatus.active)

    messages: List["Message"] = Relationship(back_populates="author")
    owned_channels: List["Channel"] = Relationship(back_populates="owner")
    memberships: List["Membership"] = Relationship(back_populates="user")
    channels: List["Channel"] = Relationship(
        back_populates="members",
        link_model=Membership,
        sa_relationship_kwargs={
            "secondary": "memberships",
            "overlaps": "memberships,user",
        },
    )


class Channel(SQLModel, table=True):
    __tablename__ = "channels"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    owner: Optional["User"] = Relationship(back_populates="owned_channels")
    messages: List["Message"] = Relationship(back_populates="channel")
    memberships: List["Membership"] = Relationship(
        back_populates="channel", sa_relationship_kwargs={"overlaps": "channels"}
    )
    members: List["User"] = Relationship(
        back_populates="channels",
        link_model=Membership,
        sa_relationship_kwargs={
            "secondary": "memberships",
            "overlaps": "channel,memberships,user",
        },
    )


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    author_id: Optional[int] = Field(default=None, foreign_key="users.id")
    channel_id: Optional[int] = Field(default=None, foreign_key="channels.id")
    message_type: MessageTypeEnum = Field(default=MessageTypeEnum.TEXT)
    # Field for text messages
    content: Optional[str] = Field(default=None)
    # Fields for file messages (matching MessageRead schema)
    s3_key: Optional[str] = Field(default=None, index=True)  # Store the S3 object key
    content_type: Optional[str] = Field(default=None)  # Store the MIME type
    original_filename: Optional[str] = Field(
        default=None
    )  # Store the original file name

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    author: Optional["User"] = Relationship(back_populates="messages")
    channel: Optional["Channel"] = Relationship(back_populates="messages")


def get_user(username: str, session) -> Optional[User]:
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    return user
