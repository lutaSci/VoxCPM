"""
Pydantic schemas for API request/response models
"""
from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field


# ============== Voice Schemas ==============

class VoiceCreate(BaseModel):
    """Schema for voice upload (used with form data, actual file is separate)"""
    voice_name: str = Field(..., min_length=1, max_length=100, description="音色名称")
    prompt_text: Optional[str] = Field(None, description="参考音频对应的文本，不填则自动ASR识别")


class VoiceResponse(BaseModel):
    """Schema for voice response"""
    voice_uuid: str = Field(..., description="音色唯一标识")
    voice_name: str = Field(..., description="音色名称")
    prompt_text: str = Field(..., description="参考音频对应的文本")
    created_at: datetime = Field(..., description="创建时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class VoiceListResponse(BaseModel):
    """Schema for voice list response"""
    voices: List[VoiceResponse] = Field(default_factory=list, description="音色列表")
    total: int = Field(..., description="总数")


class VoiceDeleteResponse(BaseModel):
    """Schema for voice deletion response"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="消息")


# ============== TTS Schemas ==============

class TTSGenerateRequest(BaseModel):
    """Schema for TTS generation request"""
    text: str = Field(..., min_length=1, max_length=5000, description="要合成的文本")
    voice_uuid: Optional[str] = Field(None, description="已上传音色的UUID")
    temp_audio_base64: Optional[str] = Field(None, description="临时音色音频(Base64编码)")
    temp_prompt_text: Optional[str] = Field(None, description="临时音色对应的文本，不填则自动ASR识别")
    cfg_value: Optional[float] = Field(None, ge=1.0, le=5.0, description="CFG值，默认2.0")
    inference_timesteps: Optional[int] = Field(None, ge=4, le=50, description="推理步数，默认10")
    normalize: bool = Field(False, description="是否启用文本正则化")
    denoise: bool = Field(False, description="是否启用参考音频降噪")
    output_format: Literal["wav", "mp3", "base64"] = Field("wav", description="输出格式")
    save_result: bool = Field(False, description="是否保存结果到服务器(24小时过期)")


class TTSGenerateResponse(BaseModel):
    """Schema for TTS generation response (base64 format)"""
    audio_base64: str = Field(..., description="音频数据(Base64编码)")
    sample_rate: int = Field(..., description="采样率")
    duration_seconds: float = Field(..., description="音频时长(秒)")
    segments: int = Field(..., description="内部拆分的段数")
    format: str = Field("wav", description="音频格式")
    download_url: Optional[str] = Field(None, description="下载链接(仅当save_result=true时)")
    expires_at: Optional[datetime] = Field(None, description="过期时间(仅当save_result=true时)")


class TTSStreamEvent(BaseModel):
    """Schema for TTS streaming event"""
    event: Literal["progress", "audio_chunk", "done", "error"] = Field(..., description="事件类型")
    segment: Optional[int] = Field(None, description="当前段索引")
    total_segments: Optional[int] = Field(None, description="总段数")
    audio_base64: Optional[str] = Field(None, description="音频数据块(Base64编码)")
    duration: Optional[float] = Field(None, description="当前段时长(秒)")
    total_duration_seconds: Optional[float] = Field(None, description="总时长(秒)")
    status: Optional[str] = Field(None, description="状态")
    message: Optional[str] = Field(None, description="消息")
    download_url: Optional[str] = Field(None, description="下载链接")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


# ============== Generated Audio Schemas ==============

class GeneratedAudioInfo(BaseModel):
    """Schema for generated audio info"""
    audio_id: str = Field(..., description="音频ID")
    filename: str = Field(..., description="文件名")
    format: str = Field(..., description="格式")
    sample_rate: int = Field(..., description="采样率")
    duration_seconds: float = Field(..., description="时长(秒)")
    created_at: datetime = Field(..., description="创建时间")
    expires_at: datetime = Field(..., description="过期时间")
    download_url: str = Field(..., description="下载链接")


# ============== Error Schemas ==============

class ErrorResponse(BaseModel):
    """Schema for error response"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    detail: Optional[str] = Field(None, description="详细信息")
