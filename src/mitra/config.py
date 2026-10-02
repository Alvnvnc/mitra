"""Central configuration for Mitra.

All values come from environment variables (see .env.example).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]  # src/mitra/config.py -> repo root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Nebius Token Factory ---
    nebius_api_key: str = ""
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"

    # --- Model routing (purpose -> model id) ---
    mitra_model_fast: str = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"
    mitra_model_chat: str = "nvidia/nemotron-3-super-120b-a12b"
    mitra_model_reasoning: str = "nvidia/Nemotron-3-Ultra-550b-a55b"

    # --- Interfaces ---
    telegram_bot_token: str = ""

    # --- Tools ---
    tavily_api_key: str = ""

    # --- Misc ---
    mitra_data_dir: Path = REPO_ROOT / "data"
    log_level: str = "INFO"

    def model_map(self) -> dict[str, str]:
        """Purpose -> model id, as used by the router."""
        return {
            "fast": self.mitra_model_fast,
            "chat": self.mitra_model_chat,
            "reasoning": self.mitra_model_reasoning,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()