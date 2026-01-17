"""
TTS Service - Core service for text-to-speech generation.
Handles model loading, text splitting, and audio generation.
"""
import os
import sys
import io
import uuid
import base64
import tempfile
import asyncio
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List, Tuple, AsyncGenerator, Dict, Any
from pathlib import Path
import logging
import soundfile as sf

from ..config import settings
from ..utils.text_splitter import smart_split
from .voice_service import get_voice_service

logger = logging.getLogger(__name__)


class TTSService:
    """
    TTS Service that wraps VoxCPM model and provides async interface.
    
    Features:
    - Lazy model loading
    - Async-friendly inference via thread pool
    - Automatic text splitting for long inputs
    - Support for both stored and temporary voice profiles
    - ASR for automatic prompt text recognition
    """
    
    def __init__(self):
        """Initialize TTS service (model loaded lazily)."""
        self._model = None
        self._asr_model = None
        self._model_lock = asyncio.Lock()
        self._executor = ThreadPoolExecutor(max_workers=settings.worker_count)
        self._sample_rate: Optional[int] = None
    
    @property
    def sample_rate(self) -> int:
        """Get model sample rate."""
        if self._sample_rate is None:
            raise RuntimeError("Model not loaded yet")
        return self._sample_rate
    
    async def _ensure_model_loaded(self):
        """Ensure model is loaded (lazy loading)."""
        if self._model is not None:
            return
        
        async with self._model_lock:
            if self._model is not None:
                return
            
            logger.info("Loading VoxCPM model...")
            
            # Load in thread to avoid blocking
            def load_model():
                import voxcpm
                
                model_path = settings.model_path
                if model_path and os.path.isdir(model_path):
                    # Use local path
                    return voxcpm.VoxCPM(
                        voxcpm_model_path=model_path,
                        zipenhancer_model_path=settings.zipenhancer_model_path if settings.enable_denoiser else None,
                        enable_denoiser=settings.enable_denoiser,
                    )
                else:
                    # Download from HuggingFace
                    return voxcpm.VoxCPM.from_pretrained(
                        hf_model_id=settings.hf_model_id,
                        load_denoiser=settings.enable_denoiser,
                        zipenhancer_model_id=settings.zipenhancer_model_path,
                    )
            
            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(self._executor, load_model)
            self._sample_rate = self._model.tts_model.sample_rate
            logger.info(f"VoxCPM model loaded. Sample rate: {self._sample_rate}")
    
    async def _ensure_asr_loaded(self):
        """Ensure ASR model is loaded for prompt text recognition."""
        if self._asr_model is not None:
            return
        
        async with self._model_lock:
            if self._asr_model is not None:
                return
            
            logger.info("Loading ASR model...")
            
            def load_asr():
                from funasr import AutoModel
                import torch
                device = "cuda:0" if torch.cuda.is_available() else "cpu"
                return AutoModel(
                    model=settings.asr_model_id,
                    disable_update=True,
                    log_level='ERROR',
                    device=device,
                )
            
            loop = asyncio.get_event_loop()
            self._asr_model = await loop.run_in_executor(self._executor, load_asr)
            logger.info("ASR model loaded.")
    
    async def recognize_prompt_text(self, audio_path: str) -> str:
        """
        Recognize text from prompt audio using ASR.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            Recognized text
        """
        await self._ensure_asr_loaded()
        
        def do_asr():
            res = self._asr_model.generate(input=audio_path, language="auto", use_itn=True)
            text = res[0]["text"].split('|>')[-1]
            return text
        
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, do_asr)
    
    async def generate(
        self,
        text: str,
        voice_uuid: Optional[str] = None,
        temp_audio_base64: Optional[str] = None,
        temp_prompt_text: Optional[str] = None,
        cfg_value: Optional[float] = None,
        inference_timesteps: Optional[int] = None,
        normalize: bool = False,
        denoise: bool = False,
    ) -> Tuple[np.ndarray, int, List[str]]:
        """
        Generate speech from text.
        
        Args:
            text: Text to synthesize
            voice_uuid: UUID of stored voice profile
            temp_audio_base64: Base64 encoded temporary audio
            temp_prompt_text: Text for temporary audio
            cfg_value: CFG guidance value
            inference_timesteps: Number of inference steps
            normalize: Whether to normalize text
            denoise: Whether to denoise prompt audio
            
        Returns:
            Tuple of (audio_array, sample_rate, segments)
        """
        await self._ensure_model_loaded()
        
        # Resolve parameters
        cfg = cfg_value or settings.default_cfg_value
        steps = inference_timesteps or settings.default_inference_timesteps
        
        # Resolve voice profile
        prompt_wav_path = None
        prompt_text = None
        temp_file = None
        
        try:
            if voice_uuid:
                # Use stored voice
                voice_service = get_voice_service()
                voice = voice_service.get_voice(voice_uuid)
                if not voice:
                    raise ValueError(f"Voice not found: {voice_uuid}")
                
                prompt_wav_path = str(voice_service.get_voice_audio_path(voice_uuid))
                prompt_text = voice["prompt_text"]
                
            elif temp_audio_base64:
                # Use temporary voice
                audio_bytes = base64.b64decode(temp_audio_base64)
                temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                temp_file.write(audio_bytes)
                temp_file.close()
                prompt_wav_path = temp_file.name
                
                # Get prompt text (auto ASR if not provided)
                if temp_prompt_text:
                    prompt_text = temp_prompt_text
                else:
                    prompt_text = await self.recognize_prompt_text(prompt_wav_path)
            
            # Split text into segments
            segments = smart_split(text, max_length=settings.split_max_length)
            logger.info(f"Text split into {len(segments)} segments")
            
            # Generate audio for each segment (serially)
            all_audio = []
            
            for i, segment in enumerate(segments):
                logger.info(f"Generating segment {i+1}/{len(segments)}: {segment[:50]}...")
                
                # Capture variables for closure
                _segment = segment
                _prompt_wav_path = prompt_wav_path
                _prompt_text = prompt_text
                _cfg = cfg
                _steps = steps
                _normalize = normalize
                _denoise = denoise
                
                def generate_segment():
                    try:
                        return self._model.generate(
                            text=_segment,
                            prompt_wav_path=_prompt_wav_path,
                            prompt_text=_prompt_text,
                            cfg_value=_cfg,
                            inference_timesteps=_steps,
                            normalize=_normalize,
                            denoise=_denoise,
                        )
                    except Exception as e:
                        import traceback
                        logger.error(f"Model generate error: {traceback.format_exc()}")
                        raise
                
                loop = asyncio.get_event_loop()
                wav = await loop.run_in_executor(self._executor, generate_segment)
                all_audio.append(wav)
            
            # Concatenate all segments
            final_audio = np.concatenate(all_audio) if len(all_audio) > 1 else all_audio[0]
            
            return final_audio, self._sample_rate, segments
            
        finally:
            # Cleanup temp file
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass
    
    async def generate_streaming(
        self,
        text: str,
        voice_uuid: Optional[str] = None,
        temp_audio_base64: Optional[str] = None,
        temp_prompt_text: Optional[str] = None,
        cfg_value: Optional[float] = None,
        inference_timesteps: Optional[int] = None,
        normalize: bool = False,
        denoise: bool = False,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Generate speech with streaming response.
        
        Yields events:
        - {"event": "progress", "segment": n, "total_segments": total, "status": "processing"}
        - {"event": "audio_chunk", "segment": n, "audio_base64": "...", "duration": x.x}
        - {"event": "done", "total_duration_seconds": x.x, "total_segments": n}
        - {"event": "error", "message": "..."}
        """
        await self._ensure_model_loaded()
        
        # Resolve parameters
        cfg = cfg_value or settings.default_cfg_value
        steps = inference_timesteps or settings.default_inference_timesteps
        
        # Resolve voice profile
        prompt_wav_path = None
        prompt_text = None
        temp_file = None
        
        try:
            if voice_uuid:
                voice_service = get_voice_service()
                voice = voice_service.get_voice(voice_uuid)
                if not voice:
                    yield {"event": "error", "message": f"Voice not found: {voice_uuid}"}
                    return
                
                prompt_wav_path = str(voice_service.get_voice_audio_path(voice_uuid))
                prompt_text = voice["prompt_text"]
                
            elif temp_audio_base64:
                audio_bytes = base64.b64decode(temp_audio_base64)
                temp_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
                temp_file.write(audio_bytes)
                temp_file.close()
                prompt_wav_path = temp_file.name
                
                if temp_prompt_text:
                    prompt_text = temp_prompt_text
                else:
                    prompt_text = await self.recognize_prompt_text(prompt_wav_path)
            
            # Split text
            segments = smart_split(text, max_length=settings.split_max_length)
            total_segments = len(segments)
            total_duration = 0.0
            
            for i, segment in enumerate(segments):
                # Progress event
                yield {
                    "event": "progress",
                    "segment": i + 1,
                    "total_segments": total_segments,
                    "status": "processing"
                }
                
                # Capture variables for closure
                _segment = segment
                _prompt_wav_path = prompt_wav_path
                _prompt_text = prompt_text
                _cfg = cfg
                _steps = steps
                _normalize = normalize
                _denoise = denoise
                
                # Generate
                def generate_segment():
                    try:
                        return self._model.generate(
                            text=_segment,
                            prompt_wav_path=_prompt_wav_path,
                            prompt_text=_prompt_text,
                            cfg_value=_cfg,
                            inference_timesteps=_steps,
                            normalize=_normalize,
                            denoise=_denoise,
                        )
                    except Exception as e:
                        import traceback
                        logger.error(f"Model generate error: {traceback.format_exc()}")
                        raise
                
                loop = asyncio.get_event_loop()
                wav = await loop.run_in_executor(self._executor, generate_segment)
                
                # Convert to base64
                buffer = io.BytesIO()
                sf.write(buffer, wav, self._sample_rate, format='WAV')
                audio_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                
                duration = len(wav) / self._sample_rate
                total_duration += duration
                
                yield {
                    "event": "audio_chunk",
                    "segment": i + 1,
                    "audio_base64": audio_base64,
                    "duration": round(duration, 3)
                }
            
            # Done event
            yield {
                "event": "done",
                "total_duration_seconds": round(total_duration, 3),
                "total_segments": total_segments
            }
            
        except Exception as e:
            logger.error(f"Streaming generation error: {e}")
            yield {"event": "error", "message": str(e)}
            
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except OSError:
                    pass
    
    def audio_to_bytes(self, audio: np.ndarray, format: str = "wav") -> bytes:
        """
        Convert numpy audio array to bytes.
        
        Args:
            audio: Audio array
            format: Output format (wav, mp3)
            
        Returns:
            Audio bytes
        """
        buffer = io.BytesIO()
        
        if format.lower() == "mp3":
            # Write as WAV first, then convert
            # Note: soundfile doesn't support MP3 directly
            # For simplicity, we'll use WAV. MP3 would require pydub or similar
            sf.write(buffer, audio, self._sample_rate, format='WAV')
            logger.warning("MP3 format requested but returning WAV (MP3 requires additional dependencies)")
        else:
            sf.write(buffer, audio, self._sample_rate, format='WAV')
        
        return buffer.getvalue()
    
    def audio_to_base64(self, audio: np.ndarray, format: str = "wav") -> str:
        """
        Convert numpy audio array to base64 string.
        
        Args:
            audio: Audio array
            format: Output format
            
        Returns:
            Base64 encoded string
        """
        audio_bytes = self.audio_to_bytes(audio, format)
        return base64.b64encode(audio_bytes).decode('utf-8')


# Singleton instance
_tts_service: Optional[TTSService] = None


def get_tts_service() -> TTSService:
    """Get the global TTS service instance."""
    global _tts_service
    if _tts_service is None:
        _tts_service = TTSService()
    return _tts_service
