"""
Voice management API routes.
"""
import tempfile
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, File, Form, UploadFile, HTTPException, status

from ..models.schemas import (
    VoiceResponse,
    VoiceListResponse,
    VoiceDeleteResponse,
    ErrorResponse,
)
from ..services.voice_service import get_voice_service
from ..services.tts_service import get_tts_service

router = APIRouter(prefix="/voices", tags=["voices"])


@router.post(
    "",
    response_model=VoiceResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid request"},
        500: {"model": ErrorResponse, "description": "Server error"},
    },
    summary="上传音色",
    description="上传参考音频创建新的音色配置文件。如果不提供prompt_text，将自动使用ASR识别。支持可选的 Podcast 元数据字段。"
)
async def create_voice(
    audio_file: UploadFile = File(..., description="参考音频文件"),
    voice_name: str = Form(..., min_length=1, max_length=100, description="音色名称"),
    prompt_text: Optional[str] = Form(None, description="参考音频对应的文本，不填则自动ASR识别"),
    description: Optional[str] = Form(None, description="音色描述（Podcast 用）"),
    suitable_for: Optional[str] = Form(None, description="适用场景，逗号分隔（如 daily,family）"),
    for_podcast: bool = Form(False, description="是否适用于 Podcast"),
):
    """Create a new voice profile."""
    # Validate file type
    allowed_types = ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/ogg", "audio/flac"]
    content_type = audio_file.content_type or ""
    
    # Also check by extension
    filename = audio_file.filename or ""
    allowed_extensions = [".wav", ".mp3", ".ogg", ".flac", ".m4a"]
    ext = os.path.splitext(filename)[1].lower()
    
    if content_type not in allowed_types and ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Allowed: wav, mp3, ogg, flac"
        )
    
    try:
        # Read audio data
        audio_data = await audio_file.read()
        
        if len(audio_data) == 0:
            raise HTTPException(status_code=400, detail="Empty audio file")
        
        # If no prompt_text provided, use ASR
        final_prompt_text = prompt_text
        if not final_prompt_text:
            # Save to temp file for ASR
            temp_file = tempfile.NamedTemporaryFile(suffix=ext or '.wav', delete=False)
            try:
                temp_file.write(audio_data)
                temp_file.close()
                
                tts_service = get_tts_service()
                final_prompt_text = await tts_service.recognize_prompt_text(temp_file.name)
            finally:
                if os.path.exists(temp_file.name):
                    os.unlink(temp_file.name)
        
        if not final_prompt_text:
            final_prompt_text = ""
        
        # Determine format from extension
        audio_format = ext.lstrip('.') if ext else 'wav'
        if audio_format not in ['wav', 'mp3', 'ogg', 'flac']:
            audio_format = 'wav'
        
        # Parse suitable_for from comma-separated string
        suitable_for_list = []
        if suitable_for:
            suitable_for_list = [s.strip() for s in suitable_for.split(",") if s.strip()]
        
        # Create voice
        voice_service = get_voice_service()
        metadata = voice_service.create_voice(
            audio_data=audio_data,
            voice_name=voice_name,
            prompt_text=final_prompt_text,
            audio_format=audio_format,
            description=description or "",
            suitable_for=suitable_for_list,
            for_podcast=for_podcast,
        )
        
        return VoiceResponse(
            voice_uuid=metadata["voice_uuid"],
            voice_name=metadata["voice_name"],
            prompt_text=metadata["prompt_text"],
            created_at=datetime.fromisoformat(metadata["created_at"]),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create voice: {str(e)}"
        )


@router.get(
    "",
    response_model=VoiceListResponse,
    summary="获取音色列表",
    description="获取所有已上传的音色列表。"
)
async def list_voices():
    """List all voice profiles."""
    voice_service = get_voice_service()
    voices = voice_service.list_voices()
    
    return VoiceListResponse(
        voices=[
            VoiceResponse(
                voice_uuid=v["voice_uuid"],
                voice_name=v["voice_name"],
                prompt_text=v["prompt_text"],
                created_at=datetime.fromisoformat(v["created_at"]),
            )
            for v in voices
        ],
        total=len(voices),
    )


@router.get(
    "/{voice_uuid}",
    response_model=VoiceResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Voice not found"},
    },
    summary="获取音色详情",
    description="根据UUID获取单个音色的详细信息。"
)
async def get_voice(voice_uuid: str):
    """Get a voice profile by UUID."""
    voice_service = get_voice_service()
    voice = voice_service.get_voice(voice_uuid)
    
    if not voice:
        raise HTTPException(
            status_code=404,
            detail=f"Voice not found: {voice_uuid}"
        )
    
    return VoiceResponse(
        voice_uuid=voice["voice_uuid"],
        voice_name=voice["voice_name"],
        prompt_text=voice["prompt_text"],
        created_at=datetime.fromisoformat(voice["created_at"]),
    )


@router.delete(
    "/{voice_uuid}",
    response_model=VoiceDeleteResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Voice not found"},
    },
    summary="删除音色",
    description="根据UUID删除音色配置文件。"
)
async def delete_voice(voice_uuid: str):
    """Delete a voice profile."""
    voice_service = get_voice_service()
    
    if not voice_service.voice_exists(voice_uuid):
        raise HTTPException(
            status_code=404,
            detail=f"Voice not found: {voice_uuid}"
        )
    
    success = voice_service.delete_voice(voice_uuid)
    
    return VoiceDeleteResponse(
        success=success,
        message="Voice deleted successfully" if success else "Failed to delete voice"
    )
