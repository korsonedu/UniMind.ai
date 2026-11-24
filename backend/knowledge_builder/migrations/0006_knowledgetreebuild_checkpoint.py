from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('knowledge_builder', '0005_blockresource_downvotes_blockresource_is_dismissed_and_more')]

    operations = [
        migrations.AddField('knowledgetreebuild', 'requires_ulr', models.BooleanField(default=False)),
        migrations.AddField('knowledgetreebuild', 'checkpoint', models.JSONField(default=dict, editable=False)),
    ]
