from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BYBIT_")

    db_url: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/bybit_tool")
    default_market_type: str = Field(default="linear")


settings = Settings()
