from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Homebrew's plain `ffmpeg` lacks libass and zimg; prefer the keg-only `ffmpeg-full` when installed.
FFMPEG_FULL_BIN = Path("/opt/homebrew/opt/ffmpeg-full/bin")


def _binary(name: str) -> str:
    candidate = FFMPEG_FULL_BIN / name
    return str(candidate) if candidate.exists() else name


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILMSPOTTING_", env_file=".env", extra="ignore")

    library_dir: Path = Path("library")
    data_dir: Path = Path("data")
    model: str = "claude-opus-5-5"
    effort: str = "medium"  # low | medium | high | xhigh | max
    ffmpeg: str = Field(default_factory=lambda: _binary("ffmpeg"))
    ffprobe: str = Field(default_factory=lambda: _binary("ffprobe"))

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
