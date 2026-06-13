# Generated migration: add institution_id to IRT models for institution-level isolation
# Handles ItemParameter PK change: OneToOneField(pk=True) → ForeignKey + auto id

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0050_add_institution_notification_config'),
        ('quizzes', '0040_add_knowledge_edge'),
    ]

    operations = [
        # 1. ItemParameter: add auto-increment id column, drop old PK
        migrations.RunSQL(
            sql=[
                # Add id column as auto-increment
                "ALTER TABLE quizzes_itemparameter ADD COLUMN id SERIAL NOT NULL",
                # Drop the old PK constraint (question_id was PK)
                "ALTER TABLE quizzes_itemparameter DROP CONSTRAINT quizzes_itemparameter_pkey",
                # Set id as new PK
                "ALTER TABLE quizzes_itemparameter ADD PRIMARY KEY (id)",
            ],
            reverse_sql=[
                "ALTER TABLE quizzes_itemparameter DROP CONSTRAINT quizzes_itemparameter_pkey",
                "ALTER TABLE quizzes_itemparameter DROP COLUMN id",
                "ALTER TABLE quizzes_itemparameter ADD PRIMARY KEY (question_id)",
            ],
            state_operations=[
                # Django state: id is the new PK (auto field)
                migrations.AddField(
                    model_name='itemparameter',
                    name='id',
                    field=models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                    ),
                    preserve_default=False,
                ),
            ],
        ),

        # 2. ItemParameter: add institution FK (initially nullable for migration)
        migrations.AddField(
            model_name='itemparameter',
            name='institution',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='users.institution',
                help_text='所属机构（机构级隔离）',
            ),
        ),

        # 3. ItemParameter: alter question from OneToOne(pk) to regular FK
        migrations.AlterField(
            model_name='itemparameter',
            name='question',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to='quizzes.question',
                help_text='关联的题目',
            ),
        ),

        # 4. ItemParameter: add unique constraint (question, institution)
        migrations.AddConstraint(
            model_name='itemparameter',
            constraint=models.UniqueConstraint(
                fields=['question', 'institution'],
                name='unique_question_institution',
            ),
        ),

        # 5. UserAbility: add institution FK (initially nullable)
        migrations.AddField(
            model_name='userability',
            name='institution',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='users.institution',
                help_text='所属机构（机构级隔离）',
            ),
        ),

        # 6. UserAbility: update unique constraint to (user, kp, institution)
        migrations.AlterUniqueTogether(
            name='userability',
            unique_together={('user', 'knowledge_point', 'institution')},
        ),

        # 7. Make institution columns NOT NULL (table is empty, safe)
        migrations.RunSQL(
            sql=[
                "ALTER TABLE quizzes_itemparameter ALTER COLUMN institution_id SET NOT NULL",
                "ALTER TABLE quizzes_userability ALTER COLUMN institution_id SET NOT NULL",
            ],
            reverse_sql=[
                "ALTER TABLE quizzes_itemparameter ALTER COLUMN institution_id DROP NOT NULL",
                "ALTER TABLE quizzes_userability ALTER COLUMN institution_id DROP NOT NULL",
            ],
        ),
    ]
