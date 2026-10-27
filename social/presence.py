"""Who is online, kept in memory only (ROADMAP rule 2: nothing touches Postgres on a timer).

A player is online while any page of theirs has /ws/me/ open (base.html opens it on every
page), and in a game while one of their game pages is open too. Their friends hear about
each change as it happens, over their own /ws/me/ sockets. A restart forgets everything here,
and the pages' sockets rebuild it as they reconnect.
"""

import asyncio

from channels.layers import get_channel_layer

from game.tasks import spawn

OFFLINE_GRACE_SECONDS = 10  # a page load closes one socket and opens the next

ONLINE, IN_GAME, OFFLINE = 'online', 'in_game', 'offline'

_sockets = {}    # user id -> open /ws/me/ sockets
_games = {}      # user id -> open game-page sockets
_online = set()  # user ids their friends have been told are online
_names = {}      # user id -> name, for the messages
_friends = {}    # user id -> friend ids: loaded when they connect, and again when friends change


def group(user_id):
    """The channel-layer group that reaches every open page of one player."""
    return f'user_{user_id}'


def status(user_id):
    if user_id not in _online:
        return OFFLINE
    return IN_GAME if _games.get(user_id) else ONLINE


def online_ids(user_ids):
    return {i for i in user_ids if i in _online}


def set_friends(user_id, name, friend_ids):
    _names[user_id] = name
    _friends[user_id] = set(friend_ids)


async def _tell_friends(user_id):
    layer = get_channel_layer()
    message = {'type': 'friend_status', 'name': _names.get(user_id, ''), 'status': status(user_id)}
    for friend_id in _friends.get(user_id, ()):
        await layer.group_send(group(friend_id), message)


async def connected(user_id):
    _sockets[user_id] = _sockets.get(user_id, 0) + 1
    if user_id not in _online:
        _online.add(user_id)
        await _tell_friends(user_id)


async def disconnected(user_id):
    _sockets[user_id] = max(0, _sockets.get(user_id, 0) - 1)
    if not _sockets[user_id]:
        spawn(_offline_if_still_gone(user_id))


async def _offline_if_still_gone(user_id):
    await asyncio.sleep(OFFLINE_GRACE_SECONDS)
    if _sockets.get(user_id) or user_id not in _online:
        return  # back on another page meanwhile
    _online.discard(user_id)
    _sockets.pop(user_id, None)
    await _tell_friends(user_id)
    # Nothing is kept about a player who has gone.
    _friends.pop(user_id, None)
    _names.pop(user_id, None)


async def entered_game(user_id):
    before = status(user_id)
    _games[user_id] = _games.get(user_id, 0) + 1
    if status(user_id) != before:
        await _tell_friends(user_id)


async def left_game(user_id):
    before = status(user_id)
    _games[user_id] = _games.get(user_id, 0) - 1
    if _games[user_id] <= 0:
        del _games[user_id]
    if status(user_id) != before:
        await _tell_friends(user_id)


def forget_everyone():
    """For tests: start from nobody online."""
    for store in (_sockets, _games, _online, _names, _friends):
        store.clear()
