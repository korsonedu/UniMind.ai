import sys

from django.apps import AppConfig


class AiAssistantConfig(AppConfig):
    name = "ai_assistant"

    def ready(self):
        # 只在真正运行 server 时预加载，避免 migrate/shell/check 等命令每次触发 HF 网络请求
        argv_str = ' '.join(sys.argv)
        if not any(cmd in argv_str for cmd in ('runserver', 'celery', 'uvicorn', 'daphne')):
            return
        try:
            from ai_engine.tool_router import preload_embedding_model
            preload_embedding_model()
        except Exception:
            pass
