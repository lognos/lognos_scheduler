from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # App
    APP_NAME: str = "P6 Scheduling Agent"
    DEBUG: bool = False
    PORT: int = Field(default=8500, description="Server port")

    # Database - P6 SQLite
    P6_DB_LOC: str = Field(default="p6.db", description="Path to the P6 SQLite database file")

    # Database - Supabase
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(..., description="Supabase anon key")
    SUPABASE_SERVICE_ROLE_KEY: str | None = Field(default=None, description="Supabase service role key (optional)")

    # AI
    GEMINI_API_KEY: str = Field(..., alias="GOOGLE_API_KEY", description="Google Gemini API Key")
    GOOGLE_DEFAULT_MODEL: str = Field(default="google-gla:gemini-3-flash-preview", description="Default Google AI Model")
    LOGFIRE_TOKEN: str | None = Field(default=None, description="Logfire Write Token")

    # Email integration (Phase 0 scaffolding)
    EMAIL_ENABLED: bool = Field(default=False, description="Enable scheduling email subsystem")
    ENABLE_EMAIL_PHASE1_SEND: bool = Field(default=False, description="Enable phase 1 draft/send email tools")
    ENABLE_EMAIL_PHASE2_ATTACHMENTS: bool = Field(default=False, description="Enable phase 2 attachment tools")
    ENABLE_EMAIL_PHASE3_INBOUND: bool = Field(default=False, description="Enable phase 3 inbox/read/respond tools")
    EMAIL_TENANT_ID: str | None = Field(default=None, alias="TENANT_ID", description="Azure tenant id for Microsoft Graph")
    EMAIL_CLIENT_ID: str | None = Field(default=None, alias="CLIENT_ID", description="Azure app client id for Microsoft Graph")
    EMAIL_CLIENT_SECRET: str | None = Field(default=None, alias="CLIENT_SECRET", description="Azure app client secret for Microsoft Graph")
    EMAIL_SENDER_ADDRESS: str | None = Field(default=None, alias="BIO4_AGENT_EMAIL_ADDRESS", description="Mailbox address used as sender")
    EMAIL_MAILBOX_USER_ID: str | None = Field(default=None, alias="BIO4_LOGNOS_USER_ID", description="Mailbox user object id for Graph mailbox operations")

settings = Settings()
