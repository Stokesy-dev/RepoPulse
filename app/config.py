from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "mysql+pymysql://repopulse:repopulse@localhost:3306/repopulse"

    # GitHub API
    github_token: str = ""

    # Application
    app_env: str = "development"
    log_level: str = "info"


settings = Settings()
