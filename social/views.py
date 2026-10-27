"""The friends page, and the buttons that change friendships (there and on profiles)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.cache import cache
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts import names
from game.game_manager import LOBBY, ROOMS, GameRoom, generate_room_code
from . import notify, presence, rules
from .models import Block, FriendRequest

INVITES_PER_10_MIN = 10  # per player


def _back(request):
    """Back to the page the button was on (a profile), else to the friends page."""
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect('friends')


@login_required(login_url='/')
def friends_page(request):
    user = request.user
    if user.profile.is_guest:
        return render(request, 'social/friends.html', {'guest': True})
    return render(request, 'social/friends.html', {
        'friends': [{'user': f, 'status': presence.status(f.id)} for f in rules.friends_of(user)],
        'received': FriendRequest.objects.filter(to_user=user).select_related('from_user__profile').order_by('-created_at'),
        'sent': FriendRequest.objects.filter(from_user=user).select_related('to_user').order_by('-created_at'),
        'blocked': Block.objects.filter(blocker=user).select_related('blocked').order_by('blocked__username'),
    })


SENT_MESSAGES = {
    rules.SENT: (messages.SUCCESS, 'Friend request sent to {name}.'),
    rules.NOW_FRIENDS: (messages.SUCCESS, 'You and {name} are friends now.'),
    rules.ALREADY_SENT: (messages.INFO, 'You already asked {name}.'),
    rules.ALREADY_FRIENDS: (messages.INFO, 'You and {name} are already friends.'),
    rules.NOT_ALLOWED: (messages.ERROR, "You can't add {name}."),
    rules.TOO_MANY: (messages.ERROR, "That's enough friend requests for today. Try again tomorrow."),
}


@login_required(login_url='/')
@require_POST
def add_friend(request):
    name = names.tidy(request.POST.get('name', ''))
    other = User.objects.select_related('profile').filter(username__iexact=name).first() if name else None
    if other is None:
        messages.error(request, f'No player is called {name}.' if name else 'Type a name first.')
        return _back(request)

    outcome = rules.send_request(request.user, other)
    level, text = SENT_MESSAGES[outcome]
    messages.add_message(request, level, text.format(name=other.username))
    if outcome == rules.SENT:
        notify.tell(other, {'type': 'friend_request', 'from': request.user.username})
    elif outcome == rules.NOW_FRIENDS:
        notify.friends_changed(request.user, other)
    return _back(request)


# action in the URL -> (what it does, what the page says after)
ACTIONS = {
    'accept': (rules.accept, 'You and {name} are friends now.'),
    'decline': (rules.decline, 'Request from {name} declined.'),
    'cancel': (rules.cancel, 'Request to {name} cancelled.'),
    'remove': (rules.unfriend, '{name} is no longer your friend.'),
    'block': (rules.block, "{name} is blocked. Neither of you can reach the other."),
    'unblock': (rules.unblock, '{name} is unblocked.'),
}


@login_required(login_url='/')
@require_POST
def friend_action(request, action, username):
    if action not in ACTIONS:
        raise Http404
    other = User.objects.filter(username=username).first()
    if other is None:
        raise Http404
    change, text = ACTIONS[action]
    if change(request.user, other):
        messages.success(request, text.format(name=other.username))
        notify.friends_changed(request.user, other)
    return _back(request)


@login_required(login_url='/')
@require_POST
def invite(request, username):
    """Ask a friend who is online to play: in the lobby the inviter is in, or in a new room.

    From a lobby's invite list (with `room`), the answer is JSON for the list to show in place.
    From the friends page, the inviter goes to the new room's lobby to wait there.
    """
    user = request.user
    friend = User.objects.filter(username=username).first()
    if friend is None or not rules.are_friends(user, friend):  # a block ends a friendship, so this covers blocks
        raise Http404
    code = request.POST.get('room', '').upper()

    def answer(ok, message, room=None):
        if code:
            return JsonResponse({'ok': ok, 'message': message}, status=200 if ok else 400)
        if ok:
            return redirect('lobby', room_code=room.room_code)
        messages.error(request, message)
        return redirect('friends')

    status = presence.status(friend.id)
    if status == presence.IN_GAME:
        return answer(False, f'{friend.username} is in a game right now.')
    if status == presence.OFFLINE:
        return answer(False, f"{friend.username} isn't online right now.")
    key = f'invites:{user.id}'
    sent = cache.get(key, 0)
    if sent >= INVITES_PER_10_MIN:
        return answer(False, "That's a lot of invites. Give it a few minutes.")

    if code:
        room = ROOMS.get(code)
        if room is None or room.state != LOBBY or user.username not in room.players:
            return answer(False, 'Invite friends from the lobby you are in.')
    else:
        room = GameRoom(generate_room_code(), creator=user.username)
        ROOMS[room.room_code] = room

    cache.set(key, sent + 1, 10 * 60)
    notify.tell(friend, {'type': 'invite', 'from': user.username, 'from_id': user.id, 'room': room.room_code})
    return answer(True, f'Invited {friend.username}.', room)
