"""Voice in game rooms: the server only introduces players and passes their messages along.

The sound goes browser to browser (WebRTC), or through Cloudflare's TURN relay when a direct
path isn't possible, and never through Render (ROADMAP rule 1). What passes through here is
small: each pair's offer and answer, and their network candidates.

Up to MAX_VOICES players talk in a room. Past four, each phone would upload its voice once
for every listener (a mesh); the 8-person voice rooms use Cloudflare's SFU instead (Phase 6).
Random matches have no voice: strangers. Two people who blocked each other never connect.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q

from game.consumers import get_username_from_scope, turn_away
from game.game_manager import ROOMS
from social.models import Block

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
