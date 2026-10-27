"""An empty synthetic transcript must not leave the student waiting on a task."""
from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_empty_completed_transcript_is_not_dispatched(auth_client, user):
    from courses.models import Course, VideoTranscript, CourseOutline
    from users.models import CourseStudentStatus
    CourseStudentStatus.objects.create(user=user, is_course_student=True)
    course = Course.objects.create(title='synthetic course')
    VideoTranscript.objects.create(course=course, asr_status='completed', full_text='')
    with patch('courses.services.task_dispatcher.dispatch_outline_generation') as dispatch:
        response = auth_client.post(f'/api/courses/{course.pk}/outline/')
    assert response.status_code == 400
    dispatch.assert_not_called()
    assert not CourseOutline.objects.filter(course=course).exists()
