"""
VoxCPM API - FastAPI application entry point.

TTS API service for VoxCPM model with support for:
- Voice profile management (upload, list, delete)
- Text-to-speech generation (sync and streaming)
- Automatic text splitting for long inputs
- Temporary and persistent voice support
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import voices, tts, downloads, v2
from .utils.cleanup import cleanup_task, get_audio_manager
from .services.tts_service import get_tts_service

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Background tasks
cleanup_task_handle = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global cleanup_task_handle
    
    logger.info("Starting VoxCPM API server...")
    logger.info(f"Model: {settings.hf_model_id}")
    logger.info(f"Voices directory: {settings.voices_dir}")
    logger.info(f"Generated audio directory: {settings.generated_audio_dir}")
    
    # Start cleanup background task
    cleanup_task_handle = asyncio.create_task(cleanup_task())
    logger.info("Started cleanup background task")
    
    # Pre-load model if not lazy loading
    # Uncomment the following to load model on startup:
    # logger.info("Pre-loading TTS model...")
    # tts_service = get_tts_service()
    # await tts_service._ensure_model_loaded()
    # logger.info("TTS model loaded")
    
    yield
    
    # Shutdown
    logger.info("Shutting down VoxCPM API server...")
    
    if cleanup_task_handle:
        cleanup_task_handle.cancel()
        try:
            await cleanup_task_handle
        except asyncio.CancelledError:
            pass
    
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="VoxCPM API",
    description="""
## VoxCPM Text-to-Speech API

VoxCPM 是一个先进的端到端 TTS 模型，支持：
- 🎙️ **零样本声音克隆** - 使用参考音频生成相似音色的语音
- 📝 **长文本自动拆分** - 自动将长文本拆分成适合生成的片段
- ⚡ **高效推理** - RTF ~0.15 (4090 GPU)

### 快速开始

1. **上传音色** - POST `/voices` 上传参考音频
2. **生成语音** - POST `/tts/generate` 使用音色生成语音
3. **流式生成** - POST `/tts/generate/stream` 获取实时音频流

### API 版本
- v1.0.0
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(voices.router)
app.include_router(tts.router)
app.include_router(downloads.router)
app.include_router(v2.router)


@app.get("/", tags=["root"])
async def root():
    """API root endpoint."""
    return {
        "service": "VoxCPM API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "model": settings.hf_model_id,
    }


def run_server():
    """Run the server using uvicorn."""
    import uvicorn
    
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    run_server()
