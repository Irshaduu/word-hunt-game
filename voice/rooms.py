"""Voice rooms: open rooms of up to eight where people talk and chat (Phase 6).

Rooms live in memory (ROADMAP rule 4): a restart closes them, which is fine for a place people
drop into. Only reports are kept in Postgres (models.Report). The owner can mute, remove and
lock; everyone can report and block. People blocked with each other (either way) don't hear,
see or read each other, and nobody joins a room whose owner they're blocked with.

A reload or a dropped connection isn't leaving: an owner who leaves has OWNER_AWAY_SECONDS to
come back. After that the room goes to whoever has been there longest, or closes if it's empty.
"""

import secrets
import string
import time

MAX_MEMBERS = 8
NAME_LENGTH = 40
EMPTY_ROOM_SECONDS = 120  # a room made but never entered is cleared after this
OWNER_AWAY_SECONDS = 30   # an owner who left has this long to come back before the room passes on

ROOMS = {}  # room id -> VoiceRoom


class Member:
    def __init__(self, name, channel):
        self.name = name
        self.channel = channel        # their room socket
        self.session = None           # their Cloudflare SFU session, while their microphone is on
        self.track = None             # the name of the audio track they publish
        self.blocked = set()          # names in this room they're blocked with, either way
        self.joined_at = time.time()


class VoiceRoom:
    def __init__(self, room_id, name, owner):
        self.id = room_id
        self.name = name
        self.owner = owner
        self.members = {}             # name -> Member
        self.locked = False           # nobody new can come in
        self.removed = set()          # people the owner removed: they can't come back
        self.muted = set()            # people the owner muted: a new page of theirs is muted too
        self.owner_absences = 0       # how often its owner has left: names each absence
        self.created_at = time.time()

    def problem_joining(self, name):
        """Why `name` can't come in, or None."""
        if name in self.removed:
            return 'removed'
        if name in self.members:
            return None  # another page of theirs
        if self.locked and name != self.owner:
            return 'locked'
        if len(self.members) >= MAX_MEMBERS:
            return 'full'
        return None

    def join(self, name, channel, blocked):
        """In they come. `blocked`: names they're blocked with (social.models.Block, either way)."""
        member = Member(name, channel)
        member.blocked = set(blocked) & set(self.members)
        for other in member.blocked:
            self.members[other].blocked.add(name)
        self.members[name] = member  # a newer page of theirs replaces the older one
        return member

    def leave(self, name, channel):
        """Out they go. False if it was an older page of theirs closing, or they'd gone already."""
        member = self.members.get(name)
        if member is None or member.channel != channel:
            return False
        del self.members[name]
        for other in self.members.values():
            other.blocked.discard(name)
        if name == self.owner:
            self.owner_absences += 1
        return True

    def owner_gone(self, absence):
        """The owner's wait is over for this absence (see owner_absences). Unless they came back,
        or came back and left again (a newer absence, with its own wait), whoever has been here
        longest looks after the room now, or it closes if nobody's here. True if it changed hands."""
        if self.owner_absences != absence or self.owner in self.members:
            return False
        if not self.members:
            if ROOMS.get(self.id) is self:
                del ROOMS[self.id]
            return False
        self.owner = min(self.members.values(), key=lambda m: m.joined_at).name
        return True

    def block(self, a, b):
        """Two members blocked each other just now (social/rules.py block)."""
        if a in self.members and b in self.members:
            self.members[a].blocked.add(b)
            self.members[b].blocked.add(a)

    def can_hear(self, listener, speaker):
        member = self.members.get(listener)
        return member is not None and speaker not in member.blocked and speaker != listener


def create(name, owner):
    room_id = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    room = VoiceRoom(room_id, name.strip()[:NAME_LENGTH] or f"{owner}'s room", owner)
    ROOMS[room_id] = room
    return room


def listing():
    """Open rooms, busiest first. Clears rooms made but never entered (rooms people left close
    by themselves, VoiceRoom.owner_gone)."""
    now = time.time()
    for room_id, room in list(ROOMS.items()):
        if not room.members and not room.owner_absences and now - room.created_at > EMPTY_ROOM_SECONDS:
            del ROOMS[room_id]
    return sorted((r for r in ROOMS.values() if r.members), key=lambda r: (-len(r.members), r.created_at))
