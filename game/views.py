"""
HTTP views for Word Hunt.
Handles landing page, room creation/joining, lobby, and game page rendering.
"""

from django.shortcuts import render, redirect
from django.http import JsonResponse
from .game_manager import ROOMS, GameRoom, generate_room_code


def landing(request):
    """Landing page — username entry + create/join room."""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        if not username:
            return render(request, 'game/landing.html', {'error': 'Please enter a username'})
        if len(username) > 15:
            return render(request, 'game/landing.html', {'error': 'Username must be 15 characters or less'})

        # Normalize: first letter uppercase, rest lowercase → "soo" = "Soo" = "SOO"
        username = username.capitalize()

        # Store username in session
        request.session['username'] = username

        action = request.POST.get('action')
        if action == 'create':
            return redirect('create_room')
        elif action == 'join':
            room_code = request.POST.get('room_code', '').strip().upper()
            if not room_code or len(room_code) != 3:
                return render(request, 'game/landing.html', {
                    'error': 'Please enter a valid 3-letter room code',
                    'username': username,
                })
            return redirect('join_room', room_code=room_code)

    context = {}
    # Check for session-stored errors from redirects
    if 'error' in request.session:
        context['error'] = request.session.pop('error')

    return render(request, 'game/landing.html', context)


def create_room(request):
    """Create a new game room and redirect to lobby."""
    username = request.session.get('username')
    if not username:
        return redirect('landing')

    room_code = generate_room_code()
    room = GameRoom(room_code, creator=username)
    ROOMS[room_code] = room

    return redirect('lobby', room_code=room_code)


def join_room(request, room_code):
    """Validate room code and redirect to lobby."""
    username = request.session.get('username')
    if not username:
        return redirect('landing')

    room_code = room_code.upper()
    if room_code not in ROOMS:
        request.session['error'] = f'Room "{room_code}" not found'
        return redirect('landing')

    room = ROOMS[room_code]
    if room.state != 'lobby':
        # Allow reconnection to in-progress game
        if username in room.players:
            return redirect('game_view', room_code=room_code)
        request.session['error'] = 'Game already in progress'
        return redirect('landing')

    if len(room.players) >= 5:
        request.session['error'] = 'Room is full (max 5 players)'
        return redirect('landing')

    # Check for duplicate username in this room
    if username in room.players and room.players[username].is_connected:
        request.session['error'] = f'"{username}" is already in the room. Pick a different name!'
        return redirect('landing')

    return redirect('lobby', room_code=room_code)


def lobby(request, room_code):
    """Lobby/waiting room page."""
    username = request.session.get('username')
    if not username:
        return redirect('landing')

    room_code = room_code.upper()
    if room_code not in ROOMS:
        return redirect('landing')

    room = ROOMS[room_code]

    return render(request, 'game/lobby.html', {
        'room_code': room_code,
        'username': username,
        'is_creator': username == room.creator,
    })


def game_view(request, room_code):
    """Main game board page."""
    username = request.session.get('username')
    if not username:
        return redirect('landing')

    room_code = room_code.upper()
    if room_code not in ROOMS:
        return redirect('landing')

    return render(request, 'game/game.html', {
        'room_code': room_code,
        'username': username,
    })
