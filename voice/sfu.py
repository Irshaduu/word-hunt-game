"""Cloudflare Realtime SFU, for the voice rooms of up to eight.

An SFU takes one audio stream from each person and forwards it to the others, so a phone
uploads its voice once however many listen (a peer-to-peer mesh would upload it once per
listener). The server makes these calls, so the app secret never reaches a browser
(CLOUDFLARE_SFU_APP_ID / CLOUDFLARE_SFU_APP_SECRET). Without them rooms are text-only.

The flow, per person: a session with their microphone published as one track (publish), then
the others' tracks pulled into it (pull), answering the SFU's offer (renegotiate).
"""

import json
import urllib.error
import urllib.request

from django.conf import settings

BASE_URL = 'https://rtc.live.cloudflare.com/v1/apps'


class SFUError(Exception):
    pass


def configured():
    return bool(settings.CLOUDFLARE_SFU_APP_ID and settings.CLOUDFLARE_SFU_APP_SECRET)


def _call(method, path, body=None):
    request = urllib.request.Request(
        f'{BASE_URL}/{settings.CLOUDFLARE_SFU_APP_ID}{path}',
        data=None if body is None else json.dumps(body).encode(),
        headers={
            'Authorization': f'Bearer {settings.CLOUDFLARE_SFU_APP_SECRET}',
            'Content-Type': 'application/json',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise SFUError(f'{method} {path}: {e}') from e
    if data.get('errorCode'):
        raise SFUError(f"{method} {path}: {data['errorCode']} {data.get('errorDescription', '')}")
    return data


def _track_errors(data):
    errors = [t for t in data.get('tracks', []) if t.get('errorCode')]
    if errors:
        raise SFUError(f"track: {errors[0]['errorCode']} {errors[0].get('errorDescription', '')}")


def publish(offer, mid, track_name):
    """A new session with the browser's microphone published as `track_name`.

    Returns (session id, the SFU's answer for the browser).
    """
    session_id = _call('POST', '/sessions/new')['sessionId']
    data = _call('POST', f'/sessions/{session_id}/tracks/new', {
        'sessionDescription': offer,
        'tracks': [{'location': 'local', 'mid': mid, 'trackName': track_name}],
    })
    _track_errors(data)
    return session_id, data['sessionDescription']


def pull(session_id, remote_tracks):
    """Pull others' tracks, [(their session id, their track name)], into this session.

    Returns the SFU's reply: requiresImmediateRenegotiation, an offer, and each track's mid.
    """
    data = _call('POST', f'/sessions/{session_id}/tracks/new', {
        'tracks': [{'location': 'remote', 'sessionId': s, 'trackName': t} for s, t in remote_tracks],
    })
    _track_errors(data)
    return data


def renegotiate(session_id, answer):
    """The browser's answer to the SFU's offer from pull()."""
    _call('PUT', f'/sessions/{session_id}/renegotiate', {'sessionDescription': answer})
