"""
Tests for GameRoom and PlayerState lifecycle:
- Room creation
- Adding / removing players
- Host transfer when creator leaves
- Room full guard
- Stale room cleanup
"""

from django.test import TestCase
from game.game_manager import (
    GameRoom, ROOMS, generate_room_code,
    cleanup_stale_rooms, LOBBY, GAME_OVER,
)
import time


class RoomCreationTests(TestCase):
    def setUp(self):
        ROOMS.clear()

    def tearDown(self):
        ROOMS.clear()

    def test_room_initialises_in_lobby(self):
        room = GameRoom('AAA', creator='Alice')
        self.assertEqual(room.state, LOBBY)
        self.assertEqual(room.creator, 'Alice')
        self.assertEqual(room.players, {})

    def test_generate_room_code_returns_three_letters(self):
        code = generate_room_code()
        self.assertEqual(len(code), 3)
        self.assertTrue(code.isalpha())
        self.assertTrue(code.isupper())

    def test_generate_room_code_is_unique(self):
        # A code is unique among open rooms, so each room is opened before the next code is made
        # (as create_room does). Without that, two random codes match about once in 400 runs.
        codes = set()
        for _ in range(10):
            code = generate_room_code()
            ROOMS[code] = GameRoom(code, creator='Alice')
            codes.add(code)
        self.assertEqual(len(codes), 10)


class PlayerAddRemoveTests(TestCase):
    def setUp(self):
        ROOMS.clear()
        self.room = GameRoom('BBB', creator='Alice')
        ROOMS['BBB'] = self.room

    def tearDown(self):
        ROOMS.clear()

    def test_add_player_success(self):
        ok, err = self.room.add_player('Alice')
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertIn('Alice', self.room.players)

    def test_add_same_player_twice_is_reconnect(self):
        self.room.add_player('Alice')
        self.room.players['Alice'].is_connected = False
        ok, err = self.room.add_player('Alice')
        self.assertTrue(ok)
        self.assertTrue(self.room.players['Alice'].is_connected)

    def test_room_full_at_ten_players(self):
        for i in range(10):
            self.room.add_player(f'Player{i}')
        ok, err = self.room.add_player('Extra')
        self.assertFalse(ok)
        self.assertIn('full', err.lower())

    def test_remove_player_from_lobby_deletes_entry(self):
        self.room.add_player('Alice')
        self.room.remove_player('Alice')
        self.assertNotIn('Alice', self.room.players)

    def test_creator_transfers_on_leave(self):
        self.room.add_player('Alice')
        self.room.add_player('Bob')
        self.room.remove_player('Alice')
        self.assertEqual(self.room.creator, 'Bob')

    def test_get_player_list_respects_join_order(self):
        self.room.add_player('Alice')
        self.room.add_player('Bob')
        self.room.add_player('Charlie')
        names = [p['username'] for p in self.room.get_player_list()]
        self.assertEqual(names, ['Alice', 'Bob', 'Charlie'])


class StaleRoomCleanupTests(TestCase):
    def setUp(self):
        ROOMS.clear()

    def tearDown(self):
        ROOMS.clear()

    def test_game_over_rooms_cleaned_after_10_minutes(self):
        room = GameRoom('CCC', creator='Alice')
        room.state = GAME_OVER
        room._game_over_time = time.time() - 601   # 10m01s ago
        ROOMS['CCC'] = room
        cleanup_stale_rooms()
        self.assertNotIn('CCC', ROOMS)

    def test_active_game_over_room_not_cleaned(self):
        room = GameRoom('DDD', creator='Alice')
        room.state = GAME_OVER
        room._game_over_time = time.time() - 60   # only 1 minute ago
        ROOMS['DDD'] = room
        cleanup_stale_rooms()
        self.assertIn('DDD', ROOMS)

    def test_inactive_room_cleaned_after_2_hours(self):
        room = GameRoom('EEE', creator='Alice')
        room.last_activity = time.time() - 7201   # 2h01s ago
        ROOMS['EEE'] = room
        cleanup_stale_rooms()
        self.assertNotIn('EEE', ROOMS)


class AwayFromLobbyTests(TestCase):
    """A dropped lobby socket (another app, a locked phone) keeps the seat until the game starts."""

    def setUp(self):
        self.room = GameRoom('AWY', creator='Alice')
        for name in ('Alice', 'Bob', 'Cara'):
            self.room.add_player(name)

    def test_away_player_keeps_their_seat_and_host(self):
        self.room.mark_away('Alice')
        self.assertIn('Alice', self.room.players)
        self.assertEqual(self.room.creator, 'Alice')
        self.assertFalse(self.room.players['Alice'].is_connected)

    def test_coming_back_clears_away_and_keeps_the_place(self):
        self.room.mark_away('Bob')
        self.room.add_player('Bob')
        self.assertTrue(self.room.players['Bob'].is_connected)
        self.assertIsNone(self.room.players['Bob'].away_since)
        self.assertEqual([p['username'] for p in self.room.get_player_list()], ['Alice', 'Bob', 'Cara'])

    def test_the_game_starts_with_whoever_is_here(self):
        self.room.mark_away('Cara')
        ok, _ = self.room.start_game()
        self.assertTrue(ok)
        self.assertNotIn('Cara', self.room.players)
        self.assertEqual(sorted(self.room.turn_order), ['Alice', 'Bob'])

    def test_starting_needs_two_players_here_and_drops_nobody_if_it_cant(self):
        self.room.mark_away('Bob')
        self.room.mark_away('Cara')
        ok, err = self.room.start_game()
        self.assertFalse(ok)
        self.assertEqual(self.room.state, LOBBY)
        self.assertEqual(len(self.room.players), 3)

    def test_host_passes_to_someone_who_is_here(self):
        self.room.mark_away('Bob')
        self.room.remove_player('Alice')
        self.assertEqual(self.room.creator, 'Cara')


class SocketCountTests(TestCase):
    """A player is away only once their last page has disconnected."""

    def setUp(self):
        self.room = GameRoom('TAB', creator='Alice')
        self.room.add_player('Alice')

    def test_closing_one_of_two_tabs_keeps_the_player_here(self):
        self.room.socket_opened('Alice', 'tab-1')
        self.room.socket_opened('Alice', 'tab-2')
        self.assertIsNone(self.room.socket_closed('Alice', 'tab-1'))
        self.assertTrue(self.room.players['Alice'].is_connected)

    def test_closing_the_last_socket_marks_the_player_away(self):
        self.room.socket_opened('Alice', 'tab-1')
        self.assertIsNotNone(self.room.socket_closed('Alice', 'tab-1'))
        self.assertFalse(self.room.players['Alice'].is_connected)

    def test_a_socket_from_before_play_again_changes_nothing(self):
        self.room.socket_opened('Alice', 'new-lobby-page')
        self.assertIsNone(self.room.socket_closed('Alice', 'old-game-page'))
        self.assertTrue(self.room.players['Alice'].is_connected)


class DropPlayerTests(TestCase):
    def test_a_dropped_player_is_out_with_no_time_and_ranks_last(self):
        room = GameRoom('DRP', creator='Alice')
        for name in ('Alice', 'Bob', 'Cara'):
            room.add_player(name)
        room.start_game()
        room.players['Alice'].time_bank = 20
        room.players['Cara'].time_bank = 60
        self.assertTrue(room.drop_player('Cara'))
        self.assertTrue(room.players['Cara'].is_eliminated)
        self.assertEqual(room.get_leaderboard()[-1]['username'], 'Cara')
        self.assertFalse(room.drop_player('Cara'))  # already out
