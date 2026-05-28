import logging
from pathlib import Path
from typing import Optional

from django.conf import settings


logger = logging.getLogger(__name__)


def _base_dir() -> Path:
    return Path(getattr(settings, 'BASE_DIR', Path(__file__).resolve().parent.parent))


def get_bots_prompt_dir() -> Path:
    path = _base_dir() / 'prompts' / 'ai_assistant' / 'bots'
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_bot_prompt_dir(bot) -> Path:
    """根据 bot 的 bot_type 获取 prompt 目录。"""
    from ai_assistant.bot_registry import get_bot_profile
    profile = get_bot_profile(bot.bot_type)
    return get_bots_prompt_dir() / profile.prompt_dir


def read_prompt_file(bot, filename: str) -> Optional[str]:
    """读取 bot prompt 目录下的指定文件。"""
    path = get_bot_prompt_dir(bot) / filename
    if not path.exists():
        return None
    try:
        return path.read_text(encoding='utf-8').strip()
    except Exception:
        logger.exception('读取 Prompt 文件失败: %s', path)
        return None


def write_prompt_file(bot, filename: str, content: str) -> Path:
    """写入 bot prompt 目录下的指定文件。"""
    dir_path = get_bot_prompt_dir(bot)
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / filename
    path.write_text(str(content or ''), encoding='utf-8')
    return path


def load_system_prompt(bot) -> str:
    """加载 bot 的完整 system prompt（文件优先，fallback 到 DB）。"""
    content = read_prompt_file(bot, 'system_prompt.txt')
    if content:
        return content
    return bot.system_prompt or '你是UniMind.ai的AI学术助教。'


def load_tool_guide(bot) -> str:
    """加载 bot 的 tool guide。"""
    content = read_prompt_file(bot, 'tool_guide.txt')
    if content:
        return f"\n\n{content}"
    return ''


def load_personality_template(bot) -> str:
    """加载 bot 的 personality 模板。"""
    content = read_prompt_file(bot, 'personality.txt')
    if content:
        return content
    return ''


# 向后兼容：保留旧接口
def get_bot_prompt_template_name(bot) -> str:
    """返回 bot prompt 文件的相对模板路径（供 serializer 使用）。"""
    from ai_assistant.bot_registry import get_bot_profile
    profile = get_bot_profile(bot.bot_type)
    return f'bots/{profile.prompt_dir}/system_prompt.txt'


def get_bot_prompt_path(bot) -> Path:
    return get_bot_prompt_dir(bot) / 'system_prompt.txt'


def read_bot_prompt_file(bot) -> Optional[str]:
    return read_prompt_file(bot, 'system_prompt.txt')


def write_bot_prompt_file(bot, content: str) -> Path:
    return write_prompt_file(bot, 'system_prompt.txt', content)


def sync_bot_prompt(bot):
    """文件优先覆盖 DB，文件不存在则从 DB 创建文件。"""
    file_content = read_prompt_file(bot, 'system_prompt.txt')
    if file_content is not None:
        if bot.system_prompt != file_content:
            bot.system_prompt = file_content
            bot.save(update_fields=['system_prompt'])
        return
    write_prompt_file(bot, 'system_prompt.txt', bot.system_prompt or '')


def delete_bot_prompt_file(bot):
    """删除 bot 的 prompt 目录。"""
    import shutil
    dir_path = get_bot_prompt_dir(bot)
    if dir_path.exists():
        try:
            shutil.rmtree(dir_path)
        except Exception:
            logger.exception('删除 Prompt 目录失败: %s', dir_path)
