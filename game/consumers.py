"""
WebSocket consumers for Word Hunt.
LobbyConsumer — handles the waiting room before game starts.
GameConsumer — handles all in-game real-time communication.
"""

import json
import asyncio
import logging
import random
import time as time_mod
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import F
from .game_manager import (
    ROOMS, GameRoom, LOBBY, PICKING, SHOWING, HUNTING, ROUND_END, GAME_OVER,
    bot_pick_delay, bot_find_delay,
)
from .models import PlayerProfile

logger = logging.getLogger(__name__)

# How long a lobby seat is kept after its socket drops (another app, a locked phone).
LOBBY_GRACE_SECONDS = 120

# How long a player can be away from a game in progress before they're out of it.
GAME_GRACE_SECONDS = 30

# Close code for "this socket can't join, don't retry": the room is gone, full or already
# playing, or nobody is signed in. The page then opens /join/<code>/, which says which.
CLOSE_CANNOT_JOIN = 4004

# Places 1-5 of a finished game, as PlayerProfile counters.
PLACE_FIELDS = ['first_places', 'second_places', 'third_places', 'fourth_places', 'fifth_places']

# Timers and Robo's moves run as background tasks. The event loop keeps only a weak
# reference to a task, so hold one until it ends, and log whatever kills it.
_background_tasks = set()


def spawn(coro):
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_task_done)
    return task


def _task_done(task):
    _background_tasks.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error('Background task failed', exc_info=task.exception())


async def turn_away(consumer):
    """Refuse a socket so its page stops retrying: accept, then close with CLOSE_CANNOT_JOIN."""
    await consumer.accept()
    await consumer.close(code=CLOSE_CANNOT_JOIN)


def driver_for(room):
    """A GameConsumer with no socket, to move a room's game on from a timer.

    The turn loop's methods only use the channel layer and the room's group, so this is all
    they need (the tests build their consumers the same way).
    """
    driver = GameConsumer()
    driver.channel_layer = get_channel_layer()
    driver.room_code = room.room_code
    driver.group_name = f'game_{room.room_code}'
    driver.username = None
    return driver


async def drop_if_still_away(room, username, away_since):
    """A player away from a game in progress for longer than the grace is out of it."""
    await asyncio.sleep(GAME_GRACE_SECONDS)
    player = room.players.get(username)
    # away_since names the absence: a player who came back (and maybe went again since) is not this one.
    if (ROOMS.get(room.room_code) is not room or room.state in (LOBBY, GAME_OVER)
            or player is None or player.away_since != away_since):
        return
    if room.drop_player(username):
        await driver_for(room).after_drop(room, username)


@database_sync_to_async
def save_results(leaderboard):
    """Add a finished game to each player's stats.

    One UPDATE per player that adds inside the database (F), so two saves can't overwrite each other.
    """
    with transaction.atomic():
        for place, entry in enumerate(leaderboard):
            changes = {}
            if entry['time_bank'] > 0:
                changes['total_earned_seconds'] = F('total_earned_seconds') + int(entry['time_bank'])
            if place < len(PLACE_FIELDS):
                changes[PLACE_FIELDS[place]] = F(PLACE_FIELDS[place]) + 1
            if changes:
                PlayerProfile.objects.filter(user__username=entry['username']).update(**changes)


def get_username_from_scope(scope):
    """The signed-in user's name, from the session (AuthMiddlewareStack), or None.

    Never read from the query string: anyone can type a name into a URL.
    """
    user = scope.get('user')
    if user is not None and user.is_authenticated:
        return user.username
    return None


