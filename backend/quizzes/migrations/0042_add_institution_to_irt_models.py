# Generated migration: add institution_id to IRT models for institution-level isolation
# Handles ItemParameter PK change: OneToOneField(pk=True) → ForeignKey + auto id
# 2026-06-13: converted PostgreSQL-specific RunSQL to backend-conditional RunPython for SQLite compat

from django.db import migrations, models
import django.db.models.deletion


def _add_itemparameter_id_pk(apps, schema_editor):
    """Add auto-increment id PK to ItemParameter. PG uses DDL; SQLite recreates table (safe: 0 rows)."""
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter ADD COLUMN id SERIAL NOT NULL"
        )
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter DROP CONSTRAINT quizzes_itemparameter_pkey"
        )
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter ADD PRIMARY KEY (id)"
        )
    elif vendor == 'sqlite':
        schema_editor.execute("""
            CREATE TABLE quizzes_itemparameter_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id BIGINT NOT NULL REFERENCES quizzes_question(id) DEFERRABLE INITIALLY DEFERRED,
                discrimination REAL NOT NULL DEFAULT 1.0,
                difficulty REAL NOT NULL DEFAULT 0.0,
                guessing REAL NOT NULL DEFAULT 0.25,
                responses_count INTEGER NOT NULL DEFAULT 0,
                last_estimated_at DATETIME NULL
            )
        """)
        schema_editor.execute(
            "INSERT INTO quizzes_itemparameter_new "
            "(question_id, discrimination, difficulty, guessing, responses_count, last_estimated_at) "
            "SELECT question_id, discrimination, difficulty, guessing, responses_count, last_estimated_at "
            "FROM quizzes_itemparameter"
        )
        schema_editor.execute("DROP TABLE quizzes_itemparameter")
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter_new RENAME TO quizzes_itemparameter"
        )
    else:
        raise RuntimeError(f"Unsupported DB vendor for PK migration: {vendor}")


def _reverse_itemparameter_id_pk(apps, schema_editor):
    """Reverse: drop id PK, restore question_id as PK."""
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter DROP CONSTRAINT quizzes_itemparameter_pkey"
        )
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter DROP COLUMN id"
        )
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter ADD PRIMARY KEY (question_id)"
        )
    elif vendor == 'sqlite':
        schema_editor.execute("""
            CREATE TABLE quizzes_itemparameter_old (
                question_id BIGINT NOT NULL PRIMARY KEY REFERENCES quizzes_question(id) DEFERRABLE INITIALLY DEFERRED,
                discrimination REAL NOT NULL DEFAULT 1.0,
                difficulty REAL NOT NULL DEFAULT 0.0,
                guessing REAL NOT NULL DEFAULT 0.25,
                responses_count INTEGER NOT NULL DEFAULT 0,
                last_estimated_at DATETIME NULL
            )
        """)
        schema_editor.execute(
            "INSERT INTO quizzes_itemparameter_old "
            "(question_id, discrimination, difficulty, guessing, responses_count, last_estimated_at) "
            "SELECT question_id, discrimination, difficulty, guessing, responses_count, last_estimated_at "
            "FROM quizzes_itemparameter"
        )
        schema_editor.execute("DROP TABLE quizzes_itemparameter")
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter_old RENAME TO quizzes_itemparameter"
        )
    else:
        raise RuntimeError(f"Unsupported DB vendor for PK reverse migration: {vendor}")


def _set_institution_not_null(apps, schema_editor):
    """Make institution columns NOT NULL. PG only; SQLite skips (ORM enforces)."""
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter ALTER COLUMN institution_id SET NOT NULL"
        )
        schema_editor.execute(
            "ALTER TABLE quizzes_userability ALTER COLUMN institution_id SET NOT NULL"
        )
    # SQLite: skip — table is empty, Django ORM enforces non-null at Python level


def _reverse_institution_not_null(apps, schema_editor):
    """Reverse: make institution columns nullable again."""
    vendor = schema_editor.connection.vendor
    if vendor == 'postgresql':
        schema_editor.execute(
            "ALTER TABLE quizzes_itemparameter ALTER COLUMN institution_id DROP NOT NULL"
        )
        schema_editor.execute(
            "ALTER TABLE quizzes_userability ALTER COLUMN institution_id DROP NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0050_add_institution_notification_config'),
        ('quizzes', '0040_add_knowledge_edge'),
    ]

    operations = [
        # 1. ItemParameter: add auto-increment id column, drop old PK (OneToOneField → AutoField)
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    code=_add_itemparameter_id_pk,
                    reverse_code=_reverse_itemparameter_id_pk,
                ),
            ],
            state_operations=[
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
        #    PG: ALTER COLUMN SET NOT NULL.  SQLite: skip (ORM enforces non-null at app level).
        #    state_operations keeps Django's ORM state in sync with the model.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    code=_set_institution_not_null,
                    reverse_code=_reverse_institution_not_null,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name='itemparameter',
                    name='institution',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='users.institution',
                        help_text='所属机构（机构级隔离）',
                    ),
                ),
                migrations.AlterField(
                    model_name='userability',
                    name='institution',
                    field=models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to='users.institution',
                        help_text='所属机构（机构级隔离）',
                    ),
                ),
            ],
        ),
    ]
