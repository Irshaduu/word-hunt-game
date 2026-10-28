"""
Tests for voice signalling (voice/consumers.py), over real sockets:
- a player joining hears who is already talking, and they hear that the player joined
- offers, answers and candidates reach only the player they're for
- muting shows to the others, and leaving tells them
- a fifth player is turned away, and so are random matches, people not in the room, and nobody signed in
- people who blocked each other are never introduced, and nothing passes between them
- the same player from a new page replaces their old socket, which then can't take them out
"""

import asyncio

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TransactionTestCase

from game.game_manager import ROOMS, GameRoom
from social import rules
from voice.consumers import VOICES
from wordhunt.asgi import application

PLAYERS = ['Asha', 'Ben', 'Cara', 'Dev', 'Eve']


class VoiceTests(TransactionTestCase):
    def setUp(self):
        VOICES.clear()
        ROOMS.clear()
        self.users, self.sessions = {}, {}
        for name in PLAYERS + ['Zed']:
            self.users[name] = User.objects.create_user(username=name)
            client = Client()
            client.force_login(self.users[name])
            self.sessions[name] = client.cookies['sessionid'].value
        room = GameRoom('VOX', creator='Asha')
        for name in PLAYERS:
            room.add_player(name)
        ROOMS['VOX'] = room

    def tearDown(self):
        VOICES.clear()
        ROOMS.clear()

    def socket(self, name=None, code='VOX'):
        headers = [(b'origin', b'http://testserver')]
        if name:
            headers.append((b'cookie', f'sessionid={self.sessions[name]}'.encode()))
        return WebsocketCommunicator(application, f'/ws/voice/{code}/', headers=headers)

    async def talk(self, name):
        """Join the room's voice chat. Keep what this returns: a dropped socket is collected mid-connect."""
        ws = self.socket(name)
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws

    async def drain(self, *sockets):
        for ws in sockets:
            while not await ws.receive_nothing(timeout=0.1):
                await ws.receive_json_from()

    async def assert_turned_away(self, ws):
        await ws.connect()
        message = await ws.receive_output()
        self.assertEqual((message['type'], message.get('code')), ('websocket.close', 4004))

    async def test_joining_hears_who_is_talking_and_they_hear_the_newcomer(self):
        asha = await self.talk('Asha')
        self.assertEqual(await asha.receive_json_from(), {'type': 'peers', 'peers': []})
        ben = await self.talk('Ben')
        self.assertEqual(await ben.receive_json_from(), {'type': 'peers', 'peers': ['Asha']})
        self.assertEqual(await asha.receive_json_from(), {'type': 'peer_joined', 'name': 'Ben'})
        await ben.disconnect()
        await asha.disconnect()

    async def test_signals_reach_only_the_player_they_are_for(self):
        asha, ben, cara = await self.talk('Asha'), await self.talk('Ben'), await self.talk('Cara')
        await self.drain(asha, ben, cara)
        offer = {'sdp': {'type': 'offer', 'sdp': 'v=0'}}
        await ben.send_json_to({'type': 'signal', 'to': 'Asha', 'data': offer})
        self.assertEqual(await asha.receive_json_from(), {'type': 'signal', 'from': 'Ben', 'data': offer})
        self.assertTrue(await cara.receive_nothing(timeout=0.1))
        for ws in (asha, ben, cara):
            await ws.disconnect()

    async def test_muting_shows_and_leaving_tells_the_others(self):
        asha, ben = await self.talk('Asha'), await self.talk('Ben')
        await self.drain(asha, ben)
        await ben.send_json_to({'type': 'mute', 'muted': True})
        self.assertEqual(await asha.receive_json_from(), {'type': 'peer_muted', 'name': 'Ben', 'muted': True})
        await ben.disconnect()
        self.assertEqual(await asha.receive_json_from(), {'type': 'peer_left', 'name': 'Ben'})
        await asha.disconnect()

    async def test_a_fifth_player_is_turned_away(self):
        four = [await self.talk(name) for name in PLAYERS[:4]]
        await self.assert_turned_away(self.socket('Eve'))
        for ws in four:
            await ws.disconnect()

    async def test_no_voice_in_random_matches_for_outsiders_or_signed_out(self):
        match = GameRoom('RND', creator='Asha', matchmade=True)
        match.add_player('Asha')
        ROOMS['RND'] = match
        await self.assert_turned_away(self.socket('Asha', code='RND'))
        await self.assert_turned_away(self.socket('Zed'))  # not a player in VOX
        await self.assert_turned_away(self.socket())

    async def test_people_who_blocked_each_other_are_never_introduced(self):
        await database_sync_to_async(rules.block)(self.users['Asha'], self.users['Ben'])
        asha = await self.talk('Asha')
        self.assertEqual(await asha.receive_json_from(), {'type': 'peers', 'peers': []})
        ben = await self.talk('Ben')
        self.assertEqual(await ben.receive_json_from(), {'type': 'peers', 'peers': []})
        self.assertTrue(await asha.receive_nothing(timeout=0.1))  # no peer_joined
        await ben.send_json_to({'type': 'signal', 'to': 'Asha', 'data': {}})
        await asha.send_json_to({'type': 'signal', 'to': 'Ben', 'data': {}})
        self.assertTrue(await asha.receive_nothing(timeout=0.1))
        self.assertTrue(await ben.receive_nothing(timeout=0.1))
        await ben.disconnect()
        self.assertTrue(await asha.receive_nothing(timeout=0.1))  # no peer_left either
        await asha.disconnect()

    async def test_a_new_page_replaces_the_old_socket(self):
        asha = await self.talk('Asha')
        ben_lobby = await self.talk('Ben')
        await self.drain(asha, ben_lobby)
        ben_game = await self.talk('Ben')  # the game page, before the lobby page's socket closed
        self.assertEqual(await ben_game.receive_json_from(), {'type': 'peers', 'peers': ['Asha']})
        self.assertEqual(await asha.receive_json_from(), {'type': 'peer_joined', 'name': 'Ben'})
        await ben_lobby.disconnect()
        await asyncio.sleep(0.05)
        self.assertIn('Ben', VOICES['VOX'])
        self.assertTrue(await asha.receive_nothing(timeout=0.1))  # no peer_left
        await ben_game.disconnect()
        await asha.disconnect()
