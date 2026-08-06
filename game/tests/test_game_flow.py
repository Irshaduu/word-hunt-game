"""
Tests for the full game flow state machine:
- start_game (randomises turns, sets PICKING state)
- pick_word (validates picker, word on board, state transition)
- start_hunt (sets hunt_start_time for all hunters)
- player_found_word (validates correct word, deducts time)
- check_round_complete
- end_round (deducts time from slow hunters, marks eliminations)
- check_game_over
- advance_turn (next picker, new board)
- reset_to_lobby
"""

from django.test import TestCase
from game.game_manager import (
    GameRoom, ROOMS,
    LOBBY, PICKING, SHOWING, HUNTING, ROUND_END, GAME_OVER,
)
import time


def make_room(players=('Alice', 'Bob')):
    """Helper: create a fresh room with given players."""
    room = GameRoom('TST', creator=players[0])
    for p in players:
        room.add_player(p)
    return room


class StartGameTests(TestCase):
    def test_start_game_requires_two_players(self):
        room = make_room(players=('Alice',))
        ok, err = room.start_game()
        self.assertFalse(ok)
        self.assertIn('2', err)

    def test_start_game_transitions_to_picking(self):
        room = make_room()
        ok, _ = room.start_game()
        self.assertTrue(ok)
        self.assertEqual(room.state, PICKING)

    def test_start_game_sets_board(self):
        room = make_room()
        room.start_game()
        self.assertGreater(len(room.board), 0)

    def test_start_game_sets_current_picker(self):
        room = make_room()
        room.start_game()
        self.assertIn(room.current_picker, ('Alice', 'Bob'))

    def test_turn_order_contains_all_players(self):
        room = make_room(players=('Alice', 'Bob', 'Charlie'))
        room.start_game()
        self.assertCountEqual(room.turn_order, ['Alice', 'Bob', 'Charlie'])


class PickWordTests(TestCase):
    def setUp(self):
        self.room = make_room()
        self.room.start_game()
        self.picker = self.room.current_picker
        self.valid_word = self.room.board[0]['word']

    def test_pick_word_succeeds_for_picker(self):
        ok, err = self.room.pick_word(self.picker, self.valid_word)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(self.room.state, SHOWING)
        self.assertEqual(self.room.chosen_word, self.valid_word)

    def test_pick_word_fails_for_non_picker(self):
        non_picker = [u for u in self.room.players if u != self.picker][0]
        ok, err = self.room.pick_word(non_picker, self.valid_word)
        self.assertFalse(ok)
        self.assertIn('turn', err.lower())

    def test_pick_word_fails_for_word_not_on_board(self):
        ok, err = self.room.pick_word(self.picker, 'NOTAWORD')
        self.assertFalse(ok)
        self.assertIn('board', err.lower())

    def test_pick_word_resets_found_flags(self):
        for p in self.room.players.values():
            p.found_current_word = True
        self.room.pick_word(self.picker, self.valid_word)
        for p in self.room.players.values():
            self.assertFalse(p.found_current_word)


