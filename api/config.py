"""
VoxCPM API Configuration
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # Model settings
    model_path: str = ""  # Empty = auto download from HF
    hf_model_id: str = "openbmb/VoxCPM1.5"
    enable_denoiser: bool = False  # Disabled by default (requires CUDA, causes issues on Mac/MPS)
    zipenhancer_model_path: str = "iic/speech_zipenhancer_ans_multiloss_16k_base"
    
    # ASR settings (for prompt text recognition)
    asr_model_id: str = "iic/SenseVoiceSmall"
    
    # Storage settings
    voices_dir: str = "./voices"
    generated_audio_dir: str = "./generated"
    
    # TTS settings
    default_cfg_value: float = 2.0
    default_inference_timesteps: int = 10
    max_text_length: int = 5000  # Maximum text length per request
    split_max_length: int = 300  # Max chars per segment for splitting
    
    # Queue settings
    queue_type: Literal["memory", "redis"] = "memory"
    queue_max_size: int = 100
    worker_count: int = 1
    
    # Redis settings (for future scaling)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Cleanup settings
    generated_audio_expire_hours: int = 24
    cleanup_interval_minutes: int = 60
    
    class Config:
        env_prefix = "VOXCPM_"
        env_file = ".env"
        extra = "ignore"


# Global settings instance
settings = Settings()

# Ensure directories exist
Path(settings.voices_dir).mkdir(parents=True, exist_ok=True)
Path(settings.generated_audio_dir).mkdir(parents=True, exist_ok=True)
