"""
HTTP views for Word Hunt.
Handles landing page, room creation/joining, lobby, and game page rendering.
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .game_manager import ROOMS, GameRoom, generate_room_code

def landing(request):
    """Landing page — username entry + create/join room."""
    context = {}
    if 'error' in request.session:
        context['error'] = request.session.pop('error')

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
        
        # Calculate global rank
        global_rank = User.objects.filter(
            Q(profile__total_earned_seconds__gt=profile.total_earned_seconds) |
            Q(profile__total_earned_seconds=profile.total_earned_seconds, id__lt=request.user.id)
        ).count() + 1
        context['global_rank'] = global_rank
        
        return render(request, 'game/landing_auth.html', context)
    else:
        # Guest, show login/register
        return render(request, 'game/landing.html', context)


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip().capitalize()
        pin = request.POST.get('pin', '').strip()

        if not username or len(username) > 10:
            request.session['error'] = 'Username must be 1-10 characters'
            return redirect('landing')
        
        if not pin or len(pin) > 4:
            request.session['error'] = 'PIN must be maximum 4 characters'
            return redirect('landing')

        if User.objects.filter(username=username).exists():
            request.session['error'] = 'Username already taken'
            return redirect('landing')

        user = User.objects.create_user(username=username, password=pin)
        login(request, user)
        # Set session to not expire on browser close (stay logged in)
        request.session.set_expiry(60 * 60 * 24 * 365) # 1 year
        return redirect('landing')
    return redirect('landing')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip().capitalize()
        pin = request.POST.get('pin', '').strip()

        user = authenticate(request, username=username, password=pin)
        if user is not None:
            login(request, user)
            request.session.set_expiry(60 * 60 * 24 * 365) # 1 year
            return redirect('landing')
        else:
            request.session['error'] = 'Invalid username or PIN'
            return redirect('landing')
    return redirect('landing')


def logout_view(request):
    logout(request)
    return redirect('landing')


@login_required(login_url='/')
def create_room(request):
    """Create a new game room and redirect to lobby."""
    username = request.user.username
    room_code = generate_room_code()
    room = GameRoom(room_code, creator=username)
    ROOMS[room_code] = room

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

    return render(request, 'game/lobby.html', {
        'room_code': room_code,
        'username': username,
        'is_creator': username == room.creator,
    })


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
    users = User.objects.select_related('profile').order_by('-profile__total_earned_seconds', 'id')
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
