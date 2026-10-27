from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from game.game_manager import ROOMS
from . import ice


@login_required(login_url='/')
def ice_servers(request):
    """The ICE servers for a voice page.

    TURN credentials go only to a player in a room with voice right now, so nobody can fetch
    them to relay anything else through the free allowance. Everyone else gets STUN only.
    """
    room = ROOMS.get(request.GET.get('room', '').upper())
    in_voice_room = room is not None and not room.matchmade and request.user.username in room.players
    return JsonResponse({'iceServers': ice.ice_servers() if in_voice_room else ice.STUN})
