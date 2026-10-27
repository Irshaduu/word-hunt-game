"""
Tests for who a WebSocket speaks for, and how a lobby seat is kept:
- a socket with no signed-in session is refused (lobby and game)
- the signed-in user is the player, whatever name the URL carries
- a refused socket is closed with CLOSE_CANNOT_JOIN, so its page stops retrying
- a dropped lobby socket keeps its seat, shown as away; Leave gives it up at once
- a seat nobody comes back to is freed after the grace, and an empty lobby closes
- a player back after missing the start is sent on to the game
"""

import asyncio
from unittest import mock

from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TransactionTestCase

from game.consumers import CLOSE_CANNOT_JOIN
from game.game_manager import ROOMS, GameRoom
from wordhunt.asgi import application


def socket(path, sessionid=None):
    headers = [(b'origin', b'http://testserver')]
    if sessionid:
        headers.append((b'cookie', f'sessionid={sessionid}'.encode()))
    return WebsocketCommunicator(application, path, headers=headers)


async def assert_turned_away(test, ws):
    """The socket is accepted only to be closed with our code, so the page knows not to retry."""
    await ws.connect()
    message = await ws.receive_output()
    test.assertEqual((message['type'], message.get('code')), ('websocket.close', CLOSE_CANNOT_JOIN))


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
        await assert_turned_away(self, ws)
        self.assertNotIn('Alice', ROOMS['ABC'].players)

    async def test_game_socket_without_session_is_refused(self):
        ws = socket('/ws/game/ABC/?username=Alice')
        await assert_turned_away(self, ws)

    async def test_signed_in_user_is_the_player_whatever_the_url_says(self):
        ws = socket('/ws/lobby/ABC/?username=Alice', self.bob_session)
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        message = await ws.receive_json_from()
        self.assertEqual([p['username'] for p in message['players']], ['Bob'])
        self.assertNotIn('Alice', ROOMS['ABC'].players)
        await ws.disconnect()


class LobbySeatTests(TransactionTestCase):
    def setUp(self):
        ROOMS.clear()
        ROOMS['ABC'] = GameRoom('ABC', creator='Alice')
        self.sessions = {}
        for name in ('Alice', 'Bob'):
            user = User.objects.create_user(username=name, password='1111')
            client = Client()
            client.force_login(user)
            self.sessions[name] = client.cookies['sessionid'].value

    def tearDown(self):
        ROOMS.clear()

    async def join(self, name):
        ws = socket('/ws/lobby/ABC/', self.sessions[name])
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        await ws.receive_json_from()  # the player list, with them in it
        return ws

    async def test_a_dropped_socket_keeps_the_seat_shown_as_away(self):
        alice = await self.join('Alice')
        bob = await self.join('Bob')
        await alice.receive_json_from()  # Bob arrived
        await bob.disconnect()
        update = await alice.receive_json_from()
        self.assertEqual([(p['username'], p['is_connected']) for p in update['players']],
                         [('Alice', True), ('Bob', False)])
        self.assertIn('Bob', ROOMS['ABC'].players)
        await alice.disconnect()

    async def test_coming_back_takes_the_same_seat(self):
        alice = await self.join('Alice')
        bob = await self.join('Bob')
        await bob.disconnect()
        bob = await self.join('Bob')
        self.assertEqual([p['username'] for p in ROOMS['ABC'].get_player_list()], ['Alice', 'Bob'])
        self.assertTrue(ROOMS['ABC'].players['Bob'].is_connected)
        await bob.disconnect()
        await alice.disconnect()

    async def test_leave_gives_the_seat_up_at_once(self):
        alice = await self.join('Alice')
        bob = await self.join('Bob')
        await alice.receive_json_from()  # Bob arrived
        await bob.send_json_to({'type': 'leave'})
        update = await alice.receive_json_from()
        self.assertEqual([p['username'] for p in update['players']], ['Alice'])
        await bob.disconnect()
        await alice.disconnect()

    @mock.patch('game.consumers.LOBBY_GRACE_SECONDS', 0)
    async def test_a_seat_nobody_comes_back_to_is_freed_and_the_empty_lobby_closes(self):
        alice = await self.join('Alice')
        await alice.disconnect()
        await asyncio.sleep(0.1)  # the grace (none, here) runs out
        self.assertNotIn('ABC', ROOMS)

    async def test_back_after_missing_the_start_goes_on_to_the_game(self):
        room = ROOMS['ABC']
        room.add_player('Alice')
        room.add_player('Bob')
        room.start_game()
        bob = socket('/ws/lobby/ABC/', self.sessions['Bob'])
        await bob.connect()
        self.assertEqual((await bob.receive_json_from())['type'], 'game_starting')
        await bob.disconnect()

    async def test_a_lobby_that_is_gone_turns_the_socket_away(self):
        ROOMS.clear()
        await assert_turned_away(self, socket('/ws/lobby/ABC/', self.sessions['Alice']))
