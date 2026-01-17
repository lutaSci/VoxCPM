#!/usr/bin/env python
"""
VoxCPM API Client Examples

This script demonstrates how to use the VoxCPM API from another service.
"""
import os
import sys
import json
import base64
import requests
from pathlib import Path

# API base URL
API_BASE_URL = os.environ.get("VOXCPM_API_URL", "http://localhost:8000")


def upload_voice(audio_path: str, voice_name: str, prompt_text: str = None) -> dict:
    """
    Upload a voice profile.
    
    Args:
        audio_path: Path to reference audio file
        voice_name: Name for the voice
        prompt_text: Text in the audio (optional, auto ASR if not provided)
    
    Returns:
        Voice metadata dict with voice_uuid
    """
    url = f"{API_BASE_URL}/voices"
    
    with open(audio_path, "rb") as f:
        files = {"audio_file": (Path(audio_path).name, f, "audio/wav")}
        data = {"voice_name": voice_name}
        if prompt_text:
            data["prompt_text"] = prompt_text
        
        response = requests.post(url, files=files, data=data)
    
    response.raise_for_status()
    return response.json()


def list_voices() -> list:
    """List all uploaded voices."""
    url = f"{API_BASE_URL}/voices"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()["voices"]


def delete_voice(voice_uuid: str) -> bool:
    """Delete a voice profile."""
    url = f"{API_BASE_URL}/voices/{voice_uuid}"
    response = requests.delete(url)
    response.raise_for_status()
    return response.json()["success"]


def generate_tts(
    text: str,
    voice_uuid: str = None,
    output_path: str = "output.wav",
    output_format: str = "wav",
    cfg_value: float = 2.0,
    inference_timesteps: int = 10,
    normalize: bool = False,
    denoise: bool = False,
    save_on_server: bool = False,
) -> dict:
    """
    Generate TTS audio.
    
    Args:
        text: Text to synthesize
        voice_uuid: UUID of uploaded voice (optional)
        output_path: Path to save audio file
        output_format: "wav", "mp3", or "base64"
        cfg_value: CFG guidance value
        inference_timesteps: Number of inference steps
        normalize: Text normalization
        denoise: Denoise prompt audio
        save_on_server: Save result on server for download
    
    Returns:
        Response metadata (or audio file saved to output_path)
    """
    url = f"{API_BASE_URL}/tts/generate"
    
    payload = {
        "text": text,
        "output_format": output_format,
        "cfg_value": cfg_value,
        "inference_timesteps": inference_timesteps,
        "normalize": normalize,
        "denoise": denoise,
        "save_result": save_on_server,
    }
    
    if voice_uuid:
        payload["voice_uuid"] = voice_uuid
    
    response = requests.post(url, json=payload)
    response.raise_for_status()
    
    if output_format == "base64":
        result = response.json()
        # Decode and save audio
        audio_data = base64.b64decode(result["audio_base64"])
        with open(output_path, "wb") as f:
            f.write(audio_data)
        print(f"Audio saved to: {output_path}")
        print(f"Duration: {result['duration_seconds']:.2f}s")
        print(f"Segments: {result['segments']}")
        if result.get("download_url"):
            print(f"Download URL: {API_BASE_URL}{result['download_url']}")
        return result
    else:
        # Direct audio response
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"Audio saved to: {output_path}")
        print(f"Sample rate: {response.headers.get('X-Sample-Rate')}")
        print(f"Duration: {response.headers.get('X-Duration-Seconds')}s")
        return {
            "sample_rate": response.headers.get("X-Sample-Rate"),
            "duration_seconds": response.headers.get("X-Duration-Seconds"),
            "segments": response.headers.get("X-Segments"),
        }


