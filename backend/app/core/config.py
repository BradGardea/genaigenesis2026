from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CrisisNet API"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:8081,http://localhost:3000"
    expo_public_mapbox_access_token: str = ""
    mapbox_downloads_token: str = ""

    @property
    def mapbox_access_token(self) -> str:
        """Mapbox public token used for Directions API calls."""
        return self.expo_public_mapbox_access_token

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )


settings = Settings()

