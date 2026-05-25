"""
WebSocket consumers for Word Hunt.
LobbyConsumer — handles the waiting room before game starts.
GameConsumer — handles all in-game real-time communication.
"""

import json
import asyncio
from urllib.parse import parse_qs
from channels.generic.websocket import AsyncWebsocketConsumer
from .game_manager import ROOMS, GameRoom, PICKING, SHOWING, HUNTING, ROUND_END, GAME_OVER


def get_username_from_scope(scope):
    """Extract username from WebSocket query string (?username=XXX)."""
    qs = parse_qs(scope.get('query_string', b'').decode('utf-8'))
    return qs.get('username', ['Anonymous'])[0]


class LobbyConsumer(AsyncWebsocketConsumer):
    """Handles the lobby/waiting room WebSocket connections."""

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code'].upper()
        self.group_name = f'lobby_{self.room_code}'
        self.username = get_username_from_scope(self.scope)

        # Validate room exists
        if self.room_code not in ROOMS:
            await self.close()
            return

        room = ROOMS[self.room_code]
        success, error = room.add_player(self.username)
        if not success:
            await self.close()
            return

        # Join channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Broadcast updated player list
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'player_update',
                'players': room.get_player_list(),
                'creator': room.creator,
            }
        )

    async def disconnect(self, close_code):
        if hasattr(self, 'room_code') and self.room_code in ROOMS:
            room = ROOMS[self.room_code]
            room.remove_player(self.username)

            # Broadcast updated player list
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'player_update',
                    'players': room.get_player_list(),
                    'creator': room.creator,
                }
            )

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type')

        if msg_type == 'start_game':
            if self.room_code not in ROOMS:
                return

            room = ROOMS[self.room_code]
            if self.username != room.creator:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': 'Only the room creator can start the game',
                }))
                return

            success, error = room.start_game()
            if not success:
                await self.send(text_data=json.dumps({
                    'type': 'error',
                    'message': error,
                }))
                return

            # Broadcast game starting to all lobby members
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'game_starting',
                    'turn_order': room.turn_order,
                }
            )

    # --- Group message handlers ---

    async def player_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_update',
            'players': event['players'],
            'creator': event['creator'],
        }))

    async def game_starting(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_starting',
            'turn_order': event['turn_order'],
        }))


