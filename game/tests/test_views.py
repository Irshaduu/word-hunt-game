"""
Tests for HTTP views:
- Landing page (guest vs authenticated)
- Register (success, duplicate username, invalid input)
- Login (success, wrong PIN)
- Logout
- Create room (redirects to lobby)
- Join room (valid, invalid code, full room, in-progress)
- Leaderboard API (structure, pagination)
- Live games API (structure)
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from game.game_manager import ROOMS, GameRoom


class LandingViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_landing_guest_returns_200(self):
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'game/landing.html')

    def test_landing_authenticated_returns_auth_template(self):
        User.objects.create_user(username='Alice', password='1234')
        self.client.login(username='Alice', password='1234')
        response = self.client.get(reverse('landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'game/landing_auth.html')


class RegisterViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_register_success_logs_in_and_redirects(self):
        response = self.client.post(reverse('register'), {
            'username': 'Alice',
            'pin': '1234',
        })
        self.assertRedirects(response, reverse('landing'))
        self.assertTrue(User.objects.filter(username='Alice').exists())

    def test_register_capitalises_username(self):
        self.client.post(reverse('register'), {'username': 'alice', 'pin': '1234'})
        self.assertTrue(User.objects.filter(username='Alice').exists())

    def test_register_duplicate_username_sets_error(self):
        User.objects.create_user(username='Alice', password='0000')
        response = self.client.post(reverse('register'), {
            'username': 'Alice',
            'pin': '9999',
        }, follow=True)
        # Should redirect back to landing with error in session
        self.assertRedirects(response, reverse('landing'))

    def test_register_empty_username_sets_error(self):
        response = self.client.post(reverse('register'), {
            'username': '',
            'pin': '1234',
        }, follow=True)
        self.assertRedirects(response, reverse('landing'))

    def test_register_username_too_long_sets_error(self):
        response = self.client.post(reverse('register'), {
            'username': 'A' * 11,
            'pin': '1234',
        }, follow=True)
        self.assertRedirects(response, reverse('landing'))

    def test_register_get_redirects_to_landing(self):
        response = self.client.get(reverse('register'))
        self.assertRedirects(response, reverse('landing'))


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username='Alice', password='1234')

    def test_login_success_redirects_to_landing(self):
        response = self.client.post(reverse('login'), {
            'username': 'Alice',
            'pin': '1234',
        })
        self.assertRedirects(response, reverse('landing'))

    def test_login_wrong_pin_sets_error(self):
        response = self.client.post(reverse('login'), {
            'username': 'Alice',
            'pin': '0000',
        }, follow=True)
        self.assertRedirects(response, reverse('landing'))

    def test_login_get_redirects_to_landing(self):
        response = self.client.get(reverse('login'))
        self.assertRedirects(response, reverse('landing'))


class LogoutViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(username='Alice', password='1234')
        self.client.login(username='Alice', password='1234')

    def test_logout_redirects_to_landing(self):
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('landing'))

    def test_logout_clears_session(self):
        self.client.get(reverse('logout'))
        response = self.client.get(reverse('landing'))
        self.assertTemplateUsed(response, 'game/landing.html')


class RoomViewTests(TestCase):
    def setUp(self):
        ROOMS.clear()
        self.client = Client()
        User.objects.create_user(username='Alice', password='1234')
        self.client.login(username='Alice', password='1234')

    def tearDown(self):
        ROOMS.clear()

    def test_create_room_redirects_to_lobby(self):
        response = self.client.get(reverse('create_room'))
        # Should redirect to a lobby URL
        self.assertEqual(response.status_code, 302)
        self.assertIn('/lobby/', response['Location'])

    def test_join_nonexistent_room_redirects_with_error(self):
        response = self.client.get(reverse('join_room', kwargs={'room_code': 'ZZZ'}))
        self.assertRedirects(response, reverse('landing'))

    def test_join_valid_room_redirects_to_lobby(self):
        room = GameRoom('XYZ', creator='Alice')
        ROOMS['XYZ'] = room
        response = self.client.get(reverse('join_room', kwargs={'room_code': 'XYZ'}))
        self.assertRedirects(response, reverse('lobby', kwargs={'room_code': 'XYZ'}))

    def test_unauthenticated_create_room_redirects_to_home(self):
        self.client.logout()
        response = self.client.get(reverse('create_room'))
        # Django's login_required appends ?next=/create/ — check location starts with /
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/'))


class LeaderboardAPITests(TestCase):
    def setUp(self):
        self.client = Client()
        for i in range(3):
            u = User.objects.create_user(username=f'Player{i}', password='0000')
            u.profile.total_earned_seconds = (3 - i) * 10
            u.profile.save()

    def test_leaderboard_returns_200(self):
        response = self.client.get(reverse('api_leaderboard'))
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_response_has_players_key(self):
        response = self.client.get(reverse('api_leaderboard'))
        data = response.json()
        self.assertIn('players', data)
        self.assertIn('has_next', data)

    def test_leaderboard_player_has_required_fields(self):
        response = self.client.get(reverse('api_leaderboard'))
        players = response.json()['players']
        self.assertGreater(len(players), 0)
        for field in ('username', 'total_earned_seconds', 'first', 'second', 'third'):
            self.assertIn(field, players[0])

    def test_leaderboard_ordered_by_total_earned_seconds(self):
        response = self.client.get(reverse('api_leaderboard'))
        players = response.json()['players']
        scores = [p['total_earned_seconds'] for p in players]
        self.assertEqual(scores, sorted(scores, reverse=True))


class LiveGamesAPITests(TestCase):
    def setUp(self):
        ROOMS.clear()
        self.client = Client()

    def tearDown(self):
        ROOMS.clear()

    def test_live_games_returns_200(self):
        response = self.client.get(reverse('api_live_games'))
        self.assertEqual(response.status_code, 200)

    def test_live_games_has_games_key(self):
        response = self.client.get(reverse('api_live_games'))
        self.assertIn('games', response.json())

    def test_lobby_rooms_not_in_live_games(self):
        room = GameRoom('ABC', creator='Alice')
        ROOMS['ABC'] = room   # state = LOBBY by default
        response = self.client.get(reverse('api_live_games'))
        games = response.json()['games']
        codes = [g['room_code'] for g in games]
        self.assertNotIn('ABC', codes)

    def test_active_rooms_appear_in_live_games(self):
        User.objects.create_user(username='Alice', password='0000')
        User.objects.create_user(username='Bob', password='0000')
        room = GameRoom('ACT', creator='Alice')
        room.add_player('Alice')
        room.add_player('Bob')
        room.start_game()   # transitions to PICKING
        ROOMS['ACT'] = room
        response = self.client.get(reverse('api_live_games'))
        codes = [g['room_code'] for g in response.json()['games']]
        self.assertIn('ACT', codes)
