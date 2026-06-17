from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = "users"

    def ready(self):
        from django.db.models.signals import post_migrate
        from users.services.achievements import seed_achievements, connect_achievement_signals
        connect_achievement_signals()
        post_migrate.connect(lambda **kwargs: seed_achievements(), sender=self)
