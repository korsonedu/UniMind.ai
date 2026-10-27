"""Three targeted regressions from the single public-course review."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from rest_framework.test import APIRequestFactory


@pytest.mark.django_db
def test_album_upload_keeps_request_context(admin_user):
    from courses.models import Album
    from courses.views import OSSMultipartCompleteView
    album = Album.objects.create(name='upload album')
    view = OSSMultipartCompleteView()
    request = view.initialize_request(APIRequestFactory().post('/', {'title': 'uploaded course', 'album_obj': album.pk}))
    request.user = admin_user
    bucket = Mock()
    bucket.object_exists.return_value = True
    bucket.head_object.return_value = SimpleNamespace(content_length=16)
    with patch('courses.views._extract_cover_async'), patch('courses.services.task_dispatcher.dispatch_transcription'):
        response = view._create_course(request, bucket, 'institutions/public/synthetic.mp4')
    assert response.status_code == 201
    assert response.data['album']['id'] == album.pk


@pytest.mark.django_db
def test_course_entry_does_not_open_articles(auth_client, user):
    from articles.models import Article
    from users.models import CourseStudentStatus
    article = Article.objects.create(title='restricted article', content='private content')
    assert auth_client.get('/api/articles/').status_code == 403
    assert auth_client.get(f'/api/articles/{article.pk}/').status_code == 403
    assert auth_client.post(f'/api/articles/{article.pk}/view/').status_code == 403
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    assert auth_client.get(f'/api/articles/{article.pk}/').json()['content'] == 'private content'


@pytest.mark.django_db
def test_shared_tag_does_not_expand_private_courses(auth_client):
    from courses.models import Course, CourseModule, CourseTag, CourseTagRelation
    module = CourseModule.objects.create(subject='finance', name='open', is_public=True)
    public = Course.objects.create(title='open lesson', module=module)
    private = Course.objects.create(title='private lesson')
    tag = CourseTag.objects.create(name='shared', slug='shared')
    for course in (public, private):
        CourseTagRelation.objects.create(course=course, tag=tag)
    tags = auth_client.get('/api/courses/tags/').json()
    tags = tags.get('results', tags) if isinstance(tags, dict) else tags
    assert tags[0]['course_count'] == 1
    assert [course['id'] for course in tags[0]['courses']] == [public.pk]
    nested = auth_client.get(f'/api/courses/{public.pk}/').json()['tags'][0]
    assert nested['course_count'] == 1
    assert [course['id'] for course in nested['courses']] == [public.pk]
