"""Random matches: an in-memory queue that puts 2-4 waiting players into a room of their own.

The queue lives in memory (ROADMAP rule 2). The only Postgres read is the blocks among the
players about to be matched, once per match, so two people who blocked each other never meet.
With few players online the queue is often empty, so the waiting page offers a game against
Robo after a while (templates/game/random.html).
"""

import asyncio

from channels.db import database_sync_to_async
from channels.layers import get_channel_layer

from social.models import Block
from .game_manager import GameRoom, LOBBY, ROOMS, generate_room_code
from .tasks import spawn

MATCH_SIZE = 4        # players in a match, at most
GATHER_SECONDS = 4    # once two are waiting, how long to wait for more to join them
ARRIVE_SECONDS = 20   # how long a new match waits in its lobby for everyone to arrive

_waiting = {}         # user id -> (name, the channel of the page that asked); oldest first
_gathering = False


def is_waiting(user_id):
    return user_id in _waiting


async def join(user_id, name, channel_name):
    """Into the queue. Asking again from another page keeps the player's place."""
    global _gathering
    _waiting[user_id] = (name, channel_name)
    if len(_waiting) >= MATCH_SIZE:
        await make_matches()
    elif len(_waiting) >= 2 and not _gathering:
        _gathering = True
        spawn(_gather())


def leave(user_id, channel_name=None):
    """Out of the queue. A page that closes only gives up a place it asked for itself."""
    entry = _waiting.get(user_id)
    if entry is not None and (channel_name is None or entry[1] == channel_name):
        del _waiting[user_id]


async def _gather():
    global _gathering
    try:
        await asyncio.sleep(GATHER_SECONDS)
        await make_matches()
    finally:
        _gathering = False


@database_sync_to_async
def _blocked_pairs(user_ids):
    pairs = Block.objects.filter(blocker_id__in=user_ids, blocked_id__in=user_ids).values_list('blocker_id', 'blocked_id')
    return {frozenset(pair) for pair in pairs}


async def make_matches():
    """Put everyone waiting, oldest first, into matches of up to MATCH_SIZE."""
    if len(_waiting) < 2:
        return
    candidates = list(_waiting)
    blocked = await _blocked_pairs(candidates)
    layer = get_channel_layer()
    while True:
        group = []
        for user_id in candidates:
            if user_id in _waiting and len(group) < MATCH_SIZE and all(
                    frozenset((user_id, other)) not in blocked for other in group):
                group.append(user_id)
        if len(group) < 2:
            return  # whoever is left waits for someone they can play with
        entries = [_waiting.pop(user_id) for user_id in group]
        room = new_match_room([name for name, _ in entries])
        for _, channel in entries:
            await layer.send(channel, {'type': 'match_found', 'room': room.room_code})


def new_match_room(names):
    """A lobby for a new random match. It starts once all of `names` are in it (consumers.py)."""
    room = GameRoom(generate_room_code(), creator=names[0], matchmade=True)
    room.expected = set(names)
    ROOMS[room.room_code] = room
    spawn(_start_or_close(room))
    return room


async def start_match(room):
    """Start a random match with whoever is here. False if fewer than two are."""
    room.expected = set()  # started, or given up on: either way only once
    ok, _ = room.start_game()
    if ok:
        await get_channel_layer().group_send(f'lobby_{room.room_code}', {
            'type': 'game_starting',
            'turn_order': room.turn_order,
        })
    return ok


async def _start_or_close(room):
    """If not everyone arrived in time: start with those who did, or close the room."""
    await asyncio.sleep(ARRIVE_SECONDS)
    if ROOMS.get(room.room_code) is not room or room.state != LOBBY or not room.expected:
        return  # started already, or gone
    if not await start_match(room):
        await get_channel_layer().group_send(f'lobby_{room.room_code}', {'type': 'match_cancelled'})
        del ROOMS[room.room_code]


def forget_everyone():
    """For tests: an empty queue."""
    global _gathering
    _waiting.clear()
    _gathering = False
