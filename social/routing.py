from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/me/', consumers.MeConsumer.as_asgi()),
]
