from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "CrisisNet API"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_v1_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:8081,http://localhost:3000"
    openai_api_key: str = ""
    openai_weather_model: str = "gpt-4.1-mini"    
    expo_public_mapbox_access_token: str = "pk.eyJ1IjoiZm9vZXliYXIiLCJhIjoiY21tcGp6aDF6MHFneTJ2cTNyOXh3cW41NyJ9.6PMiffhePPTrBR99RugqHQ"
    mapbox_downloads_token: str = "sk.eyJ1IjoiZm9vZXliYXIiLCJhIjoiY21tcGszNmNyMHIxODJzcHQyY295aWhxciJ9.J5HntU5r3w6Mqj_IAwzo7A"
    @property
    def mapbox_access_token(self) -> str:
        """Mapbox public token used for Directions API calls."""
        return self.expo_public_mapbox_access_token

    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )


settings = Settings()

