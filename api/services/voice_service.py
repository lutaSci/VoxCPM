"""
Voice management service for storing and retrieving voice profiles.
"""
import os
import json
import uuid
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from threading import Lock

from ..config import settings


class VoiceService:
    """
    Service for managing voice profiles (参考音色).
    
    Stores:
    - Audio files in: {voices_dir}/{voice_uuid}/audio.wav
    - Metadata in: {voices_dir}/voices.json
    """
    
    def __init__(self, voices_dir: str = None):
        """
        Initialize voice service.
        
        Args:
            voices_dir: Directory to store voice files
        """
        self.voices_dir = Path(voices_dir or settings.voices_dir)
        self.voices_dir.mkdir(parents=True, exist_ok=True)
        
        self.metadata_file = self.voices_dir / "voices.json"
        self._lock = Lock()
        
        # Load existing metadata
        self._metadata: Dict[str, Dict[str, Any]] = self._load_metadata()
    
    def _load_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Load metadata from JSON file."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_metadata(self):
        """Save metadata to JSON file."""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2, default=str)
    
    def create_voice(
        self,
        audio_data: bytes,
        voice_name: str,
        prompt_text: str,
        audio_format: str = "wav"
    ) -> Dict[str, Any]:
        """
        Create a new voice profile.
        
        Args:
            audio_data: Raw audio bytes
            voice_name: Name for the voice
            prompt_text: Text corresponding to the audio
            audio_format: Audio file format (default: wav)
            
        Returns:
            Voice metadata dict
        """
        voice_uuid = str(uuid.uuid4())
        voice_dir = self.voices_dir / voice_uuid
        voice_dir.mkdir(parents=True, exist_ok=True)
        
        # Save audio file
        audio_filename = f"audio.{audio_format}"
        audio_path = voice_dir / audio_filename
        with open(audio_path, 'wb') as f:
            f.write(audio_data)
        
        # Create metadata
        now = datetime.utcnow()
        metadata = {
            "voice_uuid": voice_uuid,
            "voice_name": voice_name,
            "prompt_text": prompt_text,
            "audio_filename": audio_filename,
            "created_at": now.isoformat(),
        }
        
        # Store metadata
        with self._lock:
            self._metadata[voice_uuid] = metadata
            self._save_metadata()
        
        return metadata
    
    def get_voice(self, voice_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get voice metadata by UUID.
        
        Args:
            voice_uuid: Voice UUID
            
        Returns:
            Voice metadata dict or None if not found
        """
        return self._metadata.get(voice_uuid)
    
    def get_voice_audio_path(self, voice_uuid: str) -> Optional[Path]:
        """
        Get the audio file path for a voice.
        
        Args:
            voice_uuid: Voice UUID
            
        Returns:
            Path to audio file or None if not found
        """
        voice = self.get_voice(voice_uuid)
        if not voice:
            return None
        
        audio_path = self.voices_dir / voice_uuid / voice["audio_filename"]
        if audio_path.exists():
            return audio_path
        return None
    
    def list_voices(self) -> List[Dict[str, Any]]:
        """
        List all voices.
        
        Returns:
            List of voice metadata dicts
        """
        return list(self._metadata.values())
    
    def delete_voice(self, voice_uuid: str) -> bool:
        """
        Delete a voice profile.
        
        Args:
            voice_uuid: Voice UUID
            
        Returns:
            True if deleted, False if not found
        """
        if voice_uuid not in self._metadata:
            return False
        
        # Remove directory
        voice_dir = self.voices_dir / voice_uuid
        if voice_dir.exists():
            shutil.rmtree(voice_dir)
        
        # Remove from metadata
        with self._lock:
            del self._metadata[voice_uuid]
            self._save_metadata()
        
        return True
    
    def voice_exists(self, voice_uuid: str) -> bool:
        """Check if a voice exists."""
        return voice_uuid in self._metadata


# Singleton instance
_voice_service: Optional[VoiceService] = None


def get_voice_service() -> VoiceService:
    """Get the global voice service instance."""
    global _voice_service
    if _voice_service is None:
        _voice_service = VoiceService()
    return _voice_service
