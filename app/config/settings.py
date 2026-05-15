from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QuantSandbox v2"
    app_env: str = "dev"
    app_debug: bool = True

    project_root: Path = Path("/root/project/quantsandbox_v2")
    data_dir: Path = Path("/root/project/quantsandbox_v2/data")
    db_path: Path = Path("/root/project/quantsandbox_v2/data/db/quantsandbox_v2.sqlite3")
    reports_dir: Path = Path("/root/project/quantsandbox_v2/data/reports")
    datasets_dir: Path = Path("/root/project/quantsandbox_v2/data/datasets")
    cache_dir: Path = Path("/root/project/quantsandbox_v2/data/cache")

    market_data_mode: str = "memory"
    fundamental_data_mode: str = "memory"
    market_data_file: Path | None = None
    fundamental_data_file: Path | None = None
    market_data_dir: Path | None = None
    fundamental_data_dir: Path | None = None

    tushare_token: str | None = None
    tushare_http_url: str | None = None
    tushare_price_adjust: str = "qfq"
    tushare_market_requests_per_minute: float = 120.0
    tushare_fundamental_requests_per_minute: float = 90.0
    tushare_retry_requests_per_minute: float = 30.0

    default_benchmark: str = "equal_weight_universe"
    default_commission_bps: float = 10.0
    default_slippage_bps: float = 5.0

    model_config = SettingsConfigDict(
        env_prefix="QS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
