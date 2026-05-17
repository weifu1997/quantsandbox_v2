from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "QuantSandbox v2"
    app_env: str = "dev"
    app_debug: bool = True

    project_root: Path = Path("/root/project/quantsandbox_v2")
    data_dir: Path | None = None
    db_path: Path | None = None
    reports_dir: Path | None = None
    datasets_dir: Path | None = None
    cache_dir: Path | None = None

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
    min_sample_trading_days: int = 60
    min_sample_listed_days: int = 120

    model_config = SettingsConfigDict(
        env_prefix="QS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def derive_paths(self) -> "Settings":
        project_root = Path(self.project_root)
        data_dir = Path(self.data_dir) if self.data_dir is not None else project_root / "data"
        self.project_root = project_root
        self.data_dir = data_dir
        self.db_path = Path(self.db_path) if self.db_path is not None else data_dir / "db" / "quantsandbox_v2.sqlite3"
        self.reports_dir = Path(self.reports_dir) if self.reports_dir is not None else data_dir / "reports"
        self.datasets_dir = Path(self.datasets_dir) if self.datasets_dir is not None else data_dir / "datasets"
        self.cache_dir = Path(self.cache_dir) if self.cache_dir is not None else data_dir / "cache"
        return self


def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    return settings
