"""Voice in game rooms: the server only introduces players and passes their messages along.

The sound goes browser to browser (WebRTC), or through Cloudflare's TURN relay when a direct
path isn't possible, and never through Render (ROADMAP rule 1). What passes through here is
small: each pair's offer and answer, and their network candidates.

Up to MAX_VOICES players talk in a room. Past four, each phone would upload its voice once
for every listener (a mesh); the 8-person voice rooms use Cloudflare's SFU instead (Phase 6).
Random matches have no voice: strangers. Two people who blocked each other never connect.
"""

import asyncio
import time

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q

from game.consumers import get_username_from_scope, turn_away
from game.game_manager import ROOMS
from game.models import PlayerProfile
from game.tasks import spawn
from social.models import Block
from . import rooms, sfu

MAX_VOICES = 4

# room code -> {name: channel name}: who is in that room's voice chat, and how to reach them.
VOICES = {}


@database_sync_to_async
def blocked_names(user, names):
    """Of `names`, those this user blocked or was blocked by."""
    pairs = Block.objects.filter(
        Q(blocker=user, blocked__username__in=names) | Q(blocked=user, blocker__username__in=names)
    ).values_list('blocker__username', 'blocked__username')
    return {name for pair in pairs for name in pair if name != user.username}


class VoiceConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        code = self.scope['url_route']['kwargs']['room_code'].upper()
        name = get_username_from_scope(self.scope)
        room = ROOMS.get(code)
        voices = VOICES.get(code, {})
        full = len(voices) >= MAX_VOICES and name not in voices
        if name is None or room is None or room.matchmade or name not in room.players or full:
            await turn_away(self)  # the page says voice isn't available here
            return

        self.code, self.name = code, name
        self.blocked = await blocked_names(self.scope['user'], list(voices))
        voices = VOICES.setdefault(code, {})
        voices[name] = self.channel_name  # from a new page (lobby to game), the newer socket wins
        await self.accept()

        # Those blocked either way are told nothing, and their sockets learn not to pass anything on.
        for peer in self.blocked:
            if peer in voices:
                await self.channel_layer.send(voices[peer], {'type': 'peer_blocked', 'name': name})
        # The newcomer calls everyone already talking; they wait for the call.
        peers = [peer for peer in voices if peer != name and peer not in self.blocked]
        await self.send_json({'type': 'peers', 'peers': peers})
        for peer in peers:
            await self.channel_layer.send(voices[peer], {'type': 'peer_joined', 'name': name})

    async def disconnect(self, code):
        if not hasattr(self, 'name'):
            return  # turned away
        voices = VOICES.get(self.code, {})
        if voices.get(self.name) != self.channel_name:
            return  # already replaced by a newer page of theirs
        del voices[self.name]
        if not voices:
            del VOICES[self.code]
        for peer, channel in voices.items():
            if peer not in self.blocked:
                await self.channel_layer.send(channel, {'type': 'peer_left', 'name': self.name})

    async def receive_json(self, content):
        kind = content.get('type')
        voices = VOICES.get(self.code, {})
        if kind == 'signal':
            to = content.get('to')
            if to in voices and to not in self.blocked:
                await self.channel_layer.send(voices[to], {
                    'type': 'signal', 'from': self.name, 'data': content.get('data'),
                })
        elif kind == 'mute':
            for peer, channel in voices.items():
                if peer != self.name and peer not in self.blocked:
                    await self.channel_layer.send(channel, {
                        'type': 'peer_muted', 'name': self.name, 'muted': bool(content.get('muted')),
                    })

    # Messages from the other players' sockets

    async def peer_joined(self, event):
        await self.send_json({'type': 'peer_joined', 'name': event['name']})

    async def peer_blocked(self, event):
        self.blocked.add(event['name'])  # for this socket only; the page never hears of it

    async def peer_left(self, event):
        await self.send_json({'type': 'peer_left', 'name': event['name']})

    async def signal(self, event):
        await self.send_json({'type': 'signal', 'from': event['from'], 'data': event['data']})

    async def peer_muted(self, event):
        await self.send_json({'type': 'peer_muted', 'name': event['name'], 'muted': event['muted']})


