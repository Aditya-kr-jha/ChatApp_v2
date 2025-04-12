from pydantic import BaseSettings

class Settings(BaseSettings):
    # Database settings
    DATABASE_URL: str = "sqlite:///./blog.db"

    # Authentication
    SECRET_KEY: str = "rhrytuejifuhru4577838478f47ty748urujruty478uru4t58y"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 300

    # Application settings

    ECHO: bool = True
    RELOAD: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# Create settings instance
settings = Settings()
