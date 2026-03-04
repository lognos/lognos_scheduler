"""Settings for Phase 1 - Self-contained configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, AnyUrl
from typing import List


class Settings(BaseSettings):
    """
    Phase 1 application settings.

    All configuration loaded from .env file in project root.
    """

    # Environment
    env: str = "development"

    # Supabase (database)
    supabase_url: AnyUrl
    supabase_service_role_key: str
    supabase_jwt_secret: str | None = None

    # LLM APIs
    google_api_key: str | None = None  # For Gemini models via Pydantic AI
    gemini_api_key: str | None = None  # Deprecated: Use google_api_key instead

    # Observability
    logfire_token: str | None = None

    # FastAPI Server
    api_host: str = "0.0.0.0"
    api_port: int = 8400  # Phase 1 runs on 7000 (backend uses 8400)
    allow_origins: str = "http://localhost:3000"  # comma-separated CORS origins

    # Microsoft Graph (for email operations)
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    bio4_agent_email_address: (
        str  # Agent sender email (BIO4_AGENT_EMAIL_ADDRESS in .env)
    )
    bio4_lognos_user_id: str  # Azure AD User ID for bio4@lognos.io mailbox

    # Model behavior configuration (prevent token exhaustion)
    model_name: str = (
        "google-gla:gemini-3-flash-preview"  # Primary model for all agents
    )
    audio_model_name: str = (
        "google-gla:gemini-2.0-flash"  # Audio-capable model for voice transcription
    )
    doc_processor_model_name: str = (
        "gemini-3-flash-preview"  # Model for attachment processing (google-genai SDK, no prefix)
    )
    model_max_tokens: int = 8192  # Maximum output tokens (thinking + response)
    model_thinking_budget: int = (
        4096  # Gemini thinking tokens limit (0-24576 or -1 for dynamic)
    )
    model_temperature: float = 0.3  # Lower = more focused/predictable (0.0-2.0)
    model_request_limit: int = 10  # Max agent iterations (UsageLimits.request_limit - prevents infinite tool loops)

    # Risk Management Settings
    risk_similarity_threshold: float = (
        0.75  # >= this (< duplicate): create DUPLICATE link
    )
    risk_duplicate_threshold: float = 0.85  # >= this: exact duplicate, skip creation
    risk_related_threshold: float = 0.60  # >= this (< similarity): create RELATED link
    risk_embedding_dimensions: int = 1536  # Must match vector(1536) in DB
    risk_max_reviewers: int = 3  # Maximum reviewers per risk/action

    # Auto-Sync Configuration
    auto_sync_debounce_minutes: int = 1  # Minutes to wait before syncing stale chats

    # Telegram
    telegram_bot_token: str | None = None
    telegram_mode: str = "polling"  # 'polling' or 'webhook'
    telegram_project_id: str | None = None  # Force a specific project ID for this bot

    # Backend URL (for pg_cron to call back)
    backend_url: str = "http://localhost:8400"  # Override in production

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields from .env
    )

    @property
    def allow_origins_list(self) -> List[str]:
        """Parse comma-separated CORS origins into list."""
        return [o.strip() for o in self.allow_origins.split(",") if o.strip()]

    @field_validator("supabase_service_role_key")
    @classmethod
    def ensure_service_key_present(cls, v: str) -> str:
        """Validate Supabase service role key is provided."""
        if not v or v.strip() == "***":
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required.")
        return v


# Singleton settings instance
settings = Settings()
