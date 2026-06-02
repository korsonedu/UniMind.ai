#!/usr/bin/env python3
"""
UniMind 发版时机检测脚本
每次 cron job 执行时运行，输出发版建议（无建议时静默）
"""
import subprocess
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent  # UniMindCode root
CHANGELOG = REPO / "CHANGELOG.md"

# ── 阈值配置 ──────────────────────────────────────────────
COMMITS_SINCE_TAG_THRESHOLD = 15   # 累计 N 个 commit 建议发版
DAYS_SINCE_TAG_THRESHOLD    = 7    # 距上次发版 N 天建议发版
SECURITY_FIX_THRESHOLD      = 1    # 有安全修复立即建议
FEAT_COUNT_FOR_MINOR        = 5    # 累计 N 个 feat 建议 bump MINOR


def git(cmd_args: list[str]) -> str:
    """Run git command with list args (no shell interpretation)."""
    r = subprocess.run(
        ["git"] + cmd_args, capture_output=True, text=True, cwd=REPO
    )
    return r.stdout.strip()


def get_latest_tag() -> tuple[str, str] | None:
    """返回 (tag_name, tag_date) 或 None"""
    tag = git(["describe", "--tags", "--abbrev=0"])
    if not tag:
        return None
    date = git(["log", "-1", "--format=%aI", tag])
    return tag, date


def get_commits_since(tag: str | None) -> list[dict]:
    """返回自 tag 以来的 commit 列表（无 tag 时取最近 50 条）"""
    if tag:
        range_spec = f"{tag}..HEAD"
    else:
        range_spec = "HEAD~50..HEAD"
    raw = git(["log", range_spec, "--format=%H|%s|%aI", "--no-merges"])
    if not raw:
        return []
    commits = []
    for line in raw.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0], "subject": parts[1], "date": parts[2]})
    return commits


def classify_commits(commits: list[dict]) -> dict:
    """按 type 分类 commit"""
    stats = {"feat": 0, "fix": 0, "fix_security": 0, "refactor": 0, "other": 0}
    for c in commits:
        subj = c["subject"]
        if subj.startswith("fix(security)"):
            stats["fix_security"] += 1
            stats["fix"] += 1
        elif subj.startswith("fix"):
            stats["fix"] += 1
        elif subj.startswith("feat"):
            stats["feat"] += 1
        elif subj.startswith("refactor"):
            stats["refactor"] += 1
        else:
            stats["other"] += 1
    return stats


def current_version_from_changelog() -> str:
    """从 CHANGELOG.md 提取当前版本号"""
    if not CHANGELOG.exists():
        return "unknown"
    text = CHANGELOG.read_text()
    m = re.search(r"\[v([\d.]+(?:-[\w.]+)?)\]", text)
    return m.group(1) if m else "unknown"


def suggest_bump(stats: dict, current: str) -> str:
    """建议 bump 类型"""
    if stats["feat"] >= FEAT_COUNT_FOR_MINOR:
        return "MINOR"
    if stats["fix"] > 0 or stats["refactor"] > 0:
        return "PATCH"
    return "PATCH"


def main():
    tag_info = get_latest_tag()
    tag_name = tag_info[0] if tag_info else None
    tag_date_str = tag_info[1] if tag_info else None

    commits = get_commits_since(tag_name)
    if not commits:
        return  # 无新 commit，静默

    stats = classify_commits(commits)
    commit_count = len(commits)
    current_ver = current_version_from_changelog()

    # ── 判断是否该发版 ──
    reasons = []

    # 无 tag = 从未正式发版，强制建议
    if not tag_info:
        reasons.append("🏷️  项目尚无版本 tag，建议立即创建首个正式版本")

    # 安全修复优先
    if stats["fix_security"] >= SECURITY_FIX_THRESHOLD:
        reasons.append(f"🔴 安全修复 ×{stats['fix_security']}，建议立即发版部署")

    # commit 数量阈值
    if commit_count >= COMMITS_SINCE_TAG_THRESHOLD:
        reasons.append(f"📦 已积累 {commit_count} 个 commit（阈值 {COMMITS_SINCE_TAG_THRESHOLD}）")

    # 时间阈值
    if tag_date_str:
        tag_date = datetime.fromisoformat(tag_date_str.replace("Z", "+00:00"))
        days = (datetime.now(tag_date.tzinfo) - tag_date).days
        if days >= DAYS_SINCE_TAG_THRESHOLD:
            reasons.append(f"📅 距上次发版已 {days} 天（阈值 {DAYS_SINCE_TAG_THRESHOLD} 天）")

    if not reasons:
        return  # 未达阈值，静默

    # ── 生成建议 ──
    bump = suggest_bump(stats, current_ver)
    ver_parts = current_ver.split("-")[0].split(".")
    if bump == "MINOR":
        next_ver = f"v{ver_parts[0]}.{int(ver_parts[1]) + 1}.0"
    else:
        next_ver = f"v{ver_parts[0]}.{ver_parts[1]}.{int(ver_parts[2]) + 1}"

    output = []
    output.append("=" * 50)
    output.append("📋 UniMind 发版建议")
    output.append("=" * 50)
    output.append(f"当前版本: v{current_ver}")
    output.append(f"自 {tag_name or '初始'} 以来: {commit_count} 个 commit")
    output.append(f"  feat: {stats['feat']}  fix: {stats['fix']}  refactor: {stats['refactor']}  other: {stats['other']}")
    output.append("")
    output.append("发版理由:")
    for r in reasons:
        output.append(f"  {r}")
    output.append("")
    output.append(f"建议版本: {next_ver}")
    output.append("")
    output.append("操作清单:")
    output.append("  1. 更新 CHANGELOG.md（合并 commit 为变更记录）")
    output.append("  2. git add + git commit -m 'docs: 更新 CHANGELOG 至 {}'".format(next_ver))
    output.append("  3. git tag {}".format(next_ver))
    output.append("  4. git push && git push --tags")
    output.append("  5. 服务器部署: cd /opt/unimind && git pull")
    output.append("=" * 50)

    print("\n".join(output))


if __name__ == "__main__":
    main()
