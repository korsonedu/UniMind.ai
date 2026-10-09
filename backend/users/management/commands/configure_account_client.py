from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.core.management.base import BaseCommand, CommandError
from oauth2_provider.models import Application


class Command(BaseCommand):
    help = '根据服务端环境幂等创建官网授权客户端，不输出或轮换密钥。'

    def handle(self, *args, **options):
        if not settings.ACCOUNT_ENABLED:
            raise CommandError('请先配置并启用账号服务。')
        callbacks = ' '.join(origin + '/account-api/callback/' for origin in settings.ACCOUNT_WEBSITE_ORIGINS)
        values = dict(
            name='科晟官网', client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            redirect_uris=callbacks, algorithm=Application.RS256_ALGORITHM,
            skip_authorization=True,
        )
        app = Application.objects.filter(client_id=settings.ACCOUNT_WEBSITE_CLIENT_ID).first()
        if app:
            if not all(getattr(app, key) == value for key, value in values.items()) or not check_password(settings.ACCOUNT_WEBSITE_CLIENT_SECRET, app.client_secret):
                raise CommandError('已有客户端配置不一致，请核实后人工调整；未修改已有配置。')
        else:
            app = Application(client_id=settings.ACCOUNT_WEBSITE_CLIENT_ID, client_secret=settings.ACCOUNT_WEBSITE_CLIENT_SECRET, **values)
            app.full_clean()
            app.save()
        self.stdout.write('官网授权客户端已就绪，未输出密钥。')
