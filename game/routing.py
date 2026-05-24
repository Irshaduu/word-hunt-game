from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/lobby/<str:room_code>/', consumers.LobbyConsumer.as_asgi()),
    path('ws/game/<str:room_code>/', consumers.GameConsumer.as_asgi()),
]
