"""
Tests for who is online (social/presence.py), over real /ws/me/ sockets:
- a page opening tells the player's friends they're online, and sends the player their friends' status
- the last page closing tells friends they're offline, after the grace; moving between pages never does
- a game page makes the player "in a game" for their friends
- friends changing makes every open page reload the list
- a socket with nobody signed in is turned away
"""

from unittest import mock

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TransactionTestCase

from game.game_manager import ROOMS, GameRoom
from social import presence, rules
from wordhunt.asgi import application


def socket(path, sessionid=None):
    headers = [(b'origin', b'http://testserver')]
    if sessionid:
        headers.append((b'cookie', f'sessionid={sessionid}'.encode()))
    return WebsocketCommunicator(application, path, headers=headers)


class PresenceTests(TransactionTestCase):
    def setUp(self):
        presence.forget_everyone()
        ROOMS.clear()
        self.sessions, self.users = {}, {}
        for name in ('Asha', 'Ben'):
            self.users[name] = User.objects.create_user(username=name, password='1111')
            client = Client()
            client.force_login(self.users[name])
            self.sessions[name] = client.cookies['sessionid'].value
        rules.send_request(self.users['Asha'], self.users['Ben'])
        rules.accept(self.users['Ben'], self.users['Asha'])

    def tearDown(self):
        presence.forget_everyone()
        ROOMS.clear()

    async def open_page(self, name):
        ws = socket('/ws/me/', self.sessions[name])
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws, await ws.receive_json_from()  # their friends, first thing

    async def test_a_friend_coming_online_is_seen_at_once(self):
        ben, friends = await self.open_page('Ben')
        self.assertEqual(friends, {'type': 'friends', 'friends': [{'name': 'Asha', 'status': 'offline'}], 'requests': 0})
        asha, friends = await self.open_page('Asha')
        self.assertEqual(friends['friends'], [{'name': 'Ben', 'status': 'online'}])
        self.assertEqual(await ben.receive_json_from(), {'type': 'friend_status', 'name': 'Asha', 'status': 'online'})
        await asha.disconnect()
        await ben.disconnect()

    @mock.patch('social.presence.OFFLINE_GRACE_SECONDS', 0)
    async def test_closing_the_last_page_shows_offline_after_the_grace(self):
        ben, _ = await self.open_page('Ben')
        asha, _ = await self.open_page('Asha')
        await ben.receive_json_from()  # Asha online
        await asha.disconnect()
        self.assertEqual(await ben.receive_json_from(), {'type': 'friend_status', 'name': 'Asha', 'status': 'offline'})
        await ben.disconnect()

    async def test_moving_between_pages_never_shows_offline(self):
        ben, _ = await self.open_page('Ben')
        asha, _ = await self.open_page('Asha')
        await ben.receive_json_from()  # Asha online
        await asha.disconnect()
        asha, _ = await self.open_page('Asha')  # the next page
        self.assertTrue(await ben.receive_nothing(timeout=0.2))
        self.assertEqual(presence.status(self.users['Asha'].id), presence.ONLINE)
        await asha.disconnect()
        await ben.disconnect()

    async def test_a_game_page_shows_in_a_game(self):
        room = GameRoom('ABC', creator='Asha')
        room.add_player('Asha')
        room.add_player('Ben')
        room.start_game()
        ROOMS['ABC'] = room
        ben, _ = await self.open_page('Ben')
        asha, _ = await self.open_page('Asha')
        await ben.receive_json_from()  # Asha online

        game = socket('/ws/game/ABC/', self.sessions['Asha'])
        await game.connect()
        self.assertEqual(await ben.receive_json_from(), {'type': 'friend_status', 'name': 'Asha', 'status': 'in_game'})
        await game.disconnect()
        self.assertEqual(await ben.receive_json_from(), {'type': 'friend_status', 'name': 'Asha', 'status': 'online'})
        await asha.disconnect()
        await ben.disconnect()

    async def test_friends_changing_makes_open_pages_reload_the_list(self):
        asha, _ = await self.open_page('Asha')
        cara = await User.objects.acreate(username='Cara')
        await rules.FriendRequest.objects.acreate(from_user=cara, to_user=self.users['Asha'])
        await get_channel_layer().group_send(presence.group(self.users['Asha'].id), {'type': 'friends_changed'})
        reloaded = await asha.receive_json_from()
        self.assertEqual((reloaded['type'], reloaded['requests']), ('friends', 1))
        await asha.disconnect()

    async def test_nobody_signed_in_is_turned_away(self):
        ws = socket('/ws/me/')
        await ws.connect()
        message = await ws.receive_output()
        self.assertEqual((message['type'], message.get('code')), ('websocket.close', 4004))
