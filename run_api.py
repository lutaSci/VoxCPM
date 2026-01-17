#!/usr/bin/env python
"""
VoxCPM API Server Launcher

Usage:
    python run_api.py                    # Run with default settings
    python run_api.py --port 8080        # Custom port
    python run_api.py --debug            # Debug mode with auto-reload
    
Environment Variables:
    VOXCPM_HOST         Host to bind (default: 0.0.0.0)
    VOXCPM_PORT         Port to bind (default: 8000)
    VOXCPM_DEBUG        Enable debug mode (default: false)
    VOXCPM_MODEL_PATH   Path to local model directory
    VOXCPM_HF_MODEL_ID  HuggingFace model ID (default: openbmb/VoxCPM1.5)

Install dependencies:
    pip install -e ".[api]"
"""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="VoxCPM API Server")
    parser.add_argument("--host", type=str, default=None, help="Host to bind")
    parser.add_argument("--port", type=int, default=None, help="Port to bind")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--model-path", type=str, default=None, help="Path to local model")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    
    args = parser.parse_args()
    
    # Set environment variables from args
    if args.host:
        os.environ["VOXCPM_HOST"] = args.host
    if args.port:
        os.environ["VOXCPM_PORT"] = str(args.port)
    if args.debug:
        os.environ["VOXCPM_DEBUG"] = "true"
    if args.model_path:
        os.environ["VOXCPM_MODEL_PATH"] = args.model_path
    if args.workers:
        os.environ["VOXCPM_WORKER_COUNT"] = str(args.workers)
    
    # Import after setting env vars
    import uvicorn
    from api.config import settings
    
    print("=" * 60)
    print("VoxCPM API Server")
    print("=" * 60)
    print(f"Host:       {settings.host}")
    print(f"Port:       {settings.port}")
    print(f"Debug:      {settings.debug}")
    print(f"Model:      {settings.model_path or settings.hf_model_id}")
    print(f"Voices:     {settings.voices_dir}")
    print(f"Generated:  {settings.generated_audio_dir}")
    print("=" * 60)
    print(f"API Docs:   http://{settings.host}:{settings.port}/docs")
    print(f"ReDoc:      http://{settings.host}:{settings.port}/redoc")
    print("=" * 60)
    
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
        workers=1,  # Must be 1 for GPU model (can't share across workers)
    )


if __name__ == "__main__":
    main()
