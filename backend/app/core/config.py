from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CrisisNet API"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:8081,http://localhost:3000"
    openai_api_key: str = ""
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()