class GameConsumer(AsyncWebsocketConsumer):
    """Handles all in-game WebSocket communication."""

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code'].upper()
        self.group_name = f'game_{self.room_code}'
        self.username = get_username_from_scope(self.scope)

        if self.room_code not in ROOMS:
            await self.close()
            return

        room = ROOMS[self.room_code]
        if self.username not in room.players:
            await self.close()
            return

        # Mark player as connected (handles reconnection)
        room.players[self.username].is_connected = True

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Send current game state to the connecting player
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            **room.get_game_state(),
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'room_code') and self.room_code in ROOMS:
            room = ROOMS[self.room_code]
            if self.username in room.players:
                player = room.players[self.username]
                player.is_connected = False

                if not player.is_eliminated and room.state != GAME_OVER:
                    player.is_eliminated = True
                    player.time_bank = 0

                    await self.channel_layer.group_send(
                        self.group_name,
                        {
                            'type': 'player_eliminated',
                            'username': self.username,
                            'players': room.get_player_list(),
                        }
                    )

                    is_over, winner = room.check_game_over()
                    if is_over:
                        await self.broadcast_game_over(room, winner)
                    else:
                        if room.state == PICKING and self.username == room.current_picker:
                            await self.finish_round(room)
                        elif room.state == HUNTING and room.check_round_complete():
                            await self.finish_round(room)

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type')

        if self.room_code not in ROOMS:
            return

        room = ROOMS[self.room_code]

        if msg_type == 'pick_word':
            await self.handle_pick_word(room, data)
        elif msg_type == 'found_word':
            await self.handle_found_word(room, data)
        elif msg_type == 'play_again':
            if hasattr(room, 'reset_to_lobby'):
                room.reset_to_lobby(self.username)
            await self.send(text_data=json.dumps({
                'type': 'redirect_to_lobby'
            }))

    async def handle_pick_word(self, room, data):
        """Handle a player picking a word from the board."""
        word = data.get('word', '')

        success, error = room.pick_word(self.username, word)
        if not success:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error,
            }))
            return

        # Broadcast: word was picked — show popup to all for 6 seconds
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'word_picked',
                'word': word,
                'picker': self.username,
            }
        )

        # Launch the countdown in the background so it doesn't block the picker's socket
        asyncio.ensure_future(self._wait_and_start_hunt(room))

    async def _wait_and_start_hunt(self, room):
        # Wait 6.0 seconds for the popup
        await asyncio.sleep(6.0)

        # Transition to hunting phase
        room.start_hunt()

        # Broadcast: hunt begins!
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'hunt_start',
                'players': room.get_player_list(),
            }
        )

        # Start a background task to monitor time-outs
        asyncio.ensure_future(self.monitor_timers(room))

    async def monitor_timers(self, room):
        """Background task to check if any player's time bank runs out during a hunt."""
        while room.state == HUNTING:
            await asyncio.sleep(0.5)

            if room.state != HUNTING:
                break

            # Check each hunting player's remaining time
            import time as time_mod
            now = time_mod.time()
            eliminations = []

            for username, player in room.players.items():
                if username == room.current_picker:
                    continue
                if player.is_eliminated or player.found_current_word:
                    continue
                if player.hunt_start_time is not None:
                    elapsed = now - player.hunt_start_time
                    remaining = player.time_bank - elapsed
                    if remaining <= 0:
                        # Eliminate this player
                        player.time_bank = 0
                        player.is_eliminated = True
                        player.hunt_start_time = None
                        eliminations.append(username)

            # Broadcast eliminations
            for uname in eliminations:
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'player_eliminated',
                        'username': uname,
                        'players': room.get_player_list(),
                    }
                )

            # Check if game is over
            is_over, winner = room.check_game_over()
            if is_over:
                await self.broadcast_game_over(room, winner)
                return

            # Check if round is complete (all found or eliminated)
            if room.check_round_complete():
                await self.finish_round(room)
                return

    async def handle_found_word(self, room, data):
        """Handle a player claiming they found the word."""
        word = data.get('word', '')

        success, time_taken, error = room.player_found_word(self.username, word)
        if not success:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error,
            }))
            return

        # Check if this player was eliminated (time ran out right at the buzzer)
        player = room.players[self.username]

        # Broadcast: player found the word
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'player_found',
                'username': self.username,
                'time_taken': time_taken,
                'words_found': player.words_found,
                'time_bank': round(player.time_bank, 1),
                'is_eliminated': player.is_eliminated,
                'players': room.get_player_list(),
            }
        )

        if player.is_eliminated:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'player_eliminated',
                    'username': self.username,
                    'players': room.get_player_list(),
                }
            )

        # Check game over
        is_over, winner = room.check_game_over()
        if is_over:
            await self.broadcast_game_over(room, winner)
            return

        # Check if round is now complete
        if room.check_round_complete():
            await self.finish_round(room)

    async def finish_round(self, room):
        """End the current round, process eliminations, advance to next turn."""
        newly_eliminated = room.end_round()

        # Broadcast eliminations
        for uname in newly_eliminated:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'player_eliminated',
                    'username': uname,
                    'players': room.get_player_list(),
                }
            )

        # Check game over
        is_over, winner = room.check_game_over()
        if is_over:
            await self.broadcast_game_over(room, winner)
            return

        # Broadcast round end
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'round_end',
                'players': room.get_player_list(),
            }
        )

        # Short pause before next turn
        await asyncio.sleep(0.5)

        # Advance to next turn
        next_picker = room.advance_turn()
        if next_picker is None:
            is_over, winner = room.check_game_over()
            await self.broadcast_game_over(room, winner)
            return

        # Broadcast new game state (new board, new picker)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'new_turn',
                **room.get_game_state(),
            }
        )

    async def broadcast_game_over(self, room, winner):
        """Broadcast the game over state with leaderboard."""
        room.state = GAME_OVER
        winner_time = 0
        if winner and winner in room.players:
            winner_time = round(room.players[winner].time_bank, 1)

            # Increment total_earned_seconds in DB
            from channels.db import database_sync_to_async
            from django.contrib.auth.models import User
            
            @database_sync_to_async
            def update_winner_stats(username, time_left):
                try:
                    user = User.objects.get(username=username)
                    user.profile.total_earned_seconds += int(time_left)
                    user.profile.save()
                except (User.DoesNotExist, Exception):
                    pass
            
            await update_winner_stats(winner, winner_time)

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'game_over',
                'winner': winner,
                'time_remaining': winner_time,
                'leaderboard': room.get_leaderboard(),
            }
        )

    # --- Group message handlers ---

    async def word_picked(self, event):
        await self.send(text_data=json.dumps({
            'type': 'word_picked',
            'word': event['word'],
            'picker': event['picker'],
        }))

    async def hunt_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'hunt_start',
            'players': event['players'],
        }))

    async def player_found(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_found',
            'username': event['username'],
            'time_taken': event['time_taken'],
            'words_found': event['words_found'],
            'time_bank': event['time_bank'],
            'is_eliminated': event['is_eliminated'],
            'players': event['players'],
        }))

    async def player_eliminated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'player_eliminated',
            'username': event['username'],
            'players': event['players'],
        }))

    async def round_end(self, event):
        await self.send(text_data=json.dumps({
            'type': 'round_end',
            'players': event['players'],
        }))

    async def new_turn(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_turn',
            'state': event['state'],
            'players': event['players'],
            'turn_order': event['turn_order'],
            'current_picker': event['current_picker'],
            'chosen_word': event.get('chosen_word'),
            'board': event['board'],
            'room_code': event['room_code'],
            'creator': event['creator'],
        }))

    async def game_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'time_remaining': event['time_remaining'],
            'leaderboard': event['leaderboard'],
        }))

    async def game_state(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'state': event['state'],
            'players': event['players'],
            'turn_order': event['turn_order'],
            'current_picker': event['current_picker'],
            'chosen_word': event.get('chosen_word'),
            'board': event['board'],
            'room_code': event['room_code'],
            'creator': event['creator'],
        }))
