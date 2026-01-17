"""
Downloads API routes for retrieving saved generated audio.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..models.schemas import GeneratedAudioInfo, ErrorResponse
from ..utils.cleanup import get_audio_manager

router = APIRouter(prefix="/downloads", tags=["downloads"])


@router.get(
    "/{audio_id}",
    responses={
        404: {"model": ErrorResponse, "description": "Audio not found or expired"},
    },
    summary="下载生成的音频",
    description="下载之前保存的生成音频文件。文件在24小时后过期。"
)
async def download_audio(audio_id: str):
    """Download a generated audio file."""
    audio_manager = get_audio_manager()
    
    audio_path = audio_manager.get_audio_path(audio_id)
    if not audio_path:
        raise HTTPException(
            status_code=404,
            detail="Audio not found or has expired"
        )
    
    info = audio_manager.get_audio_info(audio_id)
    
    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav" if info["format"] == "wav" else "audio/mpeg",
        filename=info["filename"],
        headers={
            "X-Sample-Rate": str(info["sample_rate"]),
            "X-Duration-Seconds": str(info["duration_seconds"]),
            "X-Expires-At": info["expires_at"],
        }
    )


@router.get(
    "/{audio_id}/info",
    response_model=GeneratedAudioInfo,
    responses={
        404: {"model": ErrorResponse, "description": "Audio not found or expired"},
    },
    summary="获取音频信息",
    description="获取生成音频的元数据信息。"
)
async def get_audio_info(audio_id: str):
    """Get information about a generated audio file."""
    audio_manager = get_audio_manager()
    
    info = audio_manager.get_audio_info(audio_id)
    if not info:
        raise HTTPException(
            status_code=404,
            detail="Audio not found or has expired"
        )
    
    from datetime import datetime
    
    return GeneratedAudioInfo(
        audio_id=info["audio_id"],
        filename=info["filename"],
        format=info["format"],
        sample_rate=info["sample_rate"],
        duration_seconds=info["duration_seconds"],
        created_at=datetime.fromisoformat(info["created_at"]),
        expires_at=datetime.fromisoformat(info["expires_at"]),
        download_url=f"/downloads/{audio_id}",
    )
