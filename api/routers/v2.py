"""
V2 API routes for Podcast TTS functionality.

These endpoints use the {success, data, error} response format.
"""
import uuid
import os
import logging
import numpy as np
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from ..config import settings
from ..models.schemas import (
    V2VoiceInfo,
    V2VoiceListData,
    V2VoiceListResponse,
    V2ErrorResponse,
    PodcastGenerateRequest,
    PodcastGenerateResponse,
    PodcastGenerateData,
    PodcastSegmentTimeline,
    VoiceUpdateRequest,
    V2VoiceUpdateResponse,
)
from ..services.voice_service import get_voice_service
from ..services.tts_service import get_tts_service
from ..utils.cleanup import get_audio_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2", tags=["v2-podcast"])


def make_error_response(error: str) -> dict:
    """Create a standard v2 error response."""
    return {"success": False, "data": None, "error": error}


# ============== Voice List ==============

@router.get(
    "/tts/voices",
    response_model=V2VoiceListResponse,
    responses={
        500: {"model": V2ErrorResponse, "description": "Server error"},
    },
    summary="获取音色列表",
    description="获取可用音色列表，支持筛选 Podcast 适用音色。"
)
async def get_voices(
    for_podcast: bool = Query(False, description="是否只返回 Podcast 适用音色"),
):
    """Get list of available voices with optional Podcast filtering."""
    try:
        voice_service = get_voice_service()
        voices = voice_service.list_voices()
        
        # Filter by for_podcast if requested
        if for_podcast:
            voices = [v for v in voices if v.get("for_podcast", False)]
        
        # Convert to V2 format
        voice_list = []
        for v in voices:
            voice_id = v["voice_uuid"]
            voice_list.append(V2VoiceInfo(
                voice_id=voice_id,
                voice_name=v["voice_name"],
                description=v.get("description", ""),
                suitable_for=v.get("suitable_for", []),
                for_podcast=v.get("for_podcast", False),
                sample_audio_url=f"/api/v2/voices/{voice_id}/sample",
            ))
        
        return V2VoiceListResponse(
            success=True,
            data=V2VoiceListData(voices=voice_list),
            error=None,
        )
    
    except Exception as e:
        logger.error(f"Failed to get voices: {e}")
        return V2VoiceListResponse(
            success=False,
            data=None,
            error=f"获取音色列表失败: {str(e)}",
        )


# ============== Voice Sample Audio ==============

@router.get(
    "/voices/{voice_id}/sample",
    responses={
        404: {"model": V2ErrorResponse, "description": "Voice not found"},
    },
    summary="获取音色示例音频",
    description="返回音色的参考音频文件。"
)
async def get_voice_sample(voice_id: str):
    """Get the sample audio file for a voice."""
    voice_service = get_voice_service()
    
    audio_path = voice_service.get_voice_audio_path(voice_id)
    if not audio_path:
        raise HTTPException(
            status_code=404,
            detail=make_error_response(f"音色不存在: {voice_id}")
        )
    
    # Determine content type from file extension
    ext = audio_path.suffix.lower()
    content_type_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    content_type = content_type_map.get(ext, "audio/wav")
    
    return FileResponse(
        path=str(audio_path),
        media_type=content_type,
        filename=f"sample{ext}",
    )


# ============== Podcast Generate ==============

