from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('users', '0070_personal_learning_access')]
    operations = [migrations.AddField(
        model_name='learninggrant', name='request_id',
        field=models.UUIDField(null=True, blank=True, unique=True),
    )]
