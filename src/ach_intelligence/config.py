from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ACH_", env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./ach.db"
    moov_url: str = ""
    max_upload_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    duplicate_keys: str = "account_amount_date,trace"
    llm_provider: Literal["offline", "ollama"] = "offline"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    api_token: str = ""

    @field_validator("duplicate_keys")
    @classmethod
    def validate_keys(cls, value: str) -> str:
        if not set(value.split(",")) <= {"account_amount_date", "trace"}:
            raise ValueError("unsupported duplicate key")
        return value
