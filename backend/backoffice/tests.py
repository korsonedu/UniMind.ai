import hashlib
import hmac
import json
import time
import uuid
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import SecurityAuditLog
from courses.models import Course, CourseModule, TranscriptSegment, VideoTranscript
from quizzes.models import KnowledgePoint, Question, UserQuestionStatus
from users.models import User, Institution, LearningProduct, LearningGrant, UserAccessProfile


class BackofficeTests(TestCase):
    def setUp(self):
        self.actors = [str(uuid.uuid4()), str(uuid.uuid4())]
        self.admins = [User.objects.create_superuser(username=f'operator{i}', password='PreviewOnly123!') for i in range(2)]
        self.student = User.objects.create_user(username='learner', email='learner@example.test', email_verified=True)
        self.config = override_settings(
            UNIMIND_ADMIN_BRIDGE_SECRET='test-bridge-secret-with-more-than-32-characters',
            UNIMIND_DIRECTUS_ADMIN_MAP=dict(zip(self.actors, [user.pk for user in self.admins])),
            UNIMIND_CONTENT_INSTITUTION_ID='global',
            CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}},
        )
        self.config.enable()
        self.addCleanup(self.config.disable)
        cache.clear()
        self.client = APIClient()

    def call(self, operation, data=None, actor=0, headers=None):
        path = f'/api/backoffice/operations/{operation}/'
        body = json.dumps(data or {}, separators=(',', ':')).encode()
        timestamp, nonce = str(int(time.time())), str(uuid.uuid4())
        canonical = '\n'.join(['v1', 'POST', path, self.actors[actor], timestamp, nonce, hashlib.sha256(body).hexdigest()])
        signature = hmac.new(b'test-bridge-secret-with-more-than-32-characters', canonical.encode(), hashlib.sha256).hexdigest()
        signed = {'HTTP_X_UNIMIND_OPERATOR': self.actors[actor], 'HTTP_X_UNIMIND_TIMESTAMP': timestamp,
                  'HTTP_X_UNIMIND_NONCE': nonce, 'HTTP_X_UNIMIND_SIGNATURE': signature}
        if headers:
            signed.update(headers)
        response = self.client.post(path, body, content_type='application/json', **signed)
        return response, signed

    def test_authentication_and_replay(self):
        self.assertEqual(self.client.post('/api/backoffice/operations/meta/', {}, format='json').status_code, 401)
        self.assertEqual(self.call('meta', headers={'HTTP_X_UNIMIND_SIGNATURE': 'forged'})[0].status_code, 401)
        response, headers = self.call('meta')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.call('meta', actor=1)[0].status_code, 200)
        self.assertEqual(self.client.post('/api/backoffice/operations/meta/', '{}', content_type='application/json', **headers).status_code, 401)

    def test_bulk_assignment_rejects_cross_institution(self):
        module = CourseModule.objects.create(name='Existing module')
        other = Institution.objects.create(name='Other', slug='other')
        course = Course.objects.create(title='Existing course', institution=other)
        response, _ = self.call('courses.assign', {'module': module.pk, 'courses': [course.pk], 'request_id': str(uuid.uuid4())})
        self.assertEqual(response.status_code, 400)
        course.refresh_from_db()
        self.assertIsNone(course.module_id)

    def test_grant_is_idempotent(self):
        product = LearningProduct.objects.create(name='Existing service', duration_days=30)
        payload = {'user': self.student.pk, 'product': product.pk, 'source': 'course', 'request_id': str(uuid.uuid4())}
        first = self.call('grants.create', payload)[0]
        second = self.call('grants.create', payload, actor=1)[0]
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(LearningGrant.objects.count(), 1)

    def test_course_access_is_per_user_not_per_module_or_grant(self):
        profile = UserAccessProfile.objects.create(user=self.student, blocked_permissions=['unrelated.permission'])
        student_client = APIClient()
        student_client.credentials(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=self.student).key)
        with tempfile.TemporaryDirectory() as directory, override_settings(
            MEDIA_ROOT=directory, OSS_ACCESS_KEY_ID='',
            STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}},
        ):
            module = CourseModule.objects.create(subject='金融学', name='基础模块', is_public=False)
            course = Course.objects.create(title='Video', module=module, video_file=SimpleUploadedFile('lesson.mp4', b'local-fixture-video'))
            self.assertEqual(student_client.get(f'/api/courses/{course.pk}/').status_code, 200)
            media = '/media/' + course.video_file.name
            response = student_client.get(media, HTTP_RANGE='bytes=0-7')
            self.assertEqual(response.status_code, 206)
            response.close()
            areas = self.call('students.detail', {'id': self.student.pk})[0].data['enabled_features']
            denied = self.call('students.access.save', {'id': self.student.pk, 'enabled_features': [key for key in areas if key != 'course.video'], 'request_id': str(uuid.uuid4())})[0]
            self.assertEqual(denied.status_code, 200)
            self.assertEqual(student_client.get('/api/courses/').status_code, 403)
            self.assertEqual(student_client.get(f'/api/courses/{course.pk}/').status_code, 403)
            self.assertEqual(student_client.get(media).status_code, 403)
            features = student_client.get('/api/users/institution/me/features/').data['features']
            self.assertNotIn('course.video', features)
            self.assertIn('ai.assistant', features)
            profile.refresh_from_db()
            self.assertIn('unrelated.permission', profile.blocked_permissions)
            self.call('students.access.save', {'id': self.student.pk, 'enabled_features': areas, 'request_id': str(uuid.uuid4())})
            self.assertEqual(student_client.get(f'/api/courses/{course.pk}/').status_code, 200)
            self.assertEqual(LearningGrant.objects.count(), 0)

    def test_subject_classification_does_not_require_album_or_knowledge_point(self):
        payload = {'subject': '金融学', 'name': '基础', 'request_id': str(uuid.uuid4())}
        module = self.call('modules.save', payload)[0]
        self.assertEqual(module.status_code, 200)
        other = self.call('modules.save', {**payload, 'subject': '经济学', 'request_id': str(uuid.uuid4())})[0]
        self.assertEqual(other.status_code, 200)
        course = self.call('courses.save', {'title': 'New lesson', 'module': module.data['id'], 'request_id': str(uuid.uuid4())})[0]
        self.assertEqual(course.status_code, 200)
        self.assertEqual(course.data['subject_name'], '金融学')
        self.assertIsNone(course.data['album_obj'])
        self.assertIsNone(course.data['knowledge_point'])

    def test_question_management_validates_answers_scope_and_history(self):
        point = KnowledgePoint.objects.create(name='Preview point', level='kp', subject='Finance')
        other = Institution.objects.create(name='Other question owner', slug='question-owner')
        foreign = KnowledgePoint.objects.create(name='Other point', level='kp', institution=other)
        payload = {'text': 'Preview question', 'knowledge_point': point.pk, 'q_type': 'objective',
                   'options': ['First', 'Second'], 'correct_answer': 'C', 'request_id': str(uuid.uuid4())}
        self.assertEqual(self.call('questions.save', payload)[0].status_code, 400)
        payload['correct_answer'] = 'B'
        self.assertEqual(self.call('questions.save', {**payload, 'knowledge_point': foreign.pk})[0].status_code, 400)
        response = self.call('questions.save', payload)[0]
        self.assertEqual(response.status_code, 200, response.data)
        key = response.data['id']
        self.assertEqual(self.call('questions.detail', {'id': key}, actor=1)[0].data['correct_answer'], 'B')
        outsider = Question.objects.create(text='Other question', institution=other)
        response = self.call('questions.assign', {'questions': [key, outsider.pk], 'knowledge_point': point.pk, 'request_id': str(uuid.uuid4())})[0]
        self.assertEqual(response.status_code, 400)
        outsider.refresh_from_db()
        self.assertIsNone(outsider.knowledge_point_id)
        self.assertEqual(self.call('questions.list')[0].data['total'], 1)
        question = Question.objects.get(pk=key)
        Question.objects.filter(pk=key).update(subjective_type='')
        UserQuestionStatus.objects.create(user=self.student, question=question)
        self.assertEqual(self.call('questions.delete', {'id': key, 'request_id': str(uuid.uuid4())})[0].status_code, 400)
        self.assertTrue(Question.objects.filter(pk=key).exists())
        self.assertEqual(self.call('questions.save', {'id': key, 'q_type': 'subjective', 'subjective_type': 'short',
                         'grading_points': 'Preview criterion', 'request_id': str(uuid.uuid4())})[0].status_code, 400)
        self.assertEqual(self.call('questions.save', {'id': key, 'difficulty_level': 'hard', 'request_id': str(uuid.uuid4())})[0].data['difficulty'], 1400)
        self.assertEqual(self.call('questions.save', {'id': key, 'difficulty_level': 'normal', 'request_id': str(uuid.uuid4())})[0].data['difficulty'], 1200)

    def test_catalog_rejects_cycles_protects_references_and_invalidates_cache(self):
        root = KnowledgePoint.objects.create(name='Preview root', level='sub', subject='Finance')
        point = KnowledgePoint.objects.create(name='Preview point', level='kp', parent=root, subject='Finance')
        payload = {'id': root.pk, 'parent': point.pk, 'request_id': str(uuid.uuid4())}
        self.assertEqual(self.call('knowledge.save', payload)[0].status_code, 400)
        root.refresh_from_db()
        self.assertIsNone(root.parent_id)
        keys = ['knowledge_tree:ids:global', 'knowledge_tree:ids:global:subject:Finance', 'knowledge_tree:ids:global:subject:Economics']
        cache.set_many({key: [root.pk] for key in keys})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call('knowledge.save', {'id': root.pk, 'subject': 'Economics', 'request_id': str(uuid.uuid4())})[0]
        self.assertEqual(response.status_code, 200, response.data)
        point.refresh_from_db()
        self.assertEqual(point.subject, 'Economics')
        self.assertTrue(all(cache.get(key) is None for key in keys))
        self.assertEqual(self.call('knowledge.delete', {'id': root.pk, 'request_id': str(uuid.uuid4())})[0].status_code, 400)
        question = Question.objects.create(text='Referenced', knowledge_point=point)
        self.assertEqual(self.call('knowledge.delete', {'id': point.pk, 'request_id': str(uuid.uuid4())})[0].status_code, 400)
        question.delete()
        self.assertEqual(self.call('knowledge.delete', {'id': point.pk, 'request_id': str(uuid.uuid4())})[0].status_code, 200)

    def transcript_fixture(self, institution=None, asr_status='completed'):
        course = Course.objects.create(title='Transcript course', institution=institution)
        transcript = VideoTranscript.objects.create(
            course=course, full_text='原第一句\n原第二句', asr_status=asr_status,
            asr_provider='qwen_filetrans')
        segments = [
            TranscriptSegment.objects.create(transcript=transcript, start_time=0, end_time=1.5, text='原第一句', index=0),
            TranscriptSegment.objects.create(transcript=transcript, start_time=1.5, end_time=3, text='原第二句', index=1),
        ]
        return course, transcript, segments

    def test_transcript_get_returns_segments(self):
        course, transcript, segments = self.transcript_fixture()
        response = self.call('courses.transcript.get', {'id': course.pk})[0]
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'completed')
        self.assertEqual(response.data['provider'], 'qwen_filetrans')
        self.assertEqual([item['id'] for item in response.data['segments']], [item.pk for item in segments])
        self.assertEqual([item['text'] for item in response.data['segments']], ['原第一句', '原第二句'])
        self.assertEqual([item['index'] for item in response.data['segments']], [0, 1])
        self.assertEqual(response.data['revision'], 0)
        self.assertEqual(response.data['manual_edited_by_name'], '')
        missing = Course.objects.create(title='No transcript')
        response = self.call('courses.transcript.get', {'id': missing.pk})[0]
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], 'not_available')
        self.assertEqual(response.data['segments'], [])
        self.assertEqual(response.data['revision'], 0)

    def test_transcript_save_updates_full_text_manual_marker_and_audit(self):
        course, transcript, segments = self.transcript_fixture()
        request_id = str(uuid.uuid4())
        response = self.call('courses.transcript.save', {
            'id': course.pk, 'revision': 0, 'request_id': request_id,
            'segments': [{'id': segments[0].pk, 'text': '修订后的第一句'}],
        })[0]
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['updated'], 1)
        self.assertEqual(response.data['revision'], 1)
        transcript.refresh_from_db()
        segments[0].refresh_from_db()
        segments[1].refresh_from_db()
        self.assertEqual(segments[0].text, '修订后的第一句')
        self.assertEqual(segments[1].text, '原第二句')
        self.assertEqual(transcript.full_text, '修订后的第一句\n原第二句')
        self.assertTrue(transcript.is_manually_edited)
        self.assertEqual(transcript.manual_edited_by_id, self.admins[0].pk)
        self.assertIsNotNone(transcript.manual_edited_at)
        log = SecurityAuditLog.objects.get(request_id=request_id)
        detail = json.loads(log.detail)
        self.assertEqual(detail['operation'], 'courses.transcript.save')
        self.assertEqual(detail['target'], course.pk)
        self.assertEqual(detail['updated'], 1)
        self.assertNotIn('修订后的第一句', log.detail)
        detail_response = self.call('courses.transcript.get', {'id': course.pk})[0]
        self.assertEqual(detail_response.data['manual_edited_by_name'], 'operator0')
        self.assertEqual(detail_response.data['segments'][0]['text'], '修订后的第一句')

    def test_transcript_save_rejects_stale_revision_and_processing(self):
        course, transcript, segments = self.transcript_fixture()
        first = self.call('courses.transcript.save', {
            'id': course.pk, 'revision': 0, 'request_id': str(uuid.uuid4()),
            'segments': [{'id': segments[0].pk, 'text': '第一次修订'}],
        })[0]
        self.assertEqual(first.status_code, 200, first.data)
        stale = self.call('courses.transcript.save', {
            'id': course.pk, 'revision': 0, 'request_id': str(uuid.uuid4()),
            'segments': [{'id': segments[0].pk, 'text': '过期修订'}],
        })[0]
        self.assertEqual(stale.status_code, 400)
        self.assertIn('字幕已被其他人更新，请刷新后重试', str(stale.data))
        segments[0].refresh_from_db()
        self.assertEqual(segments[0].text, '第一次修订')
        VideoTranscript.objects.filter(pk=transcript.pk).update(asr_status='processing')
        busy = self.call('courses.transcript.save', {
            'id': course.pk, 'revision': 1, 'request_id': str(uuid.uuid4()),
            'segments': [{'id': segments[0].pk, 'text': '处理中修订'}],
        })[0]
        self.assertEqual(busy.status_code, 400)
        self.assertIn('字幕正在重新识别', str(busy.data))

    def test_transcript_rejects_cross_institution_course(self):
        other = Institution.objects.create(name='Other transcript owner', slug='transcript-owner')
        course, transcript, segments = self.transcript_fixture(institution=other)
        self.assertEqual(self.call('courses.transcript.get', {'id': course.pk})[0].status_code, 404)
        response = self.call('courses.transcript.save', {
            'id': course.pk, 'revision': 0, 'request_id': str(uuid.uuid4()),
            'segments': [{'id': segments[0].pk, 'text': '越权修订'}],
        })[0]
        self.assertEqual(response.status_code, 404)
        segments[0].refresh_from_db()
        self.assertEqual(segments[0].text, '原第一句')

    def test_student_cannot_call_transcript_operations(self):
        course, transcript, _ = self.transcript_fixture()
        student_client = APIClient()
        student_client.credentials(HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=self.student).key)
        for operation, payload in (
            ('courses.transcript.get', {'id': course.pk}),
            ('courses.transcript.save', {'id': course.pk, 'revision': 0, 'segments': [],
                                         'request_id': str(uuid.uuid4())}),
            ('courses.transcript.retranscribe', {'id': course.pk, 'request_id': str(uuid.uuid4())}),
            ('courses.outline.regenerate', {'id': course.pk, 'request_id': str(uuid.uuid4())}),
        ):
            response = student_client.post(f'/api/backoffice/operations/{operation}/', payload, format='json')
            self.assertEqual(response.status_code, 401)
        transcript.refresh_from_db()
        self.assertEqual(transcript.revision, 0)
        self.assertFalse(transcript.is_manually_edited)

    def test_transcript_dispatches_run_after_commit(self):
        course, transcript, _ = self.transcript_fixture()
        with mock.patch('courses.services.task_dispatcher.dispatch_transcription') as transcribe, \
                mock.patch('courses.services.task_dispatcher.dispatch_outline_generation') as outline:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.call('courses.transcript.retranscribe', {
                    'id': course.pk, 'request_id': str(uuid.uuid4())})[0]
            transcribe.assert_called_once_with(course.pk, force=True)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data, {'id': course.pk, 'status': 'processing'})
            with self.captureOnCommitCallbacks(execute=True):
                response = self.call('courses.outline.regenerate', {
                    'id': course.pk, 'request_id': str(uuid.uuid4())})[0]
            outline.assert_called_once_with(course.pk)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data, {'id': course.pk, 'status': 'processing'})
