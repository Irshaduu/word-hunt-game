"""
Game State Manager for Word Hunt.
All game state is held in-memory (games are ephemeral).
Server is the authority on time — clients display countdown for UX only.
"""

import time
import random
import string
from .words import get_random_board


# Global registry of active rooms
ROOMS = {}


def cleanup_stale_rooms():
    """Remove rooms that have been in GAME_OVER for more than 10 minutes."""
    now = time.time()
    stale = [
        code for code, room in ROOMS.items()
        if room.state == GAME_OVER and hasattr(room, '_game_over_time') and now - room._game_over_time > 600
    ]
    for code in stale:
        del ROOMS[code]


def generate_room_code():
    """Generate a unique 3-letter room code."""
    cleanup_stale_rooms()
    for _ in range(100):
        code = ''.join(random.choices(string.ascii_uppercase, k=3))
        if code not in ROOMS:
            return code
    raise RuntimeError("Could not generate unique room code")


class PlayerState:
    def __init__(self, username):
        self.username = username
        self.time_bank = 100.0       # seconds
        self.words_found = 0         # total words successfully found
        self.is_eliminated = False
        self.found_current_word = False
        self.hunt_start_time = None  # server timestamp when hunt started for this player
        self.is_connected = True

    def to_dict(self):
        # Calculate effective time bank (subtract elapsed hunt time if active)
        effective_time = self.time_bank
        if self.hunt_start_time is not None:
            elapsed = time.time() - self.hunt_start_time
            effective_time = max(0, self.time_bank - elapsed)

        return {
            'username': self.username,
            'time_bank': round(effective_time, 1),
            'words_found': self.words_found,
            'is_eliminated': self.is_eliminated,
            'found_current_word': self.found_current_word,
            'is_connected': self.is_connected,
        }


# Game states
LOBBY = 'lobby'
PICKING = 'picking'
SHOWING = 'showing'
HUNTING = 'hunting'
ROUND_END = 'round_end'
GAME_OVER = 'game_over'