# --- Voice rooms (Phase 6): members, chat and the owner's tools; the sound goes through the SFU ---

CLOSE_REMOVED = 4003   # the owner removed this player; the page says so and doesn't retry
CHAT_LENGTH = 300
CHAT_GAP_SECONDS = 1   # one message a second per socket


@database_sync_to_async
def is_guest(user):
    return PlayerProfile.objects.filter(user_id=user.id, is_guest=True).exists()


class RoomConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        room = rooms.ROOMS.get(self.scope['url_route']['kwargs']['room_id'])
        if not user.is_authenticated or room is None or await is_guest(user):
            await turn_away(self)  # demo guests can't use rooms: strangers need someone to report
            return
        blocked = await blocked_names(user, list(room.members) + [room.owner])
        if room.problem_joining(user.username) or room.owner in blocked:
            await turn_away(self)
            return
        self.room, self.name = room, user.username
        self.last_chat = 0.0
        room.join(self.name, self.channel_name, blocked)
        await self.accept()
        await tell_everyone(self.channel_layer, room)

    async def disconnect(self, code):
        if not hasattr(self, 'room'):
            return  # turned away
        room = self.room
        if not room.leave(self.name, self.channel_name):
            return  # an older page of theirs
        if room.members:
            await tell_everyone(self.channel_layer, room)
        if self.name == room.owner:
            spawn(wait_for_owner(self.channel_layer, room, room.owner_absences))

    async def receive_json(self, content):
        room = self.room
        me = room.members.get(self.name)
        if me is None or me.channel != self.channel_name:
            return
        kind = content.get('type')
        if kind == 'chat':
            text = str(content.get('text', '')).strip()[:CHAT_LENGTH]
            now = time.monotonic()
            if not text or now - self.last_chat < CHAT_GAP_SECONDS:
                return
            self.last_chat = now
            for member in list(room.members.values()):
                if room.can_hear(member.name, self.name) or member.name == self.name:
                    await self.channel_layer.send(member.channel, {'type': 'chat_message', 'from': self.name, 'text': text})
        elif kind in ('mute', 'remove', 'lock') and self.name == room.owner:
            target = room.members.get(content.get('name'))
            if kind == 'lock':
                room.locked = bool(content.get('locked'))
            elif target is not None and target.name != self.name:
                if kind == 'mute':
                    if content.get('muted'):
                        room.muted.add(target.name)
                    else:
                        room.muted.discard(target.name)
                else:
                    room.removed.add(target.name)
                    await self.channel_layer.send(target.channel, {'type': 'removed'})
            await tell_everyone(self.channel_layer, room)

    # Messages for this socket

    async def room_state(self, event):
        """The room as this player sees it: people they're blocked with aren't in it."""
        room = self.room
        me = room.members.get(self.name)
        if me is None or me.channel != self.channel_name:
            return
        await self.send_json({
            'type': 'room',
            'name': room.name,
            'owner': room.owner,
            'locked': room.locked,
            'voice': sfu.configured(),
            'members': [  # the owner first, then in the order they came
                {'name': m.name, 'track': m.track, 'muted': m.name in room.muted}
                for m in sorted(room.members.values(), key=lambda m: m.name != room.owner)
                if m.name == self.name or room.can_hear(self.name, m.name)
            ],
        })

    async def chat_message(self, event):
        await self.send_json({'type': 'chat', 'from': event['from'], 'text': event['text']})

    async def removed(self, event):
        await self.send_json({'type': 'removed'})
        await self.close(code=CLOSE_REMOVED)


async def tell_everyone(layer, room):
    """Every member's socket sends its player the room as they see it."""
    for member in list(room.members.values()):
        await layer.send(member.channel, {'type': 'room_state'})


async def wait_for_owner(layer, room, absence):
    """A reload or a dropped connection isn't leaving: the owner has a while to come back."""
    await asyncio.sleep(rooms.OWNER_AWAY_SECONDS)
    if room.owner_gone(absence):
        await tell_everyone(layer, room)
