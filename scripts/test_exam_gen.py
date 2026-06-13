#!/usr/bin/env python3
"""验证命题官：thinking=disabled + tool_choice=required"""
import os, sys, json, time, requests

env_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

API_KEY = os.environ.get('LLM_API_KEY', '')
if not API_KEY:
    print("❌ LLM_API_KEY not found"); sys.exit(1)

BASE_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-pro"

TOOL = {"type": "function", "function": {"name": "search_knowledge", "description": "搜索知识点",
    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}

def call(msgs, label):
    body = {"model": MODEL, "messages": msgs,
            "thinking": {"type": "disabled"}, "max_completion_tokens": 2500,
            "tools": [TOOL], "tool_choice": "required"}
    print(f"\n📤 {label}: thinking=disabled tc=required")
    t0 = time.monotonic()
    r = requests.post(BASE_URL, headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}, json=body, timeout=60)
    ms = int((time.monotonic()-t0)*1000)
    if r.status_code != 200:
        print(f"❌ {r.status_code}: {r.text[:300]}"); return False
    d = r.json()
    tcs = d['choices'][0]['message'].get('tool_calls') or []
    ct = d['choices'][0]['message'].get('content','')
    print(f"📥 {ms}ms finish={d['choices'][0].get('finish_reason','?')} tcs={len(tcs)} content={len(ct)}c")
    if tcs: print(f"   🔧 {tcs[0]['function']['name']}")
    else: print(f"   💬 {ct[:200]}")
    return True

print("命题官: thinking=disabled + required")
ok = call([
    {"role": "system", "content": "出题前先搜索知识点。"},
    {"role": "user", "content": "出一道极限计算的题。"},
], "命题官")
print(f"\n{'✅ 正常' if ok else '❌ 失败'}")
