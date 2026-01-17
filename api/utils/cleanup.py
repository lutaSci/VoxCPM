"""
Cleanup utilities for managing temporary files.
"""
import os
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging

from ..config import settings

logger = logging.getLogger(__name__)


class GeneratedAudioManager:
    """
    Manager for generated audio files with expiration.
    
    Stores:
    - Audio files in: {generated_audio_dir}/{audio_id}.{format}
    - Metadata in: {generated_audio_dir}/metadata.json
    """
    
    def __init__(self, generated_dir: str = None, expire_hours: int = None):
        """
        Initialize the manager.
        
        Args:
            generated_dir: Directory for generated audio files
            expire_hours: Hours until files expire
        """
        self.generated_dir = Path(generated_dir or settings.generated_audio_dir)
        self.generated_dir.mkdir(parents=True, exist_ok=True)
        
        self.expire_hours = expire_hours or settings.generated_audio_expire_hours
        self.metadata_file = self.generated_dir / "metadata.json"
        
        self._metadata = self._load_metadata()
    
    def _load_metadata(self) -> dict:
        """Load metadata from file."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_metadata(self):
        """Save metadata to file."""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)
    
    def save_audio(
        self,
        audio_id: str,
        audio_data: bytes,
        format: str,
        sample_rate: int,
        duration_seconds: float
    ) -> dict:
        """
        Save generated audio with metadata.
        
        Args:
            audio_id: Unique ID for the audio
            audio_data: Raw audio bytes
            format: Audio format (wav, mp3)
            sample_rate: Audio sample rate
            duration_seconds: Audio duration
            
        Returns:
            Metadata dict with download info
        """
        filename = f"{audio_id}.{format}"
        filepath = self.generated_dir / filename
        
        # Save audio file
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        
        # Create metadata
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=self.expire_hours)
        
        metadata = {
            "audio_id": audio_id,
            "filename": filename,
            "format": format,
            "sample_rate": sample_rate,
            "duration_seconds": duration_seconds,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }
        
        self._metadata[audio_id] = metadata
        self._save_metadata()
        
        return metadata
    
    def get_audio_path(self, audio_id: str) -> Optional[Path]:
        """
        Get path to generated audio file.
        
        Args:
            audio_id: Audio ID
            
        Returns:
            Path to file or None if not found/expired
        """
        if audio_id not in self._metadata:
            return None
        
        meta = self._metadata[audio_id]
        expires_at = datetime.fromisoformat(meta["expires_at"])
        
        if datetime.utcnow() > expires_at:
            # Expired, clean up
            self._delete_audio(audio_id)
            return None
        
        filepath = self.generated_dir / meta["filename"]
        if filepath.exists():
            return filepath
        return None
    
    def get_audio_info(self, audio_id: str) -> Optional[dict]:
        """Get metadata for an audio file."""
        if audio_id not in self._metadata:
            return None
        
        meta = self._metadata[audio_id]
        expires_at = datetime.fromisoformat(meta["expires_at"])
        
        if datetime.utcnow() > expires_at:
            self._delete_audio(audio_id)
            return None
        
        return meta
    
    def _delete_audio(self, audio_id: str):
        """Delete an audio file and its metadata."""
        if audio_id in self._metadata:
            meta = self._metadata[audio_id]
            filepath = self.generated_dir / meta["filename"]
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError:
                    pass
            del self._metadata[audio_id]
            self._save_metadata()
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired files.
        
        Returns:
            Number of files cleaned up
        """
        now = datetime.utcnow()
        expired_ids = []
        
        for audio_id, meta in list(self._metadata.items()):
            try:
                expires_at = datetime.fromisoformat(meta["expires_at"])
                if now > expires_at:
                    expired_ids.append(audio_id)
            except (KeyError, ValueError):
                expired_ids.append(audio_id)
        
        for audio_id in expired_ids:
            self._delete_audio(audio_id)
        
        logger.info(f"Cleaned up {len(expired_ids)} expired audio files")
        return len(expired_ids)


# Singleton instance
_audio_manager: Optional[GeneratedAudioManager] = None


def get_audio_manager() -> GeneratedAudioManager:
    """Get the global audio manager instance."""
    global _audio_manager
    if _audio_manager is None:
        _audio_manager = GeneratedAudioManager()
    return _audio_manager


async def cleanup_task():
    """Background task to periodically clean up expired files."""
    manager = get_audio_manager()
    interval = settings.cleanup_interval_minutes * 60
    
    while True:
        try:
            await asyncio.sleep(interval)
            manager.cleanup_expired()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Cleanup task error: {e}")
