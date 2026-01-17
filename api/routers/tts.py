"""
TTS generation API routes.
"""
import uuid
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

from ..config import settings
from ..models.schemas import (
    TTSGenerateRequest,
    TTSGenerateResponse,
    ErrorResponse,
)
from ..services.tts_service import get_tts_service
from ..utils.cleanup import get_audio_manager

router = APIRouter(prefix="/tts", tags=["tts"])


@router.post(
    "/generate",
    response_model=TTSGenerateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Voice not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="同步TTS生成",
    description="""
    将文本转换为语音。支持以下功能：
    - 使用已上传的音色（通过voice_uuid）
    - 使用临时音色（通过temp_audio_base64）
    - 不使用参考音色（模型自由发挥）
    - 自动拆分长文本以保证生成质量
    """
)
async def generate_tts(request: TTSGenerateRequest):
    """Generate speech from text (synchronous)."""
    # Validate request
    if len(request.text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    if len(request.text) > settings.max_text_length:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long. Maximum length: {settings.max_text_length} characters"
        )
    
    # Can't use both voice_uuid and temp_audio
    if request.voice_uuid and request.temp_audio_base64:
        raise HTTPException(
            status_code=400,
            detail="Cannot use both voice_uuid and temp_audio_base64. Choose one."
        )
    
    try:
        tts_service = get_tts_service()
        
        # Generate audio
        audio, sample_rate, segments = await tts_service.generate(
            text=request.text,
            voice_uuid=request.voice_uuid,
            temp_audio_base64=request.temp_audio_base64,
            temp_prompt_text=request.temp_prompt_text,
            cfg_value=request.cfg_value,
            inference_timesteps=request.inference_timesteps,
            normalize=request.normalize,
            denoise=request.denoise,
        )
        
        duration_seconds = len(audio) / sample_rate
        
        # Handle output format
        if request.output_format == "base64":
            audio_base64 = tts_service.audio_to_base64(audio)
            
            # Handle save_result
            download_url = None
            expires_at = None
            
            if request.save_result:
                audio_bytes = tts_service.audio_to_bytes(audio)
                audio_id = str(uuid.uuid4())
                audio_manager = get_audio_manager()
                meta = audio_manager.save_audio(
                    audio_id=audio_id,
                    audio_data=audio_bytes,
                    format="wav",
                    sample_rate=sample_rate,
                    duration_seconds=duration_seconds,
                )
                download_url = f"/downloads/{audio_id}"
                expires_at = datetime.fromisoformat(meta["expires_at"])
            
            return TTSGenerateResponse(
                audio_base64=audio_base64,
                sample_rate=sample_rate,
                duration_seconds=round(duration_seconds, 3),
                segments=len(segments),
                format="wav",
                download_url=download_url,
                expires_at=expires_at,
            )
        
        else:
            # Return audio file directly
            audio_bytes = tts_service.audio_to_bytes(audio, request.output_format)
            
            # Save if requested
            headers = {}
            if request.save_result:
                audio_id = str(uuid.uuid4())
                audio_manager = get_audio_manager()
                meta = audio_manager.save_audio(
                    audio_id=audio_id,
                    audio_data=audio_bytes,
                    format=request.output_format,
                    sample_rate=sample_rate,
                    duration_seconds=duration_seconds,
                )
                headers["X-Download-URL"] = f"/downloads/{audio_id}"
                headers["X-Expires-At"] = meta["expires_at"]
            
            content_type = "audio/wav" if request.output_format == "wav" else "audio/mpeg"
            
            return Response(
                content=audio_bytes,
                media_type=content_type,
                headers={
                    "Content-Disposition": f"attachment; filename=tts_output.{request.output_format}",
                    "X-Sample-Rate": str(sample_rate),
                    "X-Duration-Seconds": str(round(duration_seconds, 3)),
                    "X-Segments": str(len(segments)),
                    **headers,
                }
            )
    
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        logger.error(f"TTS generation failed: {error_detail}")
        raise HTTPException(status_code=500, detail=f"TTS generation failed: {str(e)}")


@router.post(
    "/generate/stream",
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        404: {"model": ErrorResponse, "description": "Voice not found"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="流式TTS生成 (SSE)",
    description="""
    流式生成语音，使用Server-Sent Events返回音频块。
    
    事件类型：
    - progress: 进度更新
    - audio_chunk: 音频数据块
    - done: 生成完成
    - error: 错误信息
    """
)
async def generate_tts_stream(request: TTSGenerateRequest):
    """Generate speech from text with streaming response (SSE)."""
    # Validate request
    if len(request.text.strip()) == 0:
        raise HTTPException(status_code=400, detail="Text cannot be empty")
    
    if len(request.text) > settings.max_text_length:
        raise HTTPException(
            status_code=400,
            detail=f"Text too long. Maximum length: {settings.max_text_length} characters"
        )
    
    if request.voice_uuid and request.temp_audio_base64:
        raise HTTPException(
            status_code=400,
            detail="Cannot use both voice_uuid and temp_audio_base64. Choose one."
        )
    
    async def event_generator():
        """Generate SSE events."""
        tts_service = get_tts_service()
        
        all_audio_chunks = []
        total_duration = 0.0
        
        async for event in tts_service.generate_streaming(
            text=request.text,
            voice_uuid=request.voice_uuid,
            temp_audio_base64=request.temp_audio_base64,
            temp_prompt_text=request.temp_prompt_text,
            cfg_value=request.cfg_value,
            inference_timesteps=request.inference_timesteps,
            normalize=request.normalize,
            denoise=request.denoise,
        ):
            event_type = event.get("event", "message")
            
            # Collect chunks for potential save
            if event_type == "audio_chunk":
                all_audio_chunks.append(event.get("audio_base64", ""))
                total_duration += event.get("duration", 0)
            
            # Handle save_result on done event
            if event_type == "done" and request.save_result:
                # This is a simplified version - in production you might want to
                # concatenate all chunks properly
                event["download_url"] = None  # Streaming doesn't support save currently
                event["expires_at"] = None
            
            # Format as SSE
            data = json.dumps(event, ensure_ascii=False, default=str)
            yield f"event: {event_type}\ndata: {data}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
