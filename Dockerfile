# VoxCPM API Dockerfile
# Optimized for NVIDIA RTX 4090 deployment

# Base image with CUDA support
FROM nvidia/cuda:12.4.0-cudnn-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set CUDA environment
ENV CUDA_HOME=/usr/local/cuda
ENV PATH=${CUDA_HOME}/bin:${PATH}
ENV LD_LIBRARY_PATH=${CUDA_HOME}/lib64:${LD_LIBRARY_PATH}

# UV environment
ENV UV_SYSTEM_PYTHON=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3.11-venv \
    git \
    wget \
    curl \
    ffmpeg \
    libsndfile1 \
    libsox-dev \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Create app directory
WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 voxcpm && \
    chown -R voxcpm:voxcpm /app

# Copy project files first for better caching
COPY --chown=voxcpm:voxcpm pyproject.toml ./

# Install Python dependencies with uv
RUN uv pip install --system -e ".[api]"

# Copy application code
COPY --chown=voxcpm:voxcpm . .

# Create directories for data persistence
RUN mkdir -p /app/voices /app/generated /app/models && \
    chown -R voxcpm:voxcpm /app/voices /app/generated /app/models

# Switch to non-root user
USER voxcpm

# Expose port
EXPOSE 8000

# Set default environment variables
ENV VOXCPM_HOST=0.0.0.0
ENV VOXCPM_PORT=8000
ENV VOXCPM_VOICES_DIR=/app/voices
ENV VOXCPM_GENERATED_AUDIO_DIR=/app/generated
ENV VOXCPM_HF_MODEL_ID=openbmb/VoxCPM1.5

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the API server
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
