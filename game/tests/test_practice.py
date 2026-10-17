"""
Tests for the one-tap demo and practice games against Robo:
- a practice room seats Robo, so one person can start a game
- Robo never becomes host, never loses its seat to a person, and comes back after Play Again
- the demo signs in a throwaway guest (no PIN) and opens a practice room
- the demo is limited per address, and yesterday's guests are deleted
- guests stay off the global leaderboard; nobody can register as Robo
- Robo picks on its turn and finds the word on the hunt (socket code, no real waiting)
- a practice game never touches the leaderboard, and a game ends once
"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.consumers import GameConsumer
from game.game_manager import (
    BOT_NAME, ROOMS, GameRoom,
    GAME_OVER, HUNTING, LOBBY, PICKING, ROUND_END, SHOWING,
)


class PracticeRoomTests(TestCase):
    def test_practice_room_seats_robo(self):
        room = GameRoom('PRC', creator='Asha', practice=True)
        self.assertIn(BOT_NAME, room.players)
        self.assertEqual(room.human_count(), 0)

    def test_one_person_can_start_a_practice_game(self):
        room = GameRoom('PRC', creator='Asha', practice=True)
        room.add_player('Asha')
        ok, _ = room.start_game()
        self.assertTrue(ok)
        self.assertEqual(room.state, PICKING)

    def test_a_person_cannot_take_robos_seat(self):
        room = GameRoom('PRC', creator='Asha', practice=True)
        ok, _ = room.add_player(BOT_NAME)
        self.assertFalse(ok)

    def test_host_never_passes_to_robo(self):
        room = GameRoom('PRC', creator='Asha', practice=True)
        room.add_player('Asha')
        room.remove_player('Asha')
        self.assertIsNone(room.creator)
        self.assertEqual(room.human_count(), 0)

    def test_play_again_seats_robo_again(self):
        room = GameRoom('PRC', creator='Asha', practice=True)
        room.add_player('Asha')
        room.start_game()
        room.state = GAME_OVER
        room.reset_to_lobby('Asha')
        self.assertEqual(room.state, LOBBY)
        self.assertIn(BOT_NAME, room.players)
        self.assertEqual(room.creator, 'Asha')

    def test_bot_hunters_skip_the_picker(self):
        room = GameRoom('PRC', creator='Asha', practice=True)
        room.add_player('Asha')
        room.start_game()
        room.current_picker = BOT_NAME
        self.assertEqual(room.bot_hunters(), [])
        room.current_picker = 'Asha'
        self.assertEqual(room.bot_hunters(), [BOT_NAME])

    def test_an_ordinary_room_has_no_bot(self):
        room = GameRoom('ORD', creator='Asha')
        self.assertNotIn(BOT_NAME, room.players)
        self.assertFalse(room.is_bot(BOT_NAME))


class DemoViewTests(TestCase):
    def setUp(self):
        cache.clear()
        ROOMS.clear()

    def tearDown(self):
        ROOMS.clear()

    def test_demo_signs_in_a_guest_and_opens_a_practice_room(self):
        response = self.client.post(reverse('demo'), follow=True)
        guest = User.objects.get(profile__is_guest=True)
        self.assertTrue(guest.username.startswith('Guest'))
        self.assertFalse(guest.has_usable_password())
        self.assertEqual(int(self.client.session['_auth_user_id']), guest.id)
        self.assertTemplateUsed(response, 'game/lobby.html')
        room = ROOMS[response.context['room_code']]
        self.assertTrue(room.practice)
        self.assertEqual(room.creator, guest.username)
        self.assertIn(BOT_NAME, room.players)

    def test_demo_needs_a_post(self):
        response = self.client.get(reverse('demo'))
        self.assertRedirects(response, reverse('landing'))
        self.assertFalse(User.objects.exists())

    def test_demo_is_limited_per_address(self):
        for _ in range(10):
            self.client.post(reverse('demo'))
            self.client.logout()
        response = self.client.post(reverse('demo'), follow=True)
        self.assertEqual(User.objects.count(), 10)
        self.assertContains(response, 'Too many demo games')

    def test_yesterdays_guests_are_deleted(self):
        self.client.post(reverse('demo'))
        old = User.objects.get(profile__is_guest=True)
        User.objects.filter(id=old.id).update(date_joined=timezone.now() - timedelta(days=2))
        real = User.objects.create_user(username='Asha', password='1234')
        User.objects.filter(id=real.id).update(date_joined=timezone.now() - timedelta(days=30))
        self.client.logout()

        self.client.post(reverse('demo'))
        self.assertFalse(User.objects.filter(id=old.id).exists())
        self.assertTrue(User.objects.filter(id=real.id).exists())
        self.assertEqual(User.objects.filter(profile__is_guest=True).count(), 1)

    def test_signed_in_player_goes_straight_to_practice(self):
        User.objects.create_user(username='Asha', password='1234')
        self.client.login(username='Asha', password='1234')
        response = self.client.post(reverse('demo'), follow=True)
        self.assertTemplateUsed(response, 'game/lobby.html')
        self.assertFalse(User.objects.filter(profile__is_guest=True).exists())

    def test_practice_needs_sign_in(self):
        response = self.client.get(reverse('practice_room'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ROOMS)

    def test_guests_are_not_on_the_leaderboard(self):
        self.client.post(reverse('demo'))
        User.objects.create_user(username='Asha', password='1234')
        names = [p['username'] for p in self.client.get(reverse('api_leaderboard')).json()['players']]
        self.assertEqual(names, ['Asha'])

    def test_nobody_can_register_as_robo(self):
        self.client.post(reverse('register'), {'username': 'robo', 'pin': '1234'})
        self.assertFalse(User.objects.filter(username=BOT_NAME).exists())


class StubLayer:
    def __init__(self):
        self.sent = []

    async def group_send(self, group, message):
        self.sent.append(message)


def consumer_for(room):
    consumer = GameConsumer()
    consumer.channel_layer = StubLayer()
    consumer.room_code = room.room_code
    consumer.group_name = f'game_{room.room_code}'
    consumer.username = 'Asha'
    return consumer


def no_background(coro):
    """Stand-in for asyncio.ensure_future: don't start follow-on timers in a test."""
    coro.close()


