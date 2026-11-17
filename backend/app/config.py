"""Application configuration.

All settings come from environment variables (or a local .env file) so that no
secret is ever hardcoded. See `.env.example` at the repository root for the full
list. Pydantic validates types at startup, so a malformed value fails fast
instead of causing a confusing runtime error later.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TableFlow Enterprise"
    environment: str = Field(default="development", description="development | test | staging | production")
    log_level: str = "INFO"

    # --- Database -------------------------------------------------------
    database_url: str = "postgresql+psycopg://tableflow:tableflow@localhost:5432/tableflow"
    auto_create_schema: bool = False  # True only for SQLite-based tests / quick demos

    # --- Security -------------------------------------------------------
    jwt_secret_key: str = Field(default="change-me-in-env", min_length=16)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # Comma separated "provider:key" pairs for digital-ordering partners (API-key auth).
    partner_api_keys: str = "uber_eats:dev-uber-key-change-me,mr_d:dev-mrd-key-change-me"
    # Shared secrets used to verify inbound webhook signatures (HMAC-SHA256).
    webhook_secret_transaction_junction: str = "dev-tj-webhook-secret"
    webhook_secret_uber_eats: str = "dev-uber-webhook-secret"
    webhook_secret_mr_d: str = "dev-mrd-webhook-secret"
    webhook_tolerance_seconds: int = 300
    # Optional: path to the built React app (frontend/dist). When set, the API also serves the UI
    # on the same port - used by the one-click Windows starter so Node.js is not required.
    frontend_dist: str = ""
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost:8080"

    # --- Rate limiting --------------------------------------------------
    rate_limit_partner_per_minute: int = 120
    rate_limit_login_per_minute: int = 20

    # --- Integrations ----------------------------------------------------
    integration_mode: str = "simulated"  # simulated | sandbox (sandbox requires vendor credentials)
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.2
    incident_failure_threshold: int = 3  # consecutive failures before an incident is auto-raised

    # --- n8n automation --------------------------------------------------
    n8n_webhook_base_url: str = ""  # e.g. http://n8n:5678/webhook ; empty = record to outbox only
    n8n_timeout_seconds: float = 5.0
    # Local "alert sink": lets n8n deliver alerts somewhere observable when Slack/Teams/email are not configured.
    alert_sink_token: str = "dev-alert-sink-token"

    # --- Snowflake (optional) -------------------------------------------
    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_warehouse: str = "TABLEFLOW_WH"
    snowflake_database: str = "TABLEFLOW_ANALYTICS"
    snowflake_schema: str = "RAW"
    snowflake_role: str = "TABLEFLOW_LOADER"
    snowflake_private_key_path: str = ""
    snowflake_private_key_passphrase: str = ""

    @property
    def partner_keys(self) -> dict[str, str]:
        pairs = [p.split(":", 1) for p in self.partner_api_keys.split(",") if ":" in p]
        return {k.strip(): v.strip() for k, v in pairs}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
