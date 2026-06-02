from django.apps import AppConfig


class QuizzesConfig(AppConfig):
    name = "quizzes"

    def ready(self):
        import quizzes.signals  # noqa: F401
