from django.apps import AppConfig


class ArticlesConfig(AppConfig):
    name = "articles"

    def ready(self):
        import articles.signals  # noqa: F401