class GameRoom:
    """In-memory game state for a single room."""

    def __init__(self, room_code, creator):
        self.room_code = room_code
        self.creator = creator
        self.players = {}            # {username: PlayerState}
        self.player_order = []       # Join order (for lobby display)
        self.turn_order = []         # Randomized at game start
        self.current_turn_index = 0  # Index into turn_order
        self.board = []              # Current word board
        self.chosen_word = None      # Word picked this turn
        self.current_picker = None   # Username of current picker
        self.state = LOBBY
        self.show_start_time = None  # When the 3-sec popup started
        self.pick_start_time = None  # When picking phase started

    def add_player(self, username):
        """Add a player to the room. Returns (success, error_msg)."""
        if self.state == GAME_OVER:
            self.reset_to_lobby(username)

        if len(self.players) >= 5:
            return False, "Room is full (max 5 players)"
        if username in self.players:
            # Reconnecting player
            self.players[username].is_connected = True
            return True, None
        if self.state != LOBBY:
            return False, "Game already in progress"

        self.players[username] = PlayerState(username)
        self.player_order.append(username)
        return True, None

    def remove_player(self, username):
        """Handle player disconnect."""
        if username in self.players:
            if self.state == LOBBY:
                del self.players[username]
                if username in self.player_order:
                    self.player_order.remove(username)
                
                # If host leaves, assign to next joinee
                if username == self.creator:
                    if self.player_order:
                        self.creator = self.player_order[0]
                    else:
                        self.creator = None
            else:
                self.players[username].is_connected = False

    def get_player_list(self):
        """Get ordered list of player dicts for the lobby/game."""
        return [self.players[u].to_dict() for u in self.player_order if u in self.players]

    def get_active_player_count(self):
        """Count non-eliminated players."""
        return sum(1 for p in self.players.values() if not p.is_eliminated)

    def start_game(self):
        """Initialize the game — randomize turns, generate board."""
        if len(self.players) < 2:
            return False, "Need at least 2 players"

        # Randomize turn order
        self.turn_order = list(self.players.keys())
        random.shuffle(self.turn_order)

        # Generate the board
        self.board = get_random_board()

        # Set first picker
        self.current_turn_index = 0
        self.current_picker = self.turn_order[0]
        self.state = PICKING
        self.pick_start_time = time.time()

        return True, None

    def get_next_picker(self):
        """Find the next non-eliminated player in turn order."""
        total = len(self.turn_order)
        for i in range(1, total + 1):
            idx = (self.current_turn_index + i) % total
            candidate = self.turn_order[idx]
            if not self.players[candidate].is_eliminated:
                self.current_turn_index = idx
                return candidate
        return None  # Should not happen — game_over should trigger first

    def pick_word(self, username, word):
        """Player picks a word from the board. Returns (success, error_msg)."""
        if self.state != PICKING:
            return False, "Not in picking phase"
        if username != self.current_picker:
            return False, "Not your turn to pick"

        # Validate word is on the board
        board_words = [w['word'] for w in self.board]
        if word not in board_words:
            return False, "Word not on board"

        self.chosen_word = word
        self.state = SHOWING
        self.show_start_time = time.time()

        # Reset found status for all players
        for p in self.players.values():
            p.found_current_word = False

        return True, None

    def start_hunt(self):
        """Transition from SHOWING to HUNTING — start timers for all hunters."""
        self.state = HUNTING
        now = time.time()

        for username, player in self.players.items():
            if username != self.current_picker and not player.is_eliminated:
                player.hunt_start_time = now
                player.found_current_word = False

    def player_found_word(self, username, word):
        """
        A hunting player clicked a word. Validate and process.
        Returns (success, time_taken, error_msg).
        """
        if self.state != HUNTING:
            return False, 0, "Not in hunting phase"

        player = self.players.get(username)
        if not player:
            return False, 0, "Player not found"
        if player.is_eliminated:
            return False, 0, "You are eliminated"
        if username == self.current_picker:
            return False, 0, "You are the picker this round"
        if player.found_current_word:
            return False, 0, "You already found the word"
        if word != self.chosen_word:
            return False, 0, "Wrong word"

        # Calculate time taken
        now = time.time()
        elapsed = now - player.hunt_start_time
        player.time_bank -= elapsed
        player.hunt_start_time = None
        player.found_current_word = True
        player.words_found += 1

        # Clamp time bank
        if player.time_bank <= 0:
            player.time_bank = 0
            player.is_eliminated = True

        return True, round(elapsed, 1), None

    def check_round_complete(self):
        """Check if all hunters have found the word or are eliminated."""
        for username, player in self.players.items():
            if username == self.current_picker:
                continue
            if player.is_eliminated:
                continue
            if not player.found_current_word:
                return False
        return True

    def end_round(self):
        """
        End the current round. Deduct time from players who didn't find the word.
        Check eliminations. Returns list of newly eliminated players.
        """
        now = time.time()
        newly_eliminated = []

        for username, player in self.players.items():
            if username == self.current_picker:
                continue
            if player.is_eliminated:
                continue
            if not player.found_current_word and player.hunt_start_time is not None:
                # Player didn't find the word — deduct all elapsed time
                elapsed = now - player.hunt_start_time
                player.time_bank -= elapsed
                player.hunt_start_time = None

                if player.time_bank <= 0:
                    player.time_bank = 0
                    player.is_eliminated = True
                    newly_eliminated.append(username)

        self.state = ROUND_END
        return newly_eliminated

    def check_game_over(self):
        """
        Game is over when only 1 (or 0) non-eliminated players remain.
        Returns (is_over, winner_username_or_None).
        """
        active = [u for u, p in self.players.items() if not p.is_eliminated]
        if len(active) <= 1:
            winner = active[0] if active else None
            self.state = GAME_OVER
            self._game_over_time = time.time()
            return True, winner
        return False, None

    def advance_turn(self):
        """
        Advance to the next turn — get next picker, refresh board.
        Returns the new picker username.
        """
        next_picker = self.get_next_picker()
        if next_picker is None:
            self.state = GAME_OVER
            return None

        self.current_picker = next_picker
        self.chosen_word = None
        self.board = get_random_board()
        self.state = PICKING
        self.pick_start_time = time.time()

        return next_picker

    def get_game_state(self):
        """Get the full serializable game state for broadcast."""
        pick_time_remaining = 20
        if self.state == PICKING and self.pick_start_time:
            elapsed = time.time() - self.pick_start_time
            pick_time_remaining = max(0, 20 - elapsed)

        return {
            'state': self.state,
            'players': self.get_player_list(),
            'turn_order': self.turn_order,
            'current_picker': self.current_picker,
            'chosen_word': self.chosen_word if self.state in (SHOWING, HUNTING) else None,
            'board': self.board,
            'room_code': self.room_code,
            'creator': self.creator,
            'pick_time_remaining': pick_time_remaining,
        }

    def get_leaderboard(self):
        """Get final leaderboard sorted by time_bank (winner first), then words_found."""
        players = sorted(
            self.players.values(),
            key=lambda p: (-p.time_bank, -p.words_found)
        )
        return [
            {
                'username': p.username,
                'time_bank': round(p.time_bank, 1),
                'words_found': p.words_found,
                'is_eliminated': p.is_eliminated,
            }
            for p in players
        ]

    def reset_to_lobby(self, username):
        """Reset the room from GAME_OVER back to LOBBY state."""
        if self.state != LOBBY:
            self.state = LOBBY
            self.players = {}
            self.player_order = []
            self.creator = username
            self.board = []
            self.chosen_word = None
            self.current_picker = None
            self.turn_order = []
            self.current_turn_index = 0
            self.pick_start_time = None
            self.show_start_time = None
