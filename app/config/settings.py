from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BYBIT_")

    db_url: str = Field(default="postgresql+psycopg://postgres:postgres@localhost:5432/bybit_tool")
    default_market_type: str = Field(default="linear")

    trade_scenarios_breakout_buffer_pct: float = Field(default=0.2)
    trade_scenarios_buy_zone_width_pct: float = Field(default=0.4)
    trade_scenarios_support_invalidation_buffer_pct: float = Field(default=0.2)
    trade_scenarios_tp_levels_count: int = Field(default=3)


settings = Settings()
