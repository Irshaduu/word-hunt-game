"""
Tests for who a WebSocket speaks for:
- a socket with no signed-in session is refused (lobby and game)
- the signed-in user is the player, whatever name the URL carries
"""

from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TransactionTestCase

from game.game_manager import ROOMS, GameRoom
from wordhunt.asgi import application


def socket(path, sessionid=None):
    headers = [(b'origin', b'http://testserver')]
    if sessionid:
        headers.append((b'cookie', f'sessionid={sessionid}'.encode()))
    return WebsocketCommunicator(application, path, headers=headers)


class SocketIdentityTests(TransactionTestCase):
    def setUp(self):
        ROOMS.clear()
        ROOMS['ABC'] = GameRoom('ABC', creator='Alice')
        User.objects.create_user(username='Alice', password='1111')
        bob = User.objects.create_user(username='Bob', password='2222')
        client = Client()
        client.force_login(bob)
        self.bob_session = client.cookies['sessionid'].value

    def tearDown(self):
        ROOMS.clear()

    async def test_lobby_socket_without_session_is_refused(self):
        ws = socket('/ws/lobby/ABC/?username=Alice')
        connected, _ = await ws.connect()
        self.assertFalse(connected)
        self.assertNotIn('Alice', ROOMS['ABC'].players)

    async def test_game_socket_without_session_is_refused(self):
        ws = socket('/ws/game/ABC/?username=Alice')
        connected, _ = await ws.connect()
        self.assertFalse(connected)

    async def test_signed_in_user_is_the_player_whatever_the_url_says(self):
        ws = socket('/ws/lobby/ABC/?username=Alice', self.bob_session)
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        message = await ws.receive_json_from()
        self.assertEqual([p['username'] for p in message['players']], ['Bob'])
        self.assertNotIn('Alice', ROOMS['ABC'].players)
        await ws.disconnect()
