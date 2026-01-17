# VoxCPM API 服务

基于 FastAPI 的 VoxCPM TTS API 服务，支持高并发请求和 Docker 部署。

## 🚀 快速开始

### 本地运行

```bash
# 1. 安装 uv (如果还没有安装)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 安装依赖 (包含 API 可选依赖)
uv pip install -e ".[api]"

# 3. 启动服务
uv run python run_api.py

# 或指定端口
uv run python run_api.py --port 8080

# 调试模式（自动重载）
uv run python run_api.py --debug
```

服务启动后访问：
- API 文档: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down
```

## 📚 API 接口

### 音色管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/voices` | 上传音色（参考音频） |
| GET | `/voices` | 获取音色列表 |
| GET | `/voices/{uuid}` | 获取音色详情 |
| DELETE | `/voices/{uuid}` | 删除音色 |

### TTS 生成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tts/generate` | 同步生成语音 |
| POST | `/tts/generate/stream` | 流式生成语音 (SSE) |

### 下载

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/downloads/{id}` | 下载生成的音频 |
| GET | `/downloads/{id}/info` | 获取音频信息 |

## 📝 使用示例

### Python 客户端

```python
import requests
import base64

API_URL = "http://localhost:8000"

# 1. 上传音色
with open("reference.wav", "rb") as f:
    response = requests.post(
        f"{API_URL}/voices",
        files={"audio_file": f},
        data={"voice_name": "我的音色"}
    )
voice = response.json()
print(f"Voice UUID: {voice['voice_uuid']}")

# 2. 生成语音（使用已上传音色）
response = requests.post(
    f"{API_URL}/tts/generate",
    json={
        "text": "你好，这是一个测试。",
        "voice_uuid": voice["voice_uuid"],
        "output_format": "base64"
    }
)
result = response.json()
audio = base64.b64decode(result["audio_base64"])
with open("output.wav", "wb") as f:
    f.write(audio)

# 3. 生成语音（无音色，模型自由发挥）
response = requests.post(
    f"{API_sURL}/tts/generate",
    json={
        "text": "这段语音不使用参考音色。",
        "output_format": "wav"
    }
)
with open("output2.wav", "wb") as f:
    f.write(response.content)

# 4. 使用临时音色（一次性，不保存）
with open("temp_voice.wav", "rb") as f:
    audio_base64 = base64.b64encode(f.read()).decode()

response = requests.post(
    f"{API_URL}/tts/generate",
    json={
        "text": "使用临时音色生成。",
        "temp_audio_base64": audio_base64,
        "output_format": "base64"
    }
)
```

### cURL 示例

```bash
# 上传音色
curl -X POST "http://localhost:8000/voices" \
  -F "audio_file=@reference.wav" \
  -F "voice_name=测试音色"

# 生成语音
curl -X POST "http://localhost:8000/tts/generate" \
  -H "Content-Type: application/json" \
  -d '{"text": "你好世界", "output_format": "wav"}' \
  --output output.wav

# 流式生成 (SSE)
curl -X POST "http://localhost:8000/tts/generate/stream" \
  -H "Content-Type: application/json" \
  -d '{"text": "这是一段较长的文本..."}'
```

## ⚙️ 配置

通过环境变量配置（可在 `.env` 文件中设置）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `VOXCPM_HOST` | 0.0.0.0 | 监听地址 |
| `VOXCPM_PORT` | 8000 | 监听端口 |
| `VOXCPM_DEBUG` | false | 调试模式 |
| `VOXCPM_MODEL_PATH` | - | 本地模型路径 |
| `VOXCPM_HF_MODEL_ID` | openbmb/VoxCPM1.5 | HuggingFace 模型 ID |
| `VOXCPM_ENABLE_DENOISER` | true | 启用降噪器 |
| `VOXCPM_VOICES_DIR` | ./voices | 音色存储目录 |
| `VOXCPM_GENERATED_AUDIO_DIR` | ./generated | 生成音频目录 |
| `VOXCPM_SPLIT_MAX_LENGTH` | 300 | 文本拆分最大长度 |
| `VOXCPM_GENERATED_AUDIO_EXPIRE_HOURS` | 24 | 生成音频过期时间(小时) |

## 📁 项目结构

```
api/
├── __init__.py
├── config.py           # 配置管理
├── main.py             # FastAPI 入口
├── models/
│   └── schemas.py      # Pydantic 数据模型
├── routers/
│   ├── voices.py       # 音色管理路由
│   ├── tts.py          # TTS 生成路由
│   └── downloads.py    # 下载路由
├── services/
│   ├── voice_service.py   # 音色管理服务
│   └── tts_service.py     # TTS 核心服务
└── utils/
    ├── text_splitter.py   # 智能分句
    └── cleanup.py         # 临时文件清理
```

## 🔧 特性

- ✅ **长文本自动拆分** - 超过300字符自动智能分句
- ✅ **流式响应** - SSE 实时返回音频块
- ✅ **音色管理** - 上传、列表、删除音色
- ✅ **临时音色** - 一次性使用，不保存服务器
- ✅ **自动 ASR** - 未提供参考文本时自动识别
- ✅ **文件清理** - 生成音频 24 小时后自动删除
- ✅ **Docker 支持** - 一键部署到 4090 GPU

## 🐳 Docker 配置说明

`docker-compose.yml` 中的关键配置：

```yaml
# GPU 支持
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]

# 数据持久化
volumes:
  - ./voices:/app/voices      # 音色文件
  - ./generated:/app/generated # 生成的音频
  - ./models:/app/models       # 模型文件(可选)
```

确保已安装 [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)。

## 📊 性能

- 预计 QPS: 2-5 (单 4090 GPU)
- RTF: ~0.15 (VoxCPM1.5 on 4090)
- 首次请求会加载模型，需要等待 1-2 分钟
