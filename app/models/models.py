from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import Field, SQLModel, Relationship, select

from app.enum.enums import UserStatus


# Helper function to get UTC timestamp
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    hashed_password: str
    first_name: str
    last_name: str
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    status: UserStatus = Field(default=UserStatus.active)

    # Relationships
    messages: List["Message"] = Relationship(back_populates="author")
    owned_channels: List["Channel"] = Relationship(back_populates="owner")
    memberships: List["Membership"] = Relationship(back_populates="user")
    channels: List["Channel"] = Relationship(
        back_populates="members",
        link_model="Membership",
        sa_relationship_kwargs={"secondary": "memberships"}
    )


class Channel(SQLModel, table=True):
    __tablename__ = "channels"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    owner_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    # Relationships
    owner: Optional[User] = Relationship(back_populates="owned_channels")
    messages: List["Message"] = Relationship(back_populates="channel")
    memberships: List["Membership"] = Relationship(back_populates="channel")
    members: List[User] = Relationship(
        back_populates="channels",
        link_model="Membership",
        sa_relationship_kwargs={"secondary": "memberships"}
    )


class Message(SQLModel, table=True):
    __tablename__ = "messages"

    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    author_id: Optional[int] = Field(default=None, foreign_key="users.id")
    channel_id: Optional[int] = Field(default=None, foreign_key="channels.id")

    # Relationships
    author: Optional[User] = Relationship(back_populates="messages")
    channel: Optional[Channel] = Relationship(back_populates="messages")


class Membership(SQLModel, table=True):
    __tablename__ = "memberships"

    user_id: int = Field(foreign_key="users.id", primary_key=True)
    channel_id: int = Field(foreign_key="channels.id", primary_key=True)
    joined_at: datetime = Field(default_factory=utc_now)

    # Relationships
    user: User = Relationship(back_populates="memberships")
    channel: Channel = Relationship(back_populates="memberships")


def get_user(username: str, session) -> Optional[User]:
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    return user