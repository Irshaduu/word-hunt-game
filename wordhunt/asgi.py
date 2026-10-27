import os
import django
from django.core.asgi import get_asgi_application
from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'wordhunt.settings')
django.setup()

from game.routing import websocket_urlpatterns as game_sockets
from social.routing import websocket_urlpatterns as social_sockets
from voice.routing import websocket_urlpatterns as voice_sockets

application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    # Sockets read the signed-in user from the session cookie, never from the URL.
    'websocket': AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(game_sockets + social_sockets + voice_sockets))),
})
