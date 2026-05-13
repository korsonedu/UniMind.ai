from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("faq_system", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="answer",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, null=True),
        ),
        migrations.RunSQL(
            sql="UPDATE faq_system_answer SET updated_at = created_at WHERE updated_at IS NULL;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name="answer",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
    ]
