import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    APP_NAME: str = "Governed Memory Hub API"
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Network Egress Governance Policy
    EGRESS_DEFAULT_DENY: bool = True
    EGRESS_ALLOW_LIST: List[str] = [
        "localhost:8000",
        "127.0.0.1:8000",
        "api:8000",
        "localhost:3000",
        "127.0.0.1:3000",
        "cockpit:3000",
        "postgres:5432",
        "redis:6379"
    ]

    # PostgreSQL Configuration
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "governed_memory_hub"
    POSTGRES_USER: str = "hub_user"
    POSTGRES_PASSWORD: str = "hub_secure_password_123"

    # Redis Configuration
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000", "*"]

    @property
    def postgres_dsn(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()

def validate_outbound_egress_destination(destination: str) -> bool:
    """
    Enforce Default-Deny Outbound Network Egress Control.
    Checks destination against explicit named allow-list.
    Raises PermissionError if unauthorized destination is targeted.
    """
    if not settings.EGRESS_DEFAULT_DENY:
        return True

    dest_clean = destination.lower().replace("http://", "").replace("https://", "").split("/")[0]

    for allowed in settings.EGRESS_ALLOW_LIST:
        if dest_clean == allowed.lower() or dest_clean.startswith(allowed.lower()):
            return True

    raise PermissionError(f"Network Egress Violation: Outbound destination '{destination}' is blocked by default-deny network policy.")
