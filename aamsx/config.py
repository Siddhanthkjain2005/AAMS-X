"""Runtime configuration.

Everything is overridable through environment variables (see ``.env.example``)
so the same code runs from a laptop shell, from Docker and from pytest without
edits.  No secret is ever required: the full demo runs from the offline cache.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AAMSX_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- paths -------------------------------------------------------------
    data_dir: Path = Field(default=REPO_ROOT / "data")
    reports_dir: Path = Field(default=REPO_ROOT / "reports" / "out")

    # ---- ingestion ---------------------------------------------------------
    callisto_archive: str = Field(
        default="http://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto",
        description="Root of the public e-CALLISTO FITS archive.",
    )
    http_timeout_sec: float = 45.0
    fetch_concurrency: int = 8
    allow_network: bool = Field(
        default=True,
        description="When false the ingestion layer refuses to touch the network "
        "and only serves the offline Parquet cache.",
    )

    # ---- optional ElectroSense credentials (never required) ----------------
    electrosense_api: str = "https://electrosense.org/api"
    electrosense_user: str | None = None
    electrosense_password: str | None = None

    # ---- measurement -> occupancy conversion -------------------------------
    db_per_digit: float = Field(
        default=0.25,
        description="CALLISTO receivers report power in 'digits'; the network's "
        "documented nominal scale is 0.25 dB per digit.",
    )
    occupancy_threshold_db: float = Field(
        default=1.5,
        description="Absolute floor for the occupancy decision, in dB of excess "
        "power over the channel's quiet-time baseline.",
    )
    occupancy_k_mad: float = Field(
        default=5.0,
        description="Per-channel significance multiplier: a cell counts as "
        "occupied when its excess exceeds k * MAD of that channel's own "
        "fluctuation. Normalises across receivers with very different noise "
        "figures. Reference labels, not absolute ground truth.",
    )
    baseline_percentile: float = Field(
        default=10.0,
        description="Quantile used as each channel's quiet-time baseline. The "
        "median biases upward on busy stations; P10 is stable up to ~50% "
        "occupancy.",
    )

    # ---- experiment engine -------------------------------------------------
    max_concurrent_experiments: int = 4
    event_queue_size: int = 4096
    batch_workers: int = 0  # 0 -> os.cpu_count() - 1
    enable_neural: bool = Field(
        default=False, description="Feature flag for the optional torch modules."
    )
    enable_deep_rl: bool = Field(default=False, description="Feature flag for the DQN policy.")

    # ---- api ---------------------------------------------------------------
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    max_upload_bytes: int = 256 * 1024 * 1024

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cached"

    @property
    def sample_dir(self) -> Path:
        return self.data_dir / "sample"

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def registry_path(self) -> Path:
        return self.data_dir / "registry.sqlite"

    @property
    def traces_dir(self) -> Path:
        return self.data_dir / "traces"

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.cache_dir,
            self.sample_dir,
            self.index_dir,
            self.traces_dir,
            self.reports_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
