import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "school_system.settings")
django.setup()

from django.test import RequestFactory
from faq_system.views import QuestionListCreateView
from users.models import User

user = User.objects.create(username='testuser', email='test@example.com')
request = RequestFactory().get('/api/qa/questions/?filter=all&search=')
request.user = user

view = QuestionListCreateView.as_view()
try:
    response = view(request)
    print("Status code:", response.status_code)
    print("Response:", response.data)
except Exception as e:
    import traceback
    traceback.print_exc()
