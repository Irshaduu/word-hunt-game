import json
import logging
import secrets

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from game.game_manager import ROOMS
from social import rules
from . import ice, rooms, sfu
from .consumers import tell_everyone
from .models import Report

logger = logging.getLogger(__name__)

ROOMS_PER_HOUR = 5     # rooms a player can open
REPORTS_PER_HOUR = 5   # reports a player can make


@login_required(login_url='/')
def ice_servers(request):
    """The ICE servers for a voice page.

    TURN credentials go only to a player in a room with voice right now, so nobody can fetch
    them to relay anything else through the free allowance. Everyone else gets STUN only.
    """
    room = ROOMS.get(request.GET.get('room', '').upper())
    in_voice_room = room is not None and not room.matchmade and request.user.username in room.players
    return JsonResponse({'iceServers': ice.ice_servers() if in_voice_room else ice.STUN})


# --- Voice rooms ---

def _limited(user, action, limit):
    """Count one `action` by `user` this hour; True once that's more than `limit`."""
    key = f'{action}:{user.id}'
    done = cache.get(key, 0)
    if done >= limit:
        return True
    cache.set(key, done + 1, 60 * 60)
    return False


@login_required(login_url='/')
def rooms_page(request):
    """Open voice rooms, and a form to open one."""
    if request.user.profile.is_guest:
        return render(request, 'voice/rooms.html', {'guest': True})
    error = None
    if request.method == 'POST':
        if _limited(request.user, 'rooms-opened', ROOMS_PER_HOUR):
            error = "That's a lot of rooms. Try again in an hour."
        else:
            room = rooms.create(request.POST.get('name', ''), owner=request.user.username)
            return redirect('voice_room', room_id=room.id)
    return render(request, 'voice/rooms.html', {
        'rooms': rooms.listing(),
        'max_members': rooms.MAX_MEMBERS,
        'voice_ready': sfu.configured(),
        'error': error,
    })


@login_required(login_url='/')
def room_page(request, room_id):
    room = rooms.ROOMS.get(room_id)
    if room is None or request.user.profile.is_guest:
        return redirect('voice_rooms')
    return render(request, 'voice/room.html', {'room': room, 'voice_ready': sfu.configured()})


def _member(request, room_id):
    """The room and the requesting player's place in it, or 404 if they aren't in it."""
    room = rooms.ROOMS.get(room_id)
    member = room.members.get(request.user.username) if room else None
    if member is None:
        raise Http404
    return room, member


def _tell_room(room):
    async_to_sync(tell_everyone)(get_channel_layer(), room)


@login_required(login_url='/')
@require_POST
def sfu_publish(request, room_id):
    """The browser's microphone, published to the SFU. Answers with the SFU's side of it."""
    room, member = _member(request, room_id)
    if not sfu.configured():
        return JsonResponse({'error': "Voice in rooms isn't switched on yet."}, status=503)
    try:
        body = json.loads(request.body)
        track = f'{room.id}-{secrets.token_hex(4)}'
        session, answer = sfu.publish(body['sessionDescription'], body['mid'], track)
    except (sfu.SFUError, KeyError, ValueError):
        logger.exception('Could not publish to the SFU in room %s', room.id)
        return JsonResponse({'error': "Voice couldn't start. Try again."}, status=502)
    member.session, member.track = session, track
    _tell_room(room)  # everyone else now pulls the new track
    return JsonResponse({'sessionDescription': answer})


@login_required(login_url='/')
@require_POST
def sfu_pull(request, room_id):
    """Others' tracks, into the browser's session: only people it may hear."""
    room, member = _member(request, room_id)
    try:
        names = json.loads(request.body).get('names', [])
    except ValueError:
        names = []
    wanted = [room.members[n] for n in names
              if n in room.members and room.members[n].track and room.can_hear(member.name, n)]
    if not member.session or not wanted:
        return JsonResponse({'tracks': [], 'requiresImmediateRenegotiation': False})
    try:
        reply = sfu.pull(member.session, [(m.session, m.track) for m in wanted])
    except sfu.SFUError:
        logger.exception('Could not pull tracks in room %s', room.id)
        return JsonResponse({'error': "Couldn't connect to the others' voices."}, status=502)
    name_of = {m.track: m.name for m in wanted}
    return JsonResponse({
        'requiresImmediateRenegotiation': reply.get('requiresImmediateRenegotiation', False),
        'sessionDescription': reply.get('sessionDescription'),
        'tracks': [{'mid': t.get('mid'), 'name': name_of.get(t.get('trackName'))} for t in reply.get('tracks', [])],
    })


@login_required(login_url='/')
@require_POST
def sfu_renegotiate(request, room_id):
    room, member = _member(request, room_id)
    try:
        sfu.renegotiate(member.session, json.loads(request.body)['sessionDescription'])
    except (sfu.SFUError, KeyError, ValueError):
        logger.exception('Could not renegotiate in room %s', room.id)
        return JsonResponse({'error': "Couldn't connect to the others' voices."}, status=502)
    return JsonResponse({'ok': True})


@login_required(login_url='/')
@require_POST
def sfu_stop(request, room_id):
    """The player turned their microphone off: nobody pulls their track any more."""
    room, member = _member(request, room_id)
    member.session = member.track = None
    _tell_room(room)
    return JsonResponse({'ok': True})


@login_required(login_url='/')
@require_POST
def report(request, room_id, username):
    """Report someone in the room. Kept for the game's owner (python manage.py list_reports)."""
    room, _ = _member(request, room_id)
    reported = User.objects.filter(username=username).first()
    if reported is None or username not in room.members or reported == request.user:
        raise Http404
    if _limited(request.user, 'reports', REPORTS_PER_HOUR):
        return JsonResponse({'ok': False, 'message': "That's a lot of reports. Try again later."}, status=429)
    Report.objects.create(reporter=request.user, reported=reported, room_name=room.name,
                          reason=request.POST.get('reason', '').strip()[:300])
    return JsonResponse({'ok': True, 'message': f'Thanks. Your report about {username} was sent.'})


@login_required(login_url='/')
@require_POST
def block(request, room_id, username):
    """Block someone from inside a room: from now on neither of you hears, sees or reads the other."""
    room, _ = _member(request, room_id)
    other = User.objects.filter(username=username).first()
    if other is None or other == request.user:
        raise Http404
    rules.block(request.user, other)
    room.block(request.user.username, other.username)
    _tell_room(room)
    return JsonResponse({'ok': True, 'message': f'{username} is blocked.'})
