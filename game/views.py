"""
HTTP views for Word Hunt.
Handles landing page, room creation/joining, lobby, and game page rendering.
"""

import secrets
from datetime import timedelta

from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.core.cache import cache
from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from accounts import names
from social import presence, rules
from social.models import FriendRequest
from .game_manager import ROOMS, GameRoom, generate_room_code
from .stats import global_rank

# One-tap demo accounts
GUEST_LIFETIME = timedelta(days=1)
DEMO_LIMIT_PER_HOUR = 10  # per address, so nobody can mint accounts in a loop

# Wrong PINs and new accounts, per address: a 4-character PIN is quick to guess,
# and every try costs a password hash on a 0.1-CPU server.
LOGIN_FAILS_PER_15_MIN = 10
SIGNUPS_PER_HOUR = 10

def landing(request):
    """Landing page — username entry + create/join room."""
    context = {}
    if 'error' in request.session:
        context['error'] = request.session.pop('error')
    if 'notice' in request.session:
        context['notice'] = request.session.pop('notice')

    if request.user.is_authenticated:
        # User is logged in, show profile stats and room actions
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'create':
                return redirect('create_room')
            elif action == 'join':
                room_code = request.POST.get('room_code', '').strip().upper()
                if not room_code or len(room_code) != 3:
                    context['error'] = 'Please enter a valid 3-letter room code'
                else:
                    return redirect('join_room', room_code=room_code)
        
        # Pass profile data
        profile = request.user.profile
        context['username'] = request.user.username
        context['total_earned_seconds'] = profile.total_earned_seconds
        context['first_places'] = profile.first_places
        context['second_places'] = profile.second_places
        context['third_places'] = profile.third_places
        context['fourth_places'] = profile.fourth_places
        context['fifth_places'] = profile.fifth_places
        context['avatar_url'] = profile.avatar_url
        context['global_rank'] = global_rank(request.user)
        context['friend_requests'] = FriendRequest.objects.filter(to_user=request.user).count()

        return render(request, 'game/landing_auth.html', context)
    else:
        # Guest, show login/register
        return render(request, 'game/landing.html', context)


def register_view(request):
    if request.method == 'POST':
        username = names.tidy(request.POST.get('username', ''))
        pin = request.POST.get('pin', '').strip()

        if _too_many(request, 'register', SIGNUPS_PER_HOUR):
            request.session['error'] = 'Too many new accounts from here. Try again in an hour.'
            return redirect('landing')

        if not pin or len(pin) > 4:
            request.session['error'] = 'PIN must be maximum 4 characters'
            return redirect('landing')

        # The same rules as a name chosen after Google sign-in (accounts/names.py).
        problem = names.problem_with(username)
        if problem:
            request.session['error'] = problem
            return redirect('landing')

        user = User.objects.create_user(username=username, password=pin)
        _count(request, 'register', 60 * 60)
        login(request, user)
        # Set session to not expire on browser close (stay logged in)
        request.session.set_expiry(60 * 60 * 24 * 365) # 1 year
        return redirect('landing')
    return redirect('landing')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip().capitalize()
        pin = request.POST.get('pin', '').strip()

        if _too_many(request, 'login', LOGIN_FAILS_PER_15_MIN):
            request.session['error'] = 'Too many wrong PINs. Try again in 15 minutes.'
            return redirect('landing')

        user = authenticate(request, username=username, password=pin)
        if user is not None:
            login(request, user)
            request.session.set_expiry(60 * 60 * 24 * 365) # 1 year
            return redirect('landing')
        else:
            _count(request, 'login', 15 * 60)
            request.session['error'] = 'Invalid username or PIN'
            return redirect('landing')
    return redirect('landing')


def logout_view(request):
    logout(request)
    return redirect('landing')


def _client_ip(request):
    # Behind the host's proxy the socket address is the proxy's; the first forwarded one is the visitor.
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return forwarded.split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')


def _too_many(request, action, limit):
    """Has this address done `action` `limit` times inside its current window?"""
    return cache.get(f'{action}:{_client_ip(request)}', 0) >= limit


def _count(request, action, seconds):
    key = f'{action}:{_client_ip(request)}'
    cache.set(key, cache.get(key, 0) + 1, seconds)


def _new_guest():
    """A throwaway account with no PIN: nobody can sign in to it again."""
    for _ in range(50):
        name = f'Guest{secrets.randbelow(10000):04d}'
        if not User.objects.filter(username=name).exists():
            break
    else:
        raise RuntimeError('No free guest name')
    user = User(username=name)
    user.set_unusable_password()
    user.save()
    user.profile.is_guest = True
    user.profile.save()
    return user


def demo_view(request):
    """One tap from the landing page into a practice game against Robo, no sign-up."""
    if request.method != 'POST':
        return redirect('landing')

    if not request.user.is_authenticated:
        if _too_many(request, 'demo', DEMO_LIMIT_PER_HOUR):
            request.session['error'] = 'Too many demo games from here. Try again in an hour.'
            return redirect('landing')
        _count(request, 'demo', 60 * 60)

        # Yesterday's guests go before today's is made, so they never pile up.
        User.objects.filter(profile__is_guest=True, date_joined__lt=timezone.now() - GUEST_LIFETIME).delete()
        login(request, _new_guest())
        request.session.set_expiry(int(GUEST_LIFETIME.total_seconds()))

    return redirect('practice_room')