def generate_tts_with_temp_voice(
    text: str,
    audio_path: str,
    prompt_text: str = None,
    output_path: str = "output.wav",
) -> dict:
    """
    Generate TTS with a temporary voice (not saved on server).
    
    Args:
        text: Text to synthesize
        audio_path: Path to reference audio
        prompt_text: Text in reference audio (optional, auto ASR)
        output_path: Path to save output
    
    Returns:
        Response metadata
    """
    url = f"{API_BASE_URL}/tts/generate"
    
    # Read and encode audio
    with open(audio_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")
    
    payload = {
        "text": text,
        "temp_audio_base64": audio_base64,
        "output_format": "base64",
    }
    if prompt_text:
        payload["temp_prompt_text"] = prompt_text
    
    response = requests.post(url, json=payload)
    response.raise_for_status()
    
    result = response.json()
    audio_data = base64.b64decode(result["audio_base64"])
    with open(output_path, "wb") as f:
        f.write(audio_data)
    
    print(f"Audio saved to: {output_path}")
    return result


def generate_tts_streaming(
    text: str,
    voice_uuid: str = None,
    output_path: str = "output.wav",
) -> None:
    """
    Generate TTS with streaming (SSE).
    
    Args:
        text: Text to synthesize
        voice_uuid: UUID of uploaded voice (optional)
        output_path: Path to save concatenated audio
    """
    import sseclient  # pip install sseclient-py
    
    url = f"{API_BASE_URL}/tts/generate/stream"
    
    payload = {
        "text": text,
    }
    if voice_uuid:
        payload["voice_uuid"] = voice_uuid
    
    # Make streaming request
    response = requests.post(url, json=payload, stream=True)
    response.raise_for_status()
    
    client = sseclient.SSEClient(response)
    
    audio_chunks = []
    
    for event in client.events():
        data = json.loads(event.data)
        event_type = data.get("event", event.event)
        
        if event_type == "progress":
            print(f"Processing segment {data['segment']}/{data['total_segments']}...")
        
        elif event_type == "audio_chunk":
            print(f"Received chunk {data['segment']}, duration: {data['duration']:.2f}s")
            audio_chunks.append(base64.b64decode(data["audio_base64"]))
        
        elif event_type == "done":
            print(f"Done! Total duration: {data['total_duration_seconds']:.2f}s")
        
        elif event_type == "error":
            print(f"Error: {data['message']}")
            return
    
    # Save concatenated audio
    # Note: This is a simplified version - proper concatenation would need
    # to parse WAV headers. For production, request base64 and concatenate
    # the numpy arrays before encoding.
    if audio_chunks:
        # For simplicity, just save the first chunk
        # In production, you'd properly concatenate WAV files
        with open(output_path, "wb") as f:
            f.write(audio_chunks[0])  # Simplified
        print(f"Audio saved to: {output_path}")


# ============== Example Usage ==============

def main():
    """Run example client operations."""
    print("=" * 60)
    print("VoxCPM API Client Examples")
    print(f"API URL: {API_BASE_URL}")
    print("=" * 60)
    
    # Check API is running
    try:
        response = requests.get(f"{API_BASE_URL}/")
        print(f"API Status: {response.json()['status']}")
    except requests.exceptions.ConnectionError:
        print("Error: Cannot connect to API. Make sure the server is running.")
        print(f"Start with: python run_api.py")
        sys.exit(1)
    
    print("\n--- Example 1: Simple TTS (no voice cloning) ---")
    result = generate_tts(
        text="你好，这是一个语音合成测试。VoxCPM是一个先进的端到端TTS模型。",
        output_path="output_simple.wav",
        output_format="base64",
    )
    print(f"Generated {result['duration_seconds']:.2f}s of audio\n")
    
    # Check if example audio exists
    example_audio = "examples/example.wav"
    if os.path.exists(example_audio):
        print("\n--- Example 2: Upload Voice Profile ---")
        voice = upload_voice(
            audio_path=example_audio,
            voice_name="Example Voice",
            prompt_text=None,  # Auto ASR
        )
        print(f"Uploaded voice: {voice['voice_name']}")
        print(f"Voice UUID: {voice['voice_uuid']}")
        print(f"Detected text: {voice['prompt_text'][:50]}...")
        
        print("\n--- Example 3: TTS with Voice Cloning ---")
        result = generate_tts(
            text="这段语音使用了上传的参考音频进行声音克隆。",
            voice_uuid=voice["voice_uuid"],
            output_path="output_cloned.wav",
            output_format="base64",
        )
        print(f"Generated {result['duration_seconds']:.2f}s of cloned audio\n")
        
        print("\n--- Example 4: TTS with Temporary Voice ---")
        result = generate_tts_with_temp_voice(
            text="这段语音使用临时音色，不会保存在服务器上。",
            audio_path=example_audio,
            output_path="output_temp_voice.wav",
        )
        print(f"Generated {result['duration_seconds']:.2f}s of audio\n")
        
        print("\n--- Example 5: List Voices ---")
        voices = list_voices()
        print(f"Total voices: {len(voices)}")
        for v in voices:
            print(f"  - {v['voice_name']} ({v['voice_uuid'][:8]}...)")
    
    print("\n" + "=" * 60)
    print("Examples complete!")
    print("Check the generated .wav files in the current directory.")
    print("=" * 60)


if __name__ == "__main__":
    main()
