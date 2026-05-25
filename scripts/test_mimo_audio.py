#!/usr/bin/env python3
"""测试 MiMo V2.5 的音频理解能力。

用法：
  1. 准备一个短音频文件（1-2 分钟的 mp3/wav）
  2. 在服务器上运行：
     python scripts/test_mimo_audio.py /path/to/audio.mp3

测试内容：
  - MiMo 是否支持 base64 音频输入
  - 转录质量如何
  - 响应延迟
"""
import sys
import os
import base64
import json
import time
import subprocess
import tempfile
import requests


def extract_audio(video_path: str) -> str:
    """从视频提取音频（16kHz 单声道 wav，30 秒）"""
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-t", "30",
         "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", tmp],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return tmp


def test_mimo_audio(audio_path: str):
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1/chat/completions")

    if not api_key:
        print("错误：LLM_API_KEY 环境变量未设置")
        sys.exit(1)

    # 读取音频文件
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()

    file_size_mb = len(audio_b64) * 3 / 4 / 1024 / 1024
    print(f"音频文件大小: {file_size_mb:.1f} MB")
    print(f"API 端点: {base_url}")

    # 测试 1: OpenAI 格式 (audio_url)
    print("\n--- 测试 1: audio_url 格式 ---")
    payload = {
        "model": os.getenv("LLM_MODEL", "mimo-v2.5"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请将这段音频完整转录为文字，保留时间戳。"},
                    {
                        "type": "audio_url",
                        "audio_url": {"url": f"data:audio/wav;base64,{audio_b64}"},
                    },
                ],
            }
        ],
        "max_completion_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.time()
    try:
        resp = requests.post(base_url, json=payload, headers=headers, timeout=120)
        elapsed = time.time() - t0
        print(f"状态码: {resp.status_code}")
        print(f"耗时: {elapsed:.1f}s")

        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"转录结果（前 500 字）:\n{content[:500]}")
            print(f"\n总字数: {len(content)}")
        else:
            print(f"响应: {resp.text[:500]}")
    except Exception as e:
        print(f"请求失败: {e}")

    # 测试 2: input_audio 格式 (部分 API 支持)
    print("\n--- 测试 2: input_audio 格式 ---")
    payload2 = {
        "model": os.getenv("LLM_MODEL", "mimo-v2.5"),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请将这段音频完整转录为文字。"},
                    {
                        "type": "input_audio",
                        "input_audio": {
                            "data": audio_b64,
                            "format": "wav",
                        },
                    },
                ],
            }
        ],
        "max_completion_tokens": 4096,
    }

    t0 = time.time()
    try:
        resp2 = requests.post(base_url, json=payload2, headers=headers, timeout=120)
        elapsed2 = time.time() - t0
        print(f"状态码: {resp2.status_code}")
        print(f"耗时: {elapsed2:.1f}s")

        if resp2.status_code == 200:
            data2 = resp2.json()
            content2 = data2.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"转录结果（前 500 字）:\n{content2[:500]}")
        else:
            print(f"响应: {resp2.text[:500]}")
    except Exception as e:
        print(f"请求失败: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python test_mimo_audio.py <音频或视频文件路径>")
        print("  如果是视频文件，会自动提取前 30 秒音频")
        sys.exit(1)

    path = sys.argv[1]
    # 如果是视频文件，先提取音频
    video_exts = {".mp4", ".mkv", ".avi", ".mov", ".flv", ".webm"}
    if any(path.lower().endswith(ext) for ext in video_exts):
        print(f"检测到视频文件，提取前 30 秒音频...")
        path = extract_audio(path)
        print(f"音频已提取: {path}")

    test_mimo_audio(path)
