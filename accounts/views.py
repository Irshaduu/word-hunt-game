"""Sign in with Google, choosing a game name, profiles, and the privacy page."""

from collections import defaultdict

from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from game.models import MatchPlayer, PlayerProfile
from game.stats import global_rank
from social import presence, rules
from social.models import Block
from . import google, names

ONE_YEAR = 60 * 60 * 24 * 365
PENDING = 'google_pending'  # session key: a checked Google account that has no player yet
RECENT_GAMES = 20


def _sign_in(request, user):
    login(request, user)
    request.session.set_expiry(ONE_YEAR)  # stay signed in, as with a PIN


@require_POST
def google_sign_in(request):
    """The Google button posts its credential here; the answer says where the page goes next."""
    try:
        claims = google.verify(request.POST.get('credential', ''))
    except google.InvalidCredential:
        return JsonResponse({'error': 'Google sign-in failed. Please try again.'}, status=400)
    picture = google.picture_url(claims)

    profile = PlayerProfile.objects.select_related('user').filter(google_sub=claims['sub']).first()
    if profile is not None:
        # A returning player. Their Google picture may have changed since.
        if picture and picture != profile.avatar_url:
            profile.avatar_url = picture
            profile.save(update_fields=['avatar_url'])
        _sign_in(request, profile.user)
        return JsonResponse({'next': reverse('landing')})

    user = request.user
    if user.is_authenticated and not user.profile.is_guest:
        # A PIN player linking Google from their profile; from now on either way works.
        if user.profile.google_sub:
            return JsonResponse({'error': 'This account is linked to a different Google account.'}, status=400)
        user.profile.google_sub = claims['sub']
        user.profile.avatar_url = picture
        user.profile.save(update_fields=['google_sub', 'avatar_url'])
        return JsonResponse({'next': reverse('my_profile')})

    # Someone new: they choose the name they'll play under next.
    request.session[PENDING] = {
        'sub': claims['sub'],
        'picture': picture,
        'name': claims.get('given_name') or claims.get('name', ''),
    }
    return JsonResponse({'next': reverse('choose_name')})


def choose_name(request):
    """Someone new from Google picks their game name, and their account is made."""
    pending = request.session.get(PENDING)
    if not pending:
        return redirect('landing')

    name, error = '', None
    if request.method == 'POST':
        name = names.tidy(request.POST.get('username', ''))
        error = names.problem_with(name)
        if error is None:
            user = _player_for(pending, name)
            if user is None:
                error = 'That name is taken'  # by someone else, a moment ago
            else:
                del request.session[PENDING]
                _sign_in(request, user)
                return redirect('landing')

    return render(request, 'accounts/choose_name.html', {
        'name': name or names.suggest(pending['name']),
        'picture': pending['picture'],
        'error': error,
    })


def _player_for(pending, name):
    """The player for this Google account: made now with `name`, or already made in another tab.

    None if the name was taken between checking it and saving it.
    """
    existing = PlayerProfile.objects.select_related('user').filter(google_sub=pending['sub']).first()
    if existing is not None:
        return existing.user
    user = User(username=name)
    user.set_unusable_password()  # Google is their way in
    try:
        with transaction.atomic():
            user.save()  # makes their profile too (signals in game/models.py)
    except IntegrityError:
        return None
    user.profile.google_sub = pending['sub']
    user.profile.avatar_url = pending['picture']
    user.profile.save(update_fields=['google_sub', 'avatar_url'])
    return user


def _ordinal(n):
    return {1: '1st', 2: '2nd', 3: '3rd'}.get(n, f'{n}th')


def _profile_page(request, user, is_me, **extra):
    """A player's profile: their numbers and their last games, with whom."""
    results = list(
        MatchPlayer.objects.filter(user=user).select_related('match').order_by('-match__ended_at')[:RECENT_GAMES]
    )
    # Everyone else in those games, in one query.
    others = defaultdict(list)
    for other in (MatchPlayer.objects.filter(match_id__in=[r.match_id for r in results])
                  .exclude(user=user).select_related('user').order_by('place')):
        others[other.match_id].append(other.user.username)

    profile = user.profile
    return render(request, 'accounts/profile.html', {
        'player': user,
        'profile': profile,
        'is_me': is_me,
        'rank': None if profile.is_guest else global_rank(user),
        'games_played': MatchPlayer.objects.filter(user=user).count(),
        'places': [profile.first_places, profile.second_places, profile.third_places,
                   profile.fourth_places, profile.fifth_places],
        'games': [{
            'ended_at': r.match.ended_at,
            'place': r.place,
            'place_label': _ordinal(r.place),
            'of': len(others[r.match_id]) + 1,
            'words_found': r.words_found,
            'seconds_left': r.seconds_left,
            'others': others[r.match_id],
        } for r in results],
        **extra,
    })


@login_required(login_url='/')
def my_profile(request):
    return _profile_page(request, request.user, is_me=True)


@login_required(login_url='/')
def profile(request, username):
    user = get_object_or_404(User.objects.select_related('profile'), username=username)
    if user == request.user:
        return redirect('my_profile')
    if Block.objects.filter(blocker=user, blocked=request.user).exists():
        raise Http404  # someone who blocked you is nowhere to be found
    return _profile_page(request, user, is_me=False,
                         relationship=rules.relationship(request.user, user),
                         status=presence.status(user.id))


@login_required(login_url='/')
@require_POST
def delete_account(request):
    """Deletes the player and everything kept about them: stats, games and sign-in."""
    if request.POST.get('confirm') != 'yes':
        return redirect('my_profile')
    user = request.user
    logout(request)
    user.delete()
    request.session['notice'] = 'Your account and everything kept about it are deleted.'
    return redirect('landing')


def privacy(request):
    return render(request, 'accounts/privacy.html')