@mock.patch('game.consumers.asyncio.ensure_future', no_background)
@mock.patch('game.consumers.asyncio.sleep', mock.AsyncMock())
class RoboPlaysTests(TestCase):
    def setUp(self):
        ROOMS.clear()
        self.room = GameRoom('PRC', creator='Asha', practice=True)
        self.room.add_player('Asha')
        self.room.start_game()
        ROOMS['PRC'] = self.room

    def tearDown(self):
        ROOMS.clear()

    async def test_robo_picks_on_its_turn(self):
        self.room.current_picker = BOT_NAME
        consumer = consumer_for(self.room)
        await consumer._bot_pick(self.room, self.room.pick_start_time)
        self.assertEqual(self.room.state, SHOWING)
        self.assertEqual(consumer.channel_layer.sent[0]['type'], 'word_picked')
        self.assertEqual(consumer.channel_layer.sent[0]['picker'], BOT_NAME)

    async def test_a_late_pick_never_acts_on_a_later_turn(self):
        self.room.current_picker = BOT_NAME
        consumer = consumer_for(self.room)
        await consumer._bot_pick(self.room, self.room.pick_start_time - 30)
        self.assertEqual(self.room.state, PICKING)
        self.assertEqual(consumer.channel_layer.sent, [])

    def asha_picks_first(self):
        # start_game shuffles the turn order; fix it so the next turn is known.
        self.room.turn_order = ['Asha', BOT_NAME]
        self.room.current_turn_index = 0
        self.room.current_picker = 'Asha'

    async def test_robo_finds_the_word_and_the_round_moves_on(self):
        self.asha_picks_first()
        self.room.pick_word('Asha', self.room.board[0]['word'])
        self.room.start_hunt()
        consumer = consumer_for(self.room)
        await consumer._bot_hunt(self.room, BOT_NAME, self.room.pick_start_time)
        types = [m['type'] for m in consumer.channel_layer.sent]
        self.assertEqual(types[0], 'player_found')
        self.assertEqual(consumer.channel_layer.sent[0]['username'], BOT_NAME)
        self.assertIn('new_turn', types)
        self.assertEqual(self.room.current_picker, BOT_NAME)

    async def test_a_round_ends_once(self):
        self.asha_picks_first()
        self.room.pick_word('Asha', self.room.board[0]['word'])
        self.room.start_hunt()
        consumer = consumer_for(self.room)
        self.room.state = ROUND_END  # someone else already ended it
        await consumer.finish_round(self.room)
        self.assertEqual(consumer.channel_layer.sent, [])

    async def test_practice_never_touches_the_leaderboard_and_ends_once(self):
        asha = await User.objects.acreate(username='Asha')
        consumer = consumer_for(self.room)
        await consumer.broadcast_game_over(self.room, 'Asha')
        await consumer.broadcast_game_over(self.room, 'Asha')
        self.assertEqual([m['type'] for m in consumer.channel_layer.sent], ['game_over'])
        profile = await type(asha.profile).objects.aget(user=asha)
        self.assertEqual(profile.first_places, 0)
        self.assertEqual(self.room.state, GAME_OVER)
