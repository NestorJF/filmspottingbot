from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILMSPOTTING_", env_file=".env", extra="ignore")

    library_dir: Path = Path("library")
    data_dir: Path = Path("data")
    model: str = "claude-sonnet-5-5"
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "library.db"

    @property
    def checkpoints_path(self) -> Path:
        return self.data_dir / "checkpoints.db"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
