from enum import Enum

class UserStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    deleted = "deleted"

class MessageTypeEnum(str, Enum):
    text = "text"
    file = "file"