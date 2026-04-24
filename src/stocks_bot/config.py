from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    tbank_token: str
    db_path: str = "data/stocks.db"


def load_settings() -> Settings:
    return Settings()
