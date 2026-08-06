"""
Tests for PlayerState:
- Initial values
- to_dict() structure and fields
- Effective time bank during active hunt
- Elimination at zero time
"""

from django.test import TestCase
from game.game_manager import PlayerState
import time


class PlayerStateInitTests(TestCase):
    def setUp(self):
        self.player = PlayerState('Alice')

    def test_initial_time_bank_is_100(self):
        self.assertEqual(self.player.time_bank, 100.0)

    def test_initial_words_found_is_zero(self):
        self.assertEqual(self.player.words_found, 0)

    def test_not_eliminated_on_creation(self):
        self.assertFalse(self.player.is_eliminated)

    def test_is_connected_on_creation(self):
        self.assertTrue(self.player.is_connected)

    def test_no_hunt_start_time_initially(self):
        self.assertIsNone(self.player.hunt_start_time)


class PlayerStateToDictTests(TestCase):
    def setUp(self):
        self.player = PlayerState('Bob')

    def test_to_dict_contains_required_keys(self):
        d = self.player.to_dict()
        for key in ('username', 'time_bank', 'words_found',
                    'is_eliminated', 'found_current_word', 'is_connected'):
            self.assertIn(key, d)

    def test_to_dict_username(self):
        self.assertEqual(self.player.to_dict()['username'], 'Bob')

    def test_to_dict_time_bank_rounded_to_1dp(self):
        self.player.time_bank = 99.999
        d = self.player.to_dict()
        # Should be rounded to 1 decimal place
        self.assertEqual(d['time_bank'], round(99.999, 1))

    def test_to_dict_effective_time_during_hunt(self):
        """When hunt_start_time is set, to_dict() returns remaining time, not raw bank."""
        self.player.time_bank = 50.0
        self.player.hunt_start_time = time.time() - 5.0  # 5 seconds elapsed
        d = self.player.to_dict()
        # Effective time should be approx 45 seconds
        self.assertAlmostEqual(d['time_bank'], 45.0, delta=0.5)

    def test_to_dict_clamps_at_zero_during_hunt(self):
        """Effective time can never go below 0."""
        self.player.time_bank = 1.0
        self.player.hunt_start_time = time.time() - 10.0  # Way over time
        d = self.player.to_dict()
        self.assertEqual(d['time_bank'], 0)


class PlayerStateEliminationTests(TestCase):
    def test_player_can_be_eliminated(self):
        player = PlayerState('Charlie')
        player.is_eliminated = True
        self.assertTrue(player.is_eliminated)

    def test_time_bank_can_reach_zero(self):
        player = PlayerState('Dave')
        player.time_bank = 0
        self.assertEqual(player.time_bank, 0)

    def test_words_found_increments(self):
        player = PlayerState('Eve')
        player.words_found += 1
        player.words_found += 1
        self.assertEqual(player.words_found, 2)
