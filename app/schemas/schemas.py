# Imports
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from models_enums.enums import UserStatus, MessageTypeEnum


# User Schemas
class UserBase(BaseModel):
    username: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
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

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[str] = None
    status: Optional[UserStatus] = None
    password: Optional[str] = None


# Channel Schemas
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

class ChannelUpdate(BaseModel):
    owner_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None

class ChannelOwner(BaseModel):
    channel_id: int
    channel_name: str
    owner_id: int
    owner_name: str


# File Upload Schemas
class FileUploadData(BaseModel):
    s3_key: str = Field(..., description="Unique S3 object key.")
    content_type: str = Field(..., description="MIME type of the uploaded file.")
    filename: str = Field(..., description="Original filename provided by the client.")

class FileUploadResponse(BaseModel):
    message: str = "File uploaded successfully (privately)."
    data: FileUploadData


# WebSocket File Message Schemas
class WebSocketSendFile(BaseModel):
    type: Literal["send_file"] = "send_file"
    channel_id: Optional[int] = None
    recipient_id: Optional[int] = None
    file_info: FileUploadData

class WebSocketFileMessage(BaseModel):
    type: Literal["file_message"] = "file_message"
    message_id: int = Field(..., description="Message ID from the database.")
    sender_id: int = Field(..., description="ID of the user who sent the file.")
    channel_id: Optional[int] = None
    recipient_id: Optional[int] = None
    s3_key: str = Field(..., description="S3 key for pre-signed URL generation.")
    content_type: str = Field(..., description="MIME type for display.")
    filename: str = Field(..., description="Original filename for display.")
    timestamp: datetime = Field(..., description="Timestamp when the message was created.")


# Message Schemas
class MessageCreate(BaseModel):
    content: str

class MessageRead(BaseModel):
    id: int
    author_id: int
    channel_id: Optional[int] = None
    recipient_id: Optional[int] = None
    message_type: MessageTypeEnum
    content: Optional[str] = Field(None, description="Text content for text messages.")
    s3_key: Optional[str] = Field(None, description="S3 key for file messages.")
    content_type: Optional[str] = Field(None, description="MIME type for file messages.")
    original_filename: Optional[str] = Field(None, description="Original filename for file messages.")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class MessageUpdate(BaseModel):
    content: Optional[str] = None


# Pre-signed URL Schema
class FileAccessResponse(BaseModel):
    access_url: HttpUrl