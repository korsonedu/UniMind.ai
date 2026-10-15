from django.urls import path
from .views import OperationView

urlpatterns = [path('operations/<str:operation>/', OperationView.as_view())]
