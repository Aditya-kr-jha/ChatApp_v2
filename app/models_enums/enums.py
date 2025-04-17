from enum import Enum

class UserStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"

class MessageTypeEnum(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"