@router.post(
    "/tts/podcast/generate",
    response_model=PodcastGenerateResponse,
    responses={
        400: {"model": V2ErrorResponse, "description": "Invalid request"},
        404: {"model": V2ErrorResponse, "description": "Voice not found"},
        500: {"model": V2ErrorResponse, "description": "Server error"},
    },
    summary="生成 Podcast 音频",
    description="生成 Podcast 音频，返回带段落时间轴的结果。"
)
async def generate_podcast(request: PodcastGenerateRequest):
    """
    Generate Podcast audio with segment-level timeline.
    
    Each segment is generated independently, and the actual audio duration
    is used to calculate precise timeline information.
    """
    try:
        # Validate voice exists
        voice_service = get_voice_service()
        voice = voice_service.get_voice(request.voice_id)
        
        if not voice:
            return PodcastGenerateResponse(
                success=False,
                data=None,
                error=f"音色不存在: {request.voice_id}",
            )
        
        # Validate segments
        if not request.segments:
            return PodcastGenerateResponse(
                success=False,
                data=None,
                error="segments 不能为空",
            )
        
        # Sort segments by index
        sorted_segments = sorted(request.segments, key=lambda s: s.segment_index)
        
        # Get TTS service and generate audio for each segment
        tts_service = get_tts_service()
        await tts_service._ensure_model_loaded()
        
        all_audio_chunks: List[np.ndarray] = []
        timeline_results: List[PodcastSegmentTimeline] = []
        current_time_ms = 0
        
        prompt_wav_path = str(voice_service.get_voice_audio_path(request.voice_id))
        prompt_text = voice["prompt_text"]
        
        logger.info(f"Generating podcast with {len(sorted_segments)} segments")
        
        for seg in sorted_segments:
            logger.info(f"Generating segment {seg.segment_index}: {seg.content[:50]}...")
            
            # Generate audio for this segment
            audio, sample_rate, _ = await tts_service.generate(
                text=seg.content,
                voice_uuid=request.voice_id,
            )
            
            # Calculate precise duration from actual audio samples
            duration_samples = len(audio)
            duration_ms = int(duration_samples / sample_rate * 1000)
            
            # Record timeline
            timeline_results.append(PodcastSegmentTimeline(
                segment_index=seg.segment_index,
                start_time_ms=current_time_ms,
                end_time_ms=current_time_ms + duration_ms,
            ))
            
            current_time_ms += duration_ms
            all_audio_chunks.append(audio)
            
            logger.info(f"Segment {seg.segment_index} generated: {duration_ms}ms")
        
        # Concatenate all audio
        if len(all_audio_chunks) > 1:
            final_audio = np.concatenate(all_audio_chunks)
        else:
            final_audio = all_audio_chunks[0]
        
        total_duration_ms = current_time_ms
        total_duration_seconds = total_duration_ms / 1000.0
        
        # Save audio file
        audio_id = str(uuid.uuid4())
        audio_bytes = tts_service.audio_to_bytes(final_audio, request.output_format)
        audio_file_size = len(audio_bytes)
        
        audio_manager = get_audio_manager()
        meta = audio_manager.save_audio(
            audio_id=audio_id,
            audio_data=audio_bytes,
            format=request.output_format,
            sample_rate=sample_rate,
            duration_seconds=total_duration_seconds,
        )
        
        audio_url = f"/downloads/{audio_id}"
        
        logger.info(f"Podcast generated: {total_duration_seconds:.2f}s, {audio_file_size} bytes")
        
        return PodcastGenerateResponse(
            success=True,
            data=PodcastGenerateData(
                audio_url=audio_url,
                audio_file_size=audio_file_size,
                duration_seconds=round(total_duration_seconds, 3),
                duration_ms=total_duration_ms,
                segments=timeline_results,
            ),
            error=None,
        )
    
    except ValueError as e:
        logger.error(f"Podcast generation error: {e}")
        return PodcastGenerateResponse(
            success=False,
            data=None,
            error=str(e),
        )
    except Exception as e:
        import traceback
        logger.error(f"Podcast generation failed: {traceback.format_exc()}")
        return PodcastGenerateResponse(
            success=False,
            data=None,
            error=f"生成失败: {str(e)}",
        )


# ============== Voice Update ==============

@router.patch(
    "/voices/{voice_id}",
    response_model=V2VoiceUpdateResponse,
    responses={
        404: {"model": V2ErrorResponse, "description": "Voice not found"},
        500: {"model": V2ErrorResponse, "description": "Server error"},
    },
    summary="编辑音色元数据",
    description="更新音色的元数据信息，支持修改 voice_name、description、suitable_for、for_podcast 字段。"
)
async def update_voice(voice_id: str, request: VoiceUpdateRequest):
    """
    Update voice metadata.
    
    Only provided fields will be updated, others remain unchanged.
    """
    try:
        voice_service = get_voice_service()
        
        # Check if voice exists
        if not voice_service.voice_exists(voice_id):
            return V2VoiceUpdateResponse(
                success=False,
                data=None,
                error=f"音色不存在: {voice_id}",
            )
        
        # Update voice
        updated = voice_service.update_voice(
            voice_uuid=voice_id,
            voice_name=request.voice_name,
            description=request.description,
            suitable_for=request.suitable_for,
            for_podcast=request.for_podcast,
        )
        
        if not updated:
            return V2VoiceUpdateResponse(
                success=False,
                data=None,
                error="更新失败",
            )
        
        # Return updated voice info
        return V2VoiceUpdateResponse(
            success=True,
            data=V2VoiceInfo(
                voice_id=updated["voice_uuid"],
                voice_name=updated["voice_name"],
                description=updated.get("description", ""),
                suitable_for=updated.get("suitable_for", []),
                for_podcast=updated.get("for_podcast", False),
                sample_audio_url=f"/api/v2/voices/{voice_id}/sample",
            ),
            error=None,
        )
    
    except Exception as e:
        logger.error(f"Failed to update voice: {e}")
        return V2VoiceUpdateResponse(
            success=False,
            data=None,
            error=f"更新失败: {str(e)}",
        )
