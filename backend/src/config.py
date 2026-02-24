from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://norrona:changeme@localhost:5432/norrona_alert"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "change-this-to-a-random-secret"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 15
    refresh_token_expiry_days: int = 30
    magic_link_expiry_minutes: int = 10

    # Resend (email)
    resend_api_key: str = "re_placeholder"
    resend_from_email: str = "alerts@norronaalert.com"

    # VAPID (web push)
    vapid_public_key: str = "placeholder-public-key"
    vapid_private_key: str = "placeholder-private-key"
    vapid_claims_email: str = "mailto:admin@norronaalert.com"

    # APNs (iOS push)
    apns_auth_key_id: str = "KEYID1234"
    apns_team_id: str = "TEAMID1234"
    apns_bundle_id: str = "com.norronaalert.app"
    apns_auth_key_path: str = "./apns_auth_key.p8"
    apns_use_sandbox: bool = True

    # Scraping
    scrape_interval_minutes: int = Field(default=60, ge=60)
    scrape_min_delay_seconds: int = Field(default=30, ge=10)

    # Frontend
    frontend_url: str = "http://localhost:3000"

    # CORS
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]


settings = Settings()
