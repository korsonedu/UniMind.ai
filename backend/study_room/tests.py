from rest_framework.test import APITestCase

from study_room.models import ChatMessage
from users.models import User


class RetiredStudyRoomTests(APITestCase):
    def test_room_routes_no_longer_modify_historical_messages(self):
        user = User.objects.create_user(username='historical-student', is_member=True)
        message = ChatMessage.objects.create(user=user, content='历史自习消息')
        self.client.force_authenticate(user=user)

        self.assertEqual(self.client.get('/api/study/messages/').status_code, 404)
        self.assertEqual(self.client.post(f'/api/study/messages/{message.pk}/undo/').status_code, 404)
        self.assertTrue(ChatMessage.objects.filter(pk=message.pk).exists())
