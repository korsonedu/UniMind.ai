import io,json
from datetime import date
import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from users.models import User,Institution
from users.models_workspace import Workspace,WorkspaceLearner,WorkspaceMembership
from users.login_sessions import LoginSession
from courses.models import Course,VideoProgress,VideoTranscript
from notes.models import Note,Notebook
from ai_assistant.models import AIChatMessage,Bot

pytestmark=pytest.mark.django_db


def test_legacy_institution_migration_preserves_records_and_closes_personal_courses(settings):
    inst=Institution.objects.create(name='Running school',slug='running-school',plan='growth')
    settings.UNIMIND_CONTENT_INSTITUTION_ID=str(inst.pk)
    owner=User.objects.create_user(username='legacy-owner',institution=inst,is_member=True)
    student=User.objects.create_user(username='legacy-student',institution=inst,is_member=True)
    course=Course.objects.create(institution=inst,title='Existing course',is_published=True)
    VideoTranscript.objects.create(course=course,asr_status='completed',full_text='Original transcript',revision=1)
    progress=VideoProgress.objects.create(user=student,course=course,last_position=90,duration=180)
    book=Notebook.objects.create(user=student,name='Original notebook')
    note=Note.objects.create(user=student,notebook=book,title='Original note',content='Keep this')
    bot=Bot.objects.create(name='小宇',bot_type='planner')
    message=AIChatMessage.objects.create(user=student,bot=bot,role='user',content='Original message')
    args={'institution':inst.pk,'owner':owner.username,'members':[owner.username,student.username]}
    call_command('migrate_institution_workspace',**args,stdout=io.StringIO())
    assert not Workspace.objects.exists()
    call_command('migrate_institution_workspace',**args,apply=True,stdout=io.StringIO())
    ws=Workspace.objects.get(institution=inst)
    assert ws.service_ends_on==date.max and ws.max_students==200
    assert WorkspaceMembership.objects.get(user=owner,workspace=ws).role=='admin'
    learner=WorkspaceLearner.objects.get(account=student,workspace=ws).user
    progress.refresh_from_db();note.refresh_from_db();message.refresh_from_db();book.refresh_from_db()
    assert {progress.user_id,note.user_id,message.user_id,book.user_id}=={learner.pk}
    assert progress.last_position==90 and note.notebook_id==book.pk and note.content=='Keep this'
    client=APIClient();client.cookies['auth_token']=LoginSession.issue(student).key
    assert client.get('/api/courses/').status_code==403
    assert client.get(f'/api/courses/{course.pk}/transcript/').status_code==403
    assert client.get('/api/ai/history/').data==[]
    assert not Note.objects.filter(user=student).exists()
    client.credentials(HTTP_X_UNIMIND_WORKSPACE=str(ws.pk))
    assert client.get(f'/api/courses/{course.pk}/').status_code==200
    assert client.get(f'/api/courses/{course.pk}/transcript/').status_code==200
    assert [row['content'] for row in client.get('/api/ai/history/').data]==['Original message']
    assert client.get(f'/api/notes/items/{note.pk}/').status_code==200
    call_command('migrate_institution_workspace',**args,apply=True,stdout=io.StringIO())
    assert VideoProgress.objects.filter(pk=progress.pk,user=learner).count()==1
    assert Note.objects.filter(pk=note.pk,user=learner).count()==1
    student.refresh_from_db();assert student.is_member and student.is_active
