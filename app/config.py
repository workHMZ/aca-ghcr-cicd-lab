"""Validated runtime configuration loaded after the optional dotenv file."""

from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load a developer .env before BaseSettings reads the process environment.
# Existing process/container variables remain authoritative.
load_dotenv(override=False)

ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh", "max"]
Verbosity = Literal["low", "medium", "high"]


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
        str_strip_whitespace=True,
    )

    app_version: str = "3.0.0"
    build_sha: str = "unknown"
    image_tag: str = "unknown"
    env_name: str = Field(default="stg", validation_alias=AliasChoices("ENV_NAME", "DD_ENV"))
    service_name: str = Field(
        default="serverless-rag-api",
        validation_alias=AliasChoices("SERVICE_NAME", "DD_SERVICE"),
    )

    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6-terra"
    openai_max_output_tokens: int = Field(default=1200, ge=128, le=128_000)
    openai_reasoning_effort: ReasoningEffort = "low"
    openai_verbosity: Verbosity = "low"
    openai_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    openai_max_retries: int = Field(default=2, ge=0, le=5)

    azure_search_endpoint: str | None = None
    azure_search_index_name: str = "ragdocs-v3"
    azure_search_api_key: str | None = None
    search_candidate_count: int = Field(default=50, ge=10, le=1000)
    search_semantic_enabled: bool = True
    search_semantic_configuration: str = "rag-semantic"
    search_top_k_default: int = Field(default=5, ge=1, le=10)
    search_top_k_max: int = Field(default=10, ge=1, le=50)
    max_question_chars: int = Field(default=4_000, ge=1, le=100_000)

    embedding_model_name: Literal["intfloat/multilingual-e5-small"] = Field(
        default="intfloat/multilingual-e5-small",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "EMBEDDING_MODEL_NAME"),
    )
    embedding_model_revision: Literal["614241f622f53c4eeff9890bdc4f31cfecc418b3"] = (
        "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    )
    embedding_model_path: str | None = None
    embedding_offline: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "EMBEDDING_OFFLINE",
            "HF_HUB_OFFLINE",
            "TRANSFORMERS_OFFLINE",
        ),
    )
    embedding_batch_size: int = Field(default=16, ge=1, le=256)
    embedding_query_max_tokens: int = Field(
        default=512,
        ge=8,
        le=512,
        validation_alias=AliasChoices("EMBEDDING_QUERY_MAX_TOKENS", "EMBEDDING_MAX_TOKENS"),
    )

    @model_validator(mode="after")
    def validate_cross_field_bounds(self) -> "Settings":
        if self.search_top_k_default > self.search_top_k_max:
            raise ValueError("SEARCH_TOP_K_DEFAULT cannot exceed SEARCH_TOP_K_MAX")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()


settings = get_settings()
