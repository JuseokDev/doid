from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str

    DATABASE_HOST: str = "mongodb"
    DATABASE_PORT: int = 27017
    DATABASE_USERNAME: str | None = None
    DATABASE_PASSWORD: str | None = None
    DATABASE_NAME: str = "database"

    LAVALINK_HOST: str = "lavalink"
    LAVALINK_PORT: int = 2333
    LAVALINK_PASSWORD: str = "youshallnotpass"
    LAVALINK_REGION: str = "us"
    LAVALINK_NAME: str = "default-node"

    MAX_VOLUME: int = 100

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