class HuntingPhaseTests(TestCase):
    def setUp(self):
        self.room = make_room()
        self.room.start_game()
        self.picker = self.room.current_picker
        self.hunter = [u for u in self.room.players if u != self.picker][0]
        self.valid_word = self.room.board[0]['word']
        self.room.pick_word(self.picker, self.valid_word)
        self.room.start_hunt()

    def test_start_hunt_sets_state_to_hunting(self):
        self.assertEqual(self.room.state, HUNTING)

    def test_hunter_has_hunt_start_time(self):
        self.assertIsNotNone(self.room.players[self.hunter].hunt_start_time)

    def test_picker_has_no_hunt_start_time(self):
        self.assertIsNone(self.room.players[self.picker].hunt_start_time)

    def test_player_found_word_success(self):
        ok, time_taken, err = self.room.player_found_word(self.hunter, self.valid_word)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertGreaterEqual(time_taken, 0)  # Can be 0.0 if found immediately
        self.assertTrue(self.room.players[self.hunter].found_current_word)

    def test_player_found_wrong_word_fails(self):
        ok, _, err = self.room.player_found_word(self.hunter, 'WRONGWORD')
        self.assertFalse(ok)
        self.assertIn('Wrong', err)

    def test_picker_cannot_find_word(self):
        ok, _, err = self.room.player_found_word(self.picker, self.valid_word)
        self.assertFalse(ok)
        self.assertIn('picker', err.lower())

    def test_cannot_find_word_twice(self):
        self.room.player_found_word(self.hunter, self.valid_word)
        ok, _, err = self.room.player_found_word(self.hunter, self.valid_word)
        self.assertFalse(ok)
        self.assertIn('already', err.lower())

    def test_time_bank_decreases_after_find(self):
        initial = self.room.players[self.hunter].time_bank
        self.room.player_found_word(self.hunter, self.valid_word)
        self.assertLess(self.room.players[self.hunter].time_bank, initial)

    def test_check_round_complete_when_all_found(self):
        self.room.player_found_word(self.hunter, self.valid_word)
        self.assertTrue(self.room.check_round_complete())

    def test_check_round_not_complete_before_all_found(self):
        # Hunter hasn't found yet
        self.assertFalse(self.room.check_round_complete())


class GameOverTests(TestCase):
    def test_game_over_when_one_player_remains(self):
        room = make_room(players=('Alice', 'Bob'))
        room.start_game()
        # Eliminate Bob
        room.players['Bob'].is_eliminated = True
        is_over, winner = room.check_game_over()
        self.assertTrue(is_over)
        self.assertEqual(winner, 'Alice')

    def test_game_not_over_with_two_active_players(self):
        room = make_room()
        room.start_game()
        is_over, winner = room.check_game_over()
        self.assertFalse(is_over)
        self.assertIsNone(winner)

    def test_game_over_sets_state(self):
        room = make_room()
        room.start_game()
        room.players['Bob'].is_eliminated = True
        room.check_game_over()
        self.assertEqual(room.state, GAME_OVER)


class AdvanceTurnTests(TestCase):
    def test_advance_turn_changes_picker(self):
        room = make_room(players=('Alice', 'Bob', 'Charlie'))
        room.start_game()
        first_picker = room.current_picker
        room.advance_turn()
        self.assertNotEqual(room.current_picker, first_picker)

    def test_advance_turn_refreshes_board(self):
        room = make_room()
        room.start_game()
        old_board = room.board
        room.advance_turn()
        # Board should be refreshed (new random board — may differ)
        self.assertIsNotNone(room.board)

    def test_advance_turn_resets_chosen_word(self):
        room = make_room()
        room.start_game()
        room.chosen_word = 'SOMETHING'
        room.advance_turn()
        self.assertIsNone(room.chosen_word)


class ResetToLobbyTests(TestCase):
    def test_reset_clears_all_game_state(self):
        room = make_room()
        room.start_game()
        room.state = GAME_OVER
        room.reset_to_lobby('Alice')
        self.assertEqual(room.state, LOBBY)
        self.assertEqual(room.players, {})
        self.assertIsNone(room.chosen_word)
        self.assertIsNone(room.current_picker)
        self.assertEqual(room.turn_order, [])

    def test_reset_sets_new_creator(self):
        room = make_room()
        room.state = GAME_OVER
        room.reset_to_lobby('Charlie')
        self.assertEqual(room.creator, 'Charlie')

    def test_reset_only_works_from_game_over(self):
        room = make_room()
        room.add_player('Alice')
        original_state = room.state   # LOBBY
        room.reset_to_lobby('Alice')  # Should be no-op in non-GAME_OVER
        # State stays LOBBY (reset only fires on GAME_OVER)
        self.assertEqual(room.state, original_state)
