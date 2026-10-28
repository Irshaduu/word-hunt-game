from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path('ws/voice/<str:room_code>/', consumers.VoiceConsumer.as_asgi()),
    path('ws/rooms/<str:room_id>/', consumers.RoomConsumer.as_asgi()),
]
