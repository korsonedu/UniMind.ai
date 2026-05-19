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


def get_bot_prompt_path(bot) -> Path:
    return get_bots_prompt_dir() / f'bot_{bot.id}_prompt.txt'


def get_bot_prompt_template_name(bot) -> str:
    return f'bots/bot_{bot.id}_prompt.txt'


def read_bot_prompt_file(bot) -> Optional[str]:
    path = get_bot_prompt_path(bot)
    if not path.exists():
        return None
    try:
        return path.read_text(encoding='utf-8')
    except Exception:
        logger.exception('读取机器人 Prompt 文件失败: %s', path)
        return None


def write_bot_prompt_file(bot, content: str) -> Path:
    path = get_bot_prompt_path(bot)
    path.write_text(str(content or ''), encoding='utf-8')
    return path


def sync_bot_prompt(bot):
    """文件优先覆盖 DB，文件不存在则从 DB 创建文件。"""
    file_content = read_bot_prompt_file(bot)
    if file_content is not None:
        if bot.system_prompt != file_content:
            bot.system_prompt = file_content
            bot.save(update_fields=['system_prompt'])
        return

    write_bot_prompt_file(bot, bot.system_prompt or '')


def delete_bot_prompt_file(bot):
    path = get_bot_prompt_path(bot)
    if not path.exists():
        return
    try:
        path.unlink()
    except Exception:
        logger.exception('删除机器人 Prompt 文件失败: %s', path)
