"""
Tests for random matches (game/matchmaking.py):
- two players waiting are matched after the gather, into one new room made for them
- four waiting are matched at once
- leaving the queue gives up the place; a page closing only gives up its own
- two people who blocked each other are never matched
- a new match starts by itself once everyone is in its lobby
- if not everyone arrives in time, it starts with those who did, or closes if only one came
"""

import asyncio
from unittest import mock

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, TransactionTestCase

from game import matchmaking
from game.game_manager import PICKING, ROOMS
from social import rules
from wordhunt.asgi import application


def no_background(coro):
    """Stand-in for spawn: don't start the arrival timer, the test runs it itself."""
    coro.close()


class QueueTests(TransactionTestCase):
    def setUp(self):
        matchmaking.forget_everyone()
        ROOMS.clear()
        self.players = [User.objects.create_user(username=f'P{i}') for i in range(5)]

    def tearDown(self):
        matchmaking.forget_everyone()
        ROOMS.clear()

    async def join(self, user):
        """A channel standing in for the socket of the page that asked."""
        page = await get_channel_layer().new_channel()
        await matchmaking.join(user.id, user.username, page)
        return page

    async def heard(self, page):
        return await asyncio.wait_for(get_channel_layer().receive(page), timeout=1)

    @mock.patch('game.matchmaking.GATHER_SECONDS', 0)
    async def test_two_waiting_are_matched_into_a_room_made_for_them(self):
        a, b = self.players[:2]
        page_a, page_b = await self.join(a), await self.join(b)
        found_a, found_b = await self.heard(page_a), await self.heard(page_b)
        self.assertEqual(found_a['type'], 'match_found')
        self.assertEqual(found_a['room'], found_b['room'])
        room = ROOMS[found_a['room']]
        self.assertTrue(room.matchmade)
        self.assertEqual(room.expected, {'P0', 'P1'})
        self.assertFalse(matchmaking.is_waiting(a.id))

    async def test_four_waiting_are_matched_at_once(self):
        pages = [await self.join(user) for user in self.players[:4]]
        rooms = {(await self.heard(page))['room'] for page in pages}
        self.assertEqual(len(rooms), 1)
        self.assertFalse(matchmaking.is_waiting(self.players[4].id))

    @mock.patch('game.matchmaking.GATHER_SECONDS', 0)
    async def test_leaving_gives_up_the_place(self):
        a, b, c = self.players[:3]
        page_a = await self.join(a)
        matchmaking.leave(a.id, page_a)
        page_b, page_c = await self.join(b), await self.join(c)
        self.assertEqual((await self.heard(page_b))['room'], (await self.heard(page_c))['room'])
        self.assertFalse(matchmaking.is_waiting(a.id))

    async def test_a_page_closing_only_gives_up_its_own_place(self):
        a = self.players[0]
        first_page = await self.join(a)
        await self.join(a)  # the same player, now waiting on another page
        matchmaking.leave(a.id, first_page)
        self.assertTrue(matchmaking.is_waiting(a.id))

    @mock.patch('game.matchmaking.GATHER_SECONDS', 0)
    async def test_people_who_blocked_each_other_never_meet(self):
        a, b, c = self.players[:3]
        await database_sync_to_async(rules.block)(a, b)
        await self.join(a)
        await self.join(b)
        await asyncio.sleep(0.05)  # the gather ran: these two can't play together
        self.assertTrue(matchmaking.is_waiting(a.id) and matchmaking.is_waiting(b.id))
        page_c = await self.join(c)
        room = ROOMS[(await self.heard(page_c))['room']]
        self.assertEqual(room.expected, {'P0', 'P2'})  # the oldest who can play with C
        self.assertTrue(matchmaking.is_waiting(b.id))


class MatchLobbyTests(TransactionTestCase):
    def setUp(self):
        matchmaking.forget_everyone()
        ROOMS.clear()
        self.sessions = {}
        for name in ('Alice', 'Bob', 'Cara'):
            client = Client()
            client.force_login(User.objects.create_user(username=name))
            self.sessions[name] = client.cookies['sessionid'].value

    def tearDown(self):
        ROOMS.clear()

    async def arrive(self, room, name):
        """A lobby socket. Keep what this returns: a dropped one is collected mid-connect."""
        ws = WebsocketCommunicator(application, f'/ws/lobby/{room.room_code}/', headers=[
            (b'origin', b'http://testserver'), (b'cookie', f'sessionid={self.sessions[name]}'.encode())])
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws

    async def test_a_match_starts_once_everyone_is_here(self):
        room = matchmaking.new_match_room(['Alice', 'Bob'])
        alice = await self.arrive(room, 'Alice')
        bob = await self.arrive(room, 'Bob')
        heard = [(await alice.receive_json_from())['type'] for _ in range(3)]
        self.assertEqual(heard[-1], 'game_starting')
        self.assertEqual(room.state, PICKING)
        await bob.disconnect()
        await alice.disconnect()

    @mock.patch('game.matchmaking.ARRIVE_SECONDS', 0)
    async def test_with_two_of_three_arrived_it_starts_with_them(self):
        with mock.patch('game.matchmaking.spawn', no_background):
            room = matchmaking.new_match_room(['Alice', 'Bob', 'Cara'])
        alice = await self.arrive(room, 'Alice')
        bob = await self.arrive(room, 'Bob')
        await matchmaking._start_or_close(room)
        self.assertEqual(room.state, PICKING)
        self.assertEqual(sorted(room.turn_order), ['Alice', 'Bob'])
        await bob.disconnect()
        await alice.disconnect()

    @mock.patch('game.matchmaking.ARRIVE_SECONDS', 0)
    async def test_with_only_one_arrived_the_match_closes(self):
        with mock.patch('game.matchmaking.spawn', no_background):
            room = matchmaking.new_match_room(['Alice', 'Bob'])
        alice = await self.arrive(room, 'Alice')
        await alice.receive_json_from()  # the player list
        await matchmaking._start_or_close(room)
        self.assertEqual((await alice.receive_json_from())['type'], 'match_cancelled')
        self.assertNotIn(room.room_code, ROOMS)
        await alice.disconnect()
