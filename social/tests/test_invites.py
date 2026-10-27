"""
Tests for game invites and the queue over /ws/me/:
- inviting a friend who is online makes a room, sends the inviter to it, and tells the friend
- only friends can be invited, and only while they're online and not in a game
- from a lobby, an invite is to that lobby, which the inviter must be in
- invites are limited per player
- "Not now" tells the inviter, and only someone whose invite arrived can be told
- a page can wait in the random-match queue, and closing it stops the wait
"""

from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from game import matchmaking
from game.game_manager import ROOMS, GameRoom
from social import presence, rules
from social.tests.test_views import OpenPage
from wordhunt.asgi import application


class InviteTests(TestCase):
    def setUp(self):
        cache.clear()
        presence.forget_everyone()
        ROOMS.clear()
        self.asha = User.objects.create_user(username='Asha', password='1234')
        self.ben = User.objects.create_user(username='Ben', password='1234')
        rules.send_request(self.asha, self.ben)
        rules.accept(self.ben, self.asha)
        presence._online.add(self.ben.id)  # Ben has a page open
        self.client.force_login(self.asha)

    def tearDown(self):
        presence.forget_everyone()
        ROOMS.clear()

    def test_inviting_a_friend_makes_a_room_and_tells_them(self):
        ben_pages = OpenPage(self.ben)
        response = self.client.post(reverse('invite', args=['Ben']))
        [code] = ROOMS
        self.assertRedirects(response, reverse('lobby', args=[code]))
        self.assertEqual(ben_pages.received(), [{'type': 'invite', 'from': 'Asha', 'from_id': self.asha.id, 'room': code}])

    def test_only_friends_can_be_invited(self):
        User.objects.create_user(username='Cara')
        self.assertEqual(self.client.post(reverse('invite', args=['Cara'])).status_code, 404)

    def test_a_friend_not_online_or_in_a_game_is_not_invited(self):
        presence.forget_everyone()
        self.assertContains(self.client.post(reverse('invite', args=['Ben']), follow=True), "Ben isn&#x27;t online right now.")
        presence._online.add(self.ben.id)
        presence._games[self.ben.id] = 1
        self.assertContains(self.client.post(reverse('invite', args=['Ben']), follow=True), 'Ben is in a game right now.')
        self.assertFalse(ROOMS)

    def test_from_a_lobby_the_invite_is_to_that_lobby(self):
        room = GameRoom('LOB', creator='Asha')
        room.add_player('Asha')
        ROOMS['LOB'] = room
        response = self.client.post(reverse('invite', args=['Ben']), {'room': 'lob'})
        self.assertEqual(response.json(), {'ok': True, 'message': 'Invited Ben.'})
        self.assertEqual(list(ROOMS), ['LOB'])

    def test_a_lobby_invite_needs_the_inviter_in_that_lobby(self):
        ROOMS['LOB'] = GameRoom('LOB', creator='Cara')
        response = self.client.post(reverse('invite', args=['Ben']), {'room': 'LOB'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_invites_are_limited(self):
        for _ in range(10):
            self.client.post(reverse('invite', args=['Ben']))
        response = self.client.post(reverse('invite', args=['Ben']), follow=True)
        self.assertContains(response, 'a lot of invites')
        self.assertEqual(len(ROOMS), 10)


class InviteSocketTests(TransactionTestCase):
    def setUp(self):
        presence.forget_everyone()
        matchmaking.forget_everyone()
        self.users, self.sessions = {}, {}
        for name in ('Asha', 'Ben'):
            self.users[name] = User.objects.create_user(username=name)
            client = Client()
            client.force_login(self.users[name])
            self.sessions[name] = client.cookies['sessionid'].value

    def tearDown(self):
        presence.forget_everyone()
        matchmaking.forget_everyone()

    async def open_page(self, name):
        ws = WebsocketCommunicator(application, '/ws/me/', headers=[
            (b'origin', b'http://testserver'), (b'cookie', f'sessionid={self.sessions[name]}'.encode())])
        await ws.connect()
        await ws.receive_json_from()  # their friends
        return ws

    async def test_not_now_tells_the_inviter_once(self):
        asha, ben = await self.open_page('Asha'), await self.open_page('Ben')
        await get_channel_layer().group_send(presence.group(self.users['Ben'].id), {
            'type': 'invite', 'from': 'Asha', 'from_id': self.users['Asha'].id, 'room': 'ABC'})
        self.assertEqual(await ben.receive_json_from(), {'type': 'invite', 'from': 'Asha', 'room': 'ABC'})

        await ben.send_json_to({'type': 'decline_invite', 'from': 'Asha'})
        self.assertEqual(await asha.receive_json_from(), {'type': 'invite_declined', 'by': 'Ben'})
        await ben.send_json_to({'type': 'decline_invite', 'from': 'Asha'})  # the invite is used up
        self.assertTrue(await asha.receive_nothing(timeout=0.2))
        await asha.disconnect()
        await ben.disconnect()

    async def test_a_page_waits_in_the_queue_until_it_closes(self):
        ben = await self.open_page('Ben')
        await ben.send_json_to({'type': 'queue_join'})
        self.assertEqual(await ben.receive_json_from(), {'type': 'queue_joined'})
        self.assertTrue(matchmaking.is_waiting(self.users['Ben'].id))
        await ben.disconnect()
        self.assertFalse(matchmaking.is_waiting(self.users['Ben'].id))