@login_required(login_url='/')
def create_room(request):
    """Create a new game room and redirect to lobby."""
    username = request.user.username
    room_code = generate_room_code()
    room = GameRoom(room_code, creator=username)
    ROOMS[room_code] = room

    return redirect('lobby', room_code=room_code)


@login_required(login_url='/')
def practice_room(request):
    """A room with Robo already in it, so one person can play a real game."""
    room_code = generate_room_code()
    ROOMS[room_code] = GameRoom(room_code, creator=request.user.username, practice=True)
    return redirect('lobby', room_code=room_code)


@login_required(login_url='/')
def join_room(request, room_code):
    """Validate room code and redirect to lobby."""
    username = request.user.username
    room_code = room_code.upper()
    
    if room_code not in ROOMS:
        request.session['error'] = f'Room "{room_code}" not found'
        return redirect('landing')

    room = ROOMS[room_code]
    if room.state != 'lobby' and room.state != 'game_over':
        # Allow reconnection to in-progress game
        if username in room.players:
            return redirect('game_view', room_code=room_code)
        request.session['error'] = 'Game already in progress'
        return redirect('landing')

    if len(room.players) >= 10:
        request.session['error'] = 'Room is full (max 10 players)'
        return redirect('landing')

    # Check for duplicate username in this room (shouldn't happen with unique users unless logic error, but good to keep)
    if username in room.players and room.players[username].is_connected:
        # Since we use real accounts now, this means they might have 2 tabs open. Just redirect to lobby.
        return redirect('lobby', room_code=room_code)

    return redirect('lobby', room_code=room_code)


@login_required(login_url='/')
def lobby(request, room_code):
    """Lobby/waiting room page."""
    username = request.user.username
    room_code = room_code.upper()
    if room_code not in ROOMS:
        return redirect('landing')

    room = ROOMS[room_code]

    # Friends to invite, with their status kept current by social/me.js. Not for a random
    # match (it starts by itself), nor for demo guests (no friends).
    friends = []
    if not room.matchmade and not request.user.profile.is_guest:
        friends = [{'name': f.username, 'status': presence.status(f.id)} for f in rules.friends_of(request.user)]

    return render(request, 'game/lobby.html', {
        'room_code': room_code,
        'username': username,
        'is_creator': username == room.creator,
        'auto_start': bool(room.expected),
        'friends': friends,
    })


@login_required(login_url='/')
def random_match(request):
    """The page that waits in the random-match queue (game/matchmaking.py)."""
    return render(request, 'game/random.html')


@login_required(login_url='/')
def game_view(request, room_code):
    """Main game board page."""
    username = request.user.username
    room_code = room_code.upper()
    if room_code not in ROOMS:
        return redirect('landing')

    return render(request, 'game/game.html', {
        'room_code': room_code,
        'username': username,
    })


def api_leaderboard(request):
    """JSON endpoint for paginated global leaderboard."""
    users = (User.objects.select_related('profile').exclude(profile__is_guest=True)
             .order_by('-profile__total_earned_seconds', 'id'))
    paginator = Paginator(users, 25)
    page_num = request.GET.get('page', 1)
    page = paginator.get_page(page_num)

    data = []
    for u in page:
        if not hasattr(u, 'profile'):
            continue
        data.append({
            'username': u.username,
            'total_earned_seconds': u.profile.total_earned_seconds,
            'first': u.profile.first_places,
            'second': u.profile.second_places,
            'third': u.profile.third_places,
            'fourth': u.profile.fourth_places,
            'fifth': u.profile.fifth_places,
        })

    return JsonResponse({
        'players': data,
        'has_next': page.has_next(),
        'next_page_number': page.next_page_number() if page.has_next() else None
    })


def api_live_games(request):
    """JSON endpoint returning a list of currently active games."""
    live_games = []
    # States that mean the game is actively being played
    active_states = ['picking', 'showing', 'hunting', 'round_end']
    
    for code, room in list(ROOMS.items()):
        if room.state in active_states:
            live_games.append({
                'room_code': code,
                'state': room.state,
                'players_count': room.get_active_player_count(),
                'total_players': len(room.players),
            })
            
    return JsonResponse({'games': live_games})


@login_required(login_url='/')
def spectate_view(request, room_code):
    """View to spectate an active game."""
    username = request.user.username
    room_code = room_code.upper()
    
    if room_code not in ROOMS:
        request.session['error'] = f'Room "{room_code}" not found'
        return redirect('landing')
        
    # Check if they are actually a player in the game, if so just route them to game_view
    room = ROOMS[room_code]
    if username in room.players:
        return redirect('game_view', room_code=room_code)
        
    # Prevent spectating lobbies (they listen to the wrong WebSocket group)
    if room.state == 'lobby':
        return redirect('lobby', room_code=room_code)

    return render(request, 'game/game.html', {
        'room_code': room_code,
        'username': username,
        'is_spectator': True,
    })


def healthz(request):
    """For the uptime pinger: two bytes back, no session and no database.

    It runs around the clock, so a query here would keep the database awake all month.
    """
    return HttpResponse('ok', content_type='text/plain')