class LobbyConsumer(AsyncWebsocketConsumer):
    """Handles the lobby/waiting room WebSocket connections."""

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code'].upper()
        self.group_name = f'lobby_{self.room_code}'
        self.username = get_username_from_scope(self.scope)

        room = ROOMS.get(self.room_code)
        if self.username is None or room is None:
            await turn_away(self)
            return

        success, error = room.add_player(self.username)
        if not success:
            await turn_away(self)
            return
        room.socket_opened(self.username, self.channel_name)
        self.seated = True

        # Join channel group
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        if room.state != LOBBY:
            # Back after missing the start (their socket had dropped): straight on to the game.
            await self.send(text_data=json.dumps({
                'type': 'game_starting',
                'turn_order': room.turn_order,
            }))

        await self.broadcast_players(room)

    async def disconnect(self, close_code):
        if not getattr(self, 'seated', False):
            return  # turned away: never joined the room
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

        room = ROOMS.get(self.room_code)
        if room is None or getattr(self, 'left', False):
            return
        away_since = room.socket_closed(self.username, self.channel_name)
        if away_since is None:
            return  # still here on another page
        if room.state == LOBBY:
            # Another app or a locked phone: the seat is kept for a while, shown as away.
            spawn(self._free_seat_later(room, self.username, away_since))
            await self.broadcast_players(room)
        elif room.state != GAME_OVER:
            # Off to the game page, normally there within a second; if not, out after the grace.
            spawn(drop_if_still_away(room, self.username, away_since))

    async def _free_seat_later(self, room, username, away_since):
        """Give the seat up if its player hasn't come back from this absence within the grace."""
        await asyncio.sleep(LOBBY_GRACE_SECONDS)
        player = room.players.get(username)
        # away_since names the absence: a player who came back (and maybe left again since) is not this one.
        if (ROOMS.get(room.room_code) is not room or room.state != LOBBY
                or player is None or player.away_since != away_since):
            return
        room.remove_player(username)
        await self.after_leaving(room)

    async def after_leaving(self, room):
        """Someone gave their seat up: close the lobby once no person is left (Robo doesn't count)."""
        if room.state == LOBBY and room.human_count() == 0:
            if ROOMS.get(room.room_code) is room:
                del ROOMS[room.room_code]
            return
        await self.broadcast_players(room)

    async def broadcast_players(self, room):
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'player_update',
                'players': room.get_player_list(),
                'creator': room.creator,
            }
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type')

        if msg_type == 'leave':
            # The Leave button: give the seat up now, not after the grace.
            room = ROOMS.get(self.room_code)
            if room is not None:
                self.left = True
                room.remove_player(self.username)
                await self.after_leaving(room)
            return

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

        if self.username is None or self.room_code not in ROOMS:
            await turn_away(self)
            return

        room = ROOMS[self.room_code]
        
        if self.username not in room.players:
            self.role = 'spectator'
            room.spectators.add(self.username)
        else:
            self.role = 'player'
            room.socket_opened(self.username, self.channel_name)  # back in the game, if they'd dropped

        self.last_sound_time = 0

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        if self.role == 'spectator':
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'spectator_update',
                    'spectators': list(room.spectators),
                }
            )

        # Send current game state to the connecting player
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            **room.get_game_state(),
            'role': self.role,
        }))

        if room.state == PICKING and not getattr(room, 'pick_timer_started', False):
            room.pick_timer_started = True
            spawn(self._auto_pick_timer(room, room.pick_start_time, room.current_picker))
            self._schedule_bot_pick(room)

    async def disconnect(self, close_code):
        if hasattr(self, 'room_code') and self.room_code in ROOMS:
            room = ROOMS[self.room_code]
            if self.username in room.players:
                away_since = room.socket_closed(self.username, self.channel_name)
                if away_since is not None and room.state not in (LOBBY, GAME_OVER):
                    spawn(drop_if_still_away(room, self.username, away_since))
            elif getattr(self, 'role', None) == 'spectator':
                if self.username in room.spectators:
                    room.spectators.remove(self.username)
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'spectator_update',
                        'spectators': list(room.spectators),
                    }
                )

        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get('type')

        if self.room_code not in ROOMS:
            return

        room = ROOMS[self.room_code]
        
        # Spectators cannot send game commands
        if getattr(self, 'role', 'player') == 'spectator':
            return

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
        elif msg_type == 'play_sound':
            await self.handle_play_sound(data)
        elif msg_type == 'leave':
            # The Leave button: out now, as its dialog warns, rather than after the grace.
            if room.state not in (LOBBY, GAME_OVER) and room.drop_player(self.username):
                await self.after_drop(room, self.username)

    async def handle_play_sound(self, data):
        """Handle a player triggering a soundboard sound with rate limiting."""
        now = time_mod.time()
        # Enforce 2-second rate limit per connection
        if now - self.last_sound_time < 2.0:
            return
            
        self.last_sound_time = now
        sound = data.get('sound', '')
        if sound in ['airhorn', 'clap']:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'play_sound',
                    'sound': sound,
                    'sender': self.username,
                }
            )

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
        spawn(self._wait_and_start_hunt(room))

    async def _auto_pick_timer(self, room, pick_start_time, picker_username):
        await asyncio.sleep(20.0)
        if getattr(self, 'room_code', None) not in ROOMS:
            return
        if room.state == PICKING and room.pick_start_time == pick_start_time:
            await self._pick_for(room, picker_username)

    async def _pick_for(self, room, picker_username):
        """Pick a random board word for a picker who hasn't: an idle player, or Robo."""
        board_words = [w['word'] for w in room.board]
        if not board_words:
            return
        random_word = random.choice(board_words)
        success, error = room.pick_word(picker_username, random_word)
        if success:
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'word_picked',
                    'word': random_word,
                    'picker': picker_username,
                }
            )
            spawn(self._wait_and_start_hunt(room))

    def _schedule_bot_pick(self, room):
        if room.is_bot(room.current_picker):
            spawn(self._bot_pick(room, room.pick_start_time))

    async def _bot_pick(self, room, pick_start_time):
        """Robo's turn: look at the board for a moment, then pick."""
        await asyncio.sleep(bot_pick_delay())
        # pick_start_time names the turn, so a late wake-up never acts on a later one.
        if ROOMS.get(room.room_code) is room and room.state == PICKING and room.pick_start_time == pick_start_time:
            await self._pick_for(room, room.current_picker)

    async def _bot_hunt(self, room, bot_name, pick_start_time):
        """Robo hunts like a player: after a human-ish pause it finds the word."""
        await asyncio.sleep(bot_find_delay())
        if ROOMS.get(room.room_code) is room and room.state == HUNTING and room.pick_start_time == pick_start_time:
            await self._claim_found(room, bot_name, room.chosen_word)

    async def _wait_and_start_hunt(self, room):
        # Wait 6.0 seconds for the popup
        await asyncio.sleep(6.0)
        # The game can end meanwhile, when a player leaves and only one is left.
        if ROOMS.get(room.room_code) is not room or room.state != SHOWING:
            return

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

        for bot_name in room.bot_hunters():
            spawn(self._bot_hunt(room, bot_name, room.pick_start_time))

        # Start a background task to monitor time-outs
        spawn(self.monitor_timers(room))

    async def monitor_timers(self, room):
        """Background task to check if any player's time bank runs out during a hunt."""
        while room.state == HUNTING:
            await asyncio.sleep(0.5)

            if room.state != HUNTING:
                break

            # Check each hunting player's remaining time
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
        error = await self._claim_found(room, self.username, data.get('word', ''))
        if error:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': error,
            }))

    async def _claim_found(self, room, username, word):
        """A player (or Robo) found the word: score it and tell the room. Returns an error or None."""
        success, time_taken, error = room.player_found_word(username, word)
        if not success:
            return error

        # Check if this player was eliminated (time ran out right at the buzzer)
        player = room.players[username]

        # Broadcast: player found the word
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'player_found',
                'username': username,
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
                    'username': username,
                    'players': room.get_player_list(),
                }
            )

        # Check game over
        is_over, winner = room.check_game_over()
        if is_over:
            await self.broadcast_game_over(room, winner)
            return None

        # Check if round is now complete
        if room.check_round_complete():
            await self.finish_round(room)
        return None

    async def after_drop(self, room, username):
        """A player is out for leaving: tell the room, then move the game on if that settles anything."""
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'player_eliminated',
                'username': username,
                'players': room.get_player_list(),
                'reason': 'left',
            }
        )
        is_over, winner = room.check_game_over()
        if is_over:
            await self.broadcast_game_over(room, winner)
        elif room.state == PICKING and room.current_picker == username:
            await self._pick_for(room, username)  # nobody waits out a picker who is gone
        elif room.state == HUNTING and room.check_round_complete():
            await self.finish_round(room)

    async def finish_round(self, room):
        """End the current round, process eliminations, advance to next turn."""
        # A find and the timer loop can both see the round complete; only the first one ends it.
        if room.state != HUNTING:
            return
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

        room.pick_timer_started = True
        spawn(self._auto_pick_timer(room, room.pick_start_time, next_picker))
        self._schedule_bot_pick(room)

    async def broadcast_game_over(self, room, winner):
        """Broadcast the game over state with leaderboard."""
        room.state = GAME_OVER
        # Two paths can reach the end at once; the stats and the message go out once.
        if room.game_over_announced:
            return
        room.game_over_announced = True
        winner_time = 0
        if winner and winner in room.players:
            winner_time = round(room.players[winner].time_bank, 1)

        # Practice games against Robo never touch the global leaderboard.
        if winner and winner in room.players and not room.practice:
            try:
                await save_results(room.get_leaderboard())
            except Exception:
                # The game still ends for everyone; the log says whose results were lost.
                logger.exception('Could not save the results of room %s', room.room_code)

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
            'reason': event.get('reason', 'time'),  # 'left': gone too long, or pressed Leave
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
            'spectators': event.get('spectators', []),
            'turn_order': event['turn_order'],
            'current_picker': event['current_picker'],
            'chosen_word': event.get('chosen_word'),
            'board': event['board'],
            'room_code': event['room_code'],
            'creator': event['creator'],
            'pick_time_remaining': event.get('pick_time_remaining'),
        }))

    async def game_over(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_over',
            'winner': event['winner'],
            'time_remaining': event['time_remaining'],
            'leaderboard': event['leaderboard'],
        }))

    async def play_sound(self, event):
        await self.send(text_data=json.dumps({
            'type': 'play_sound',
            'sound': event['sound'],
            'sender': event['sender'],
        }))

    async def game_state(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_state',
            'state': event['state'],
            'players': event['players'],
            'spectators': event.get('spectators', []),
            'turn_order': event['turn_order'],
            'current_picker': event['current_picker'],
            'chosen_word': event.get('chosen_word'),
            'board': event['board'],
            'room_code': event['room_code'],
            'creator': event['creator'],
        }))

    async def spectator_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'spectator_update',
            'spectators': event['spectators'],
        }))
