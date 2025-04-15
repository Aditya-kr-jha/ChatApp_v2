from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.models_enums.enums import UserStatus


class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: str
    last_name: str
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    status: UserStatus = UserStatus.active


class UserCreate(UserBase):
    password: str


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Added UserUpdate schema
class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    status: Optional[UserStatus] = None
    password: Optional[str] = None # For password updates


class ChannelCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ChannelRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Added ChannelUpdate schema (optional, but good practice)
class ChannelUpdate(BaseModel):
    owner_id: int=None
    name: Optional[str] = None
    description: Optional[str] = None


class MessageCreate(BaseModel):
    content: str


class MessageRead(BaseModel):
    id: int
    content: str
    author_id: int
    channel_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Added MessageUpdate schema
class MessageUpdate(BaseModel):
    content: Optional[str] = None
