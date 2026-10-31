"""Registered students see only explicitly public course modules."""
import pytest
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_registered_public_course_boundary(auth_client, user, settings, tmp_path):
    from courses.models import Album, Course, CourseModule, StartupMaterial
    from users.models import CourseStudentStatus
    settings.MEDIA_ROOT = str(tmp_path)
    settings.UNIMIND_CONTENT_INSTITUTION_ID = 'global'
    settings.OSS_ACCESS_KEY_ID = ''
    album = Album.objects.create(name='mixed album')
    empty_album = Album.objects.create(name='empty album')
    public = CourseModule.objects.create(subject='finance', name='public', is_public=True)
    private = CourseModule.objects.create(subject='finance', name='private')
    open_course = Course.objects.create(title='public lesson', module=public, album_obj=album,
                                       video_file='public.mp4', courseware='public.pdf')
    paid = Course.objects.create(title='paid lesson', module=private, album_obj=album,
                                video_file='paid.mp4')
    unassigned = Course.objects.create(title='unassigned lesson')
    material = StartupMaterial.objects.create(name='paid startup', file='startup.pdf')
    for name in ('public.mp4', 'public.pdf', 'paid.mp4', 'startup.pdf'):
        (tmp_path / name).write_bytes(b'synthetic file')
    for course in (paid, unassigned):
        assert auth_client.get(f'/api/courses/{course.pk}/').status_code == 404
    listed = auth_client.get('/api/courses/')
    assert listed.status_code == 200
    assert [item['id'] for item in listed.json()['items']] == [open_course.pk]
    detail = auth_client.get(f'/api/courses/{open_course.pk}/')
    assert detail.status_code == 200
    assert [item['id'] for item in detail.json()['album']['courses']] == [open_course.pk]
    assert auth_client.get(f'/api/courses/modules/{private.pk}/').status_code == 404
    assert auth_client.get('/api/courses/modules/').json()[0]['id'] == public.pk
    assert auth_client.get(f'/api/courses/albums/{album.pk}/').json()['course_count'] == 1
    assert auth_client.get(f'/api/courses/albums/{empty_album.pk}/').status_code == 404
    assert auth_client.get(f'/api/courses/startup-materials/{material.pk}/').status_code == 403
    for action in ('outline', 'transcript'):
        assert auth_client.post(f'/api/courses/{open_course.pk}/{action}/').status_code == 403
    auth_client.cookies['auth_token'] = Token.objects.create(user=user).key
    for name in ('public.mp4', 'public.pdf'):
        response = auth_client.get('/media/' + name)
        assert response.status_code == 200
        response.close()
    for name in ('paid.mp4', 'startup.pdf'):
        assert auth_client.get('/media/' + name).status_code == 403
    assert APIClient().get('/media/public.mp4').status_code == 401
    assert APIClient().get('/api/courses/').status_code == 401
    from ai_engine.tool_permissions import filter_tools
    assert filter_tools('planner', None, [{'function': {'name': 'search_courses'}}], user=user) == []
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    assert auth_client.get(f'/api/courses/{paid.pk}/').status_code == 200
    assert auth_client.get(f'/api/courses/{unassigned.pk}/').status_code == 200
    assert auth_client.get(f'/api/courses/startup-materials/{material.pk}/').status_code == 200
    assert auth_client.get(f'/api/courses/albums/{empty_album.pk}/').status_code == 200
