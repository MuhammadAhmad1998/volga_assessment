from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration for the transcription service."""

    # Whisper model: tiny / base / small / medium / large-v3
    # "tiny" is fast for demos; use "base" or larger for better accuracy.
    whisper_model: str = "tiny"
    whisper_device: str = "cpu"  # "cuda" if a GPU is available
    whisper_compute_type: str = "int8"  # int8 on CPU, float16 on GPU

    # Audio normalization target for Whisper
    target_sample_rate: int = 16000
    target_channels: int = 1

    # Long-audio chunking (seconds). Files longer than this are split.
    chunk_seconds: float = 300.0  # 5 minutes
    chunk_overlap_seconds: float = 1.0

    # Storage paths
    upload_dir: Path = Path("uploads")
    output_dir: Path = Path("outputs")

    # Job retries
    max_retries: int = 3

    class Config:
        env_prefix = "VOLGA_"


settings = Settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.output_dir.mkdir(parents=True, exist_ok=True)
