"""
Tests for the game staying steady when something fails:
- a finished game's places and leftover seconds are added inside the database
- a failed save is logged, and the game still ends for everyone
- a background timer that crashes is logged, not lost
"""

import asyncio
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TransactionTestCase

from game.consumers import spawn
from game.game_manager import ROOMS, GameRoom
from game.models import PlayerProfile
from game.tests.test_practice import consumer_for


class ResultsTests(TransactionTestCase):
    # TransactionTestCase: save_results runs through database_sync_to_async, which closes
    # connections that a TestCase transaction would still be using.
    def setUp(self):
        ROOMS.clear()
        self.room = GameRoom('RES', creator='Asha')
        self.room.add_player('Asha')
        self.room.add_player('Ben')
        self.room.start_game()
        self.room.players['Asha'].time_bank = 42.6
        self.room.players['Ben'].time_bank = 0
        self.room.players['Ben'].is_eliminated = True

    def tearDown(self):
        ROOMS.clear()

    async def test_places_and_seconds_are_added_to_the_stats(self):
        asha = await User.objects.acreate(username='Asha')
        ben = await User.objects.acreate(username='Ben')
        await PlayerProfile.objects.filter(user=asha).aupdate(first_places=3, total_earned_seconds=100)

        await consumer_for(self.room).broadcast_game_over(self.room, 'Asha')

        asha_stats = await PlayerProfile.objects.aget(user=asha)
        ben_stats = await PlayerProfile.objects.aget(user=ben)
        self.assertEqual((asha_stats.first_places, asha_stats.total_earned_seconds), (4, 142))
        self.assertEqual((ben_stats.second_places, ben_stats.total_earned_seconds), (1, 0))

    async def test_a_failed_save_is_logged_and_the_game_still_ends(self):
        consumer = consumer_for(self.room)
        with mock.patch('game.consumers.save_results', side_effect=RuntimeError('database asleep')):
            with self.assertLogs('game.consumers', level='ERROR'):
                await consumer.broadcast_game_over(self.room, 'Asha')
        self.assertEqual([m['type'] for m in consumer.channel_layer.sent], ['game_over'])


class BackgroundTaskTests(SimpleTestCase):
    async def test_a_crashed_timer_is_logged(self):
        async def crash():
            raise RuntimeError('timer broke')

        with self.assertLogs('game.consumers', level='ERROR') as logs:
            await asyncio.gather(spawn(crash()), return_exceptions=True)
            await asyncio.sleep(0)  # let the task's done-callback run
        self.assertIsInstance(logs.records[0].exc_info[1], RuntimeError)
