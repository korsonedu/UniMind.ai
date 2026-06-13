#!/usr/bin/env python3
"""
验证 DeepSeek V4 thinking=enabled 下的工具调用。

根据官方文档 api-docs.deepseek.com/guides/thinking_mode：
- thinking mode 支持工具调用
- 约束：做了 tool call 的 assistant 消息的 reasoning_content 必须回传
- 关键：不能用 tool_choice=required，用 auto 或省略
"""
import os, sys, json, time, requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
env_path = os.path.join(os.path.dirname(__file__), '..', 'backend', '.env')
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

API_KEY = os.environ.get('LLM_API_KEY', '')
if not API_KEY: print("❌ LLM_API_KEY"); sys.exit(1)

BASE_URL = "https://api.deepseek.com/v1/chat/completions"
MODEL = "deepseek-v4-pro"

TOOLS = [
    {"type": "function", "function": {"name": "get_stats", "description": "获取学生学习统计：做题量、正确率、连续天数", "parameters": {
        "type": "object", "properties": {"student": {"type": "string"}}, "required": ["student"]
    }}},
    {"type": "function", "function": {"name": "get_weak_points", "description": "获取薄弱知识点", "parameters": {
        "type": "object", "properties": {"student": {"type": "string"}}, "required": ["student"]
    }}},
]

def run_tool(name, args):
    s = args.get("student", "?")
    if name == "get_stats":
        return json.dumps({"student": s, "total": 238, "accuracy": 0.72, "streak": 14}, ensure_ascii=False)
    return json.dumps({"student": s, "weak_points": ["极限计算(65%)", "中值定理(58%)", "不定积分(52%)"]}, ensure_ascii=False)

def call(messages, tools, tool_choice, label=""):
    body = {"model": MODEL, "messages": messages, "thinking": {"type": "enabled"},
            "max_completion_tokens": 2500}
    if tools: body["tools"] = tools
    if tool_choice: body["tool_choice"] = tool_choice

    print(f"\n{'='*60}")
    print(f"📤 {label}: tc={tool_choice or 'auto(default)'} | {len(messages)} msgs")
    for i, m in enumerate(messages):
        rc = "✅" if m.get("reasoning_content") else "  "
        tc = "🔧" if m.get("tool_calls") else "  "
        c = str(m.get("content",""))[:60].replace("\n"," ")
        print(f"  [{i}] {m['role']:10s} rc={rc} tc={tc} | {c}")

    t0 = time.monotonic()
    r = requests.post(BASE_URL, headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}, json=body, timeout=120)
    ms = int((time.monotonic()-t0)*1000)
    if r.status_code != 200:
        print(f"❌ HTTP {r.status_code}: {r.text[:300]}")
        return None
    d = r.json()
    msg = d['choices'][0]['message']
    content = msg.get('content') or ''
    rc = msg.get('reasoning_content') or ''
    tcs = msg.get('tool_calls') or []
    usage = d.get('usage', {})
    print(f"📥 {ms}ms finish={d['choices'][0].get('finish_reason','?')} rc={len(rc)}c content={len(content)}c tcs={len(tcs)} | in={usage.get('prompt_tokens','?')} out={usage.get('completion_tokens','?')}")
    if tcs:
        for tc in tcs:
            a = tc['function'].get('arguments','')[:80]
            print(f"   🔧 {tc['function']['name']}({a}...)")
    else:
        print(f"   💬 {content[:250]}")
    return {"content": content, "reasoning_content": rc, "tool_calls": tcs}

def asst_msg(resp):
    m = {"role": "assistant", "content": resp.get("content") or ""}
    if resp.get("reasoning_content"): m["reasoning_content"] = resp["reasoning_content"]
    if resp.get("tool_calls"): m["tool_calls"] = resp["tool_calls"]
    return m

# ══════════════════════════════════════════════════════════
print("╔══════════════════════════════════════════════════════╗")
print("║  DeepSeek V4: thinking=enabled + tool_choice=auto  ║")
print("╚══════════════════════════════════════════════════════╝")

msgs = [
    {"role": "system", "content": "你是学习教练小宇。你必须先通过工具获取学生数据再回答，不要编造数字。没有数据时不要给出任何具体建议。"},
    {"role": "user", "content": "帮我分析张三的学习情况，给出具体建议。"},
]

# ── 测试1: thinking=enabled, 不传 tool_choice ──
print("\n── 测试1: thinking=enabled, 不传 tool_choice（默认 auto）──")
r1 = call(msgs, TOOLS, None, "轮1")
if not r1: sys.exit(1)

if not r1["tool_calls"]:
    print("⚠️ 模型没调工具，直接给了回复。")
    # 试试强行告诉它调工具
    msgs.append({"role": "assistant", "content": r1.get("content", "")})
    msgs.append({"role": "user", "content": "你没有查数据。请先调用 get_stats 和 get_weak_points 获取张三的真实数据，然后再分析。"})
    r1b = call(msgs, TOOLS, "auto", "轮1b-重试")
    if r1b and r1b["tool_calls"]:
        r1 = r1b
    else:
        print("⚠️ 依然不调工具，可能是 model 行为或其认为不需要")
else:
    print(f"✅ 轮1：模型主动调了 {len(r1['tool_calls'])} 个工具")

# 如果调了工具，继续第二轮
if r1 and r1["tool_calls"]:
    msgs.append(asst_msg(r1))
    for tc in r1["tool_calls"]:
        a = json.loads(tc["function"]["arguments"])
        msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": run_tool(tc["function"]["name"], a)})

    r2 = call(msgs, TOOLS, "auto", "轮2")
    if not r2: sys.exit(1)
    if r2["tool_calls"]:
        print(f"✅ 轮2：继续调 {len(r2['tool_calls'])} 个工具")
        msgs.append(asst_msg(r2))
        for tc in r2["tool_calls"]:
            a = json.loads(tc["function"]["arguments"])
            msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": run_tool(tc["function"]["name"], a)})
        r3 = call(msgs, TOOLS, "auto", "轮3-终")
        if r3 and not r3.get("tool_calls"):
            print(f"✅ 轮3：最终回复成功")
    else:
        print(f"✅ 轮2：模型直接给回复")

print(f"\n🏁 完成！thinking=enabled + tool_choice=auto 无 400 错误")
