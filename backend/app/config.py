from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env ligger i prosjektrot (to nivåer opp fra denne filen)
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"


class Settings(BaseSettings):
    database_url: str
    api_secret_key: str = "dev-secret"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    admin_api_key: str = "dev-admin-key"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
