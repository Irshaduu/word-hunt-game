"""ICE servers: how two browsers find a way to send each other sound.

STUN (free: Google's and Cloudflare's) tells a phone its public address, and most pairs of
players then connect directly. Some networks, many mobile carriers among them, won't allow
that, and TURN relays the sound instead. That is Cloudflare's TURN, with short-lived
credentials made here, so the API token never reaches a browser
(CLOUDFLARE_TURN_KEY_ID / CLOUDFLARE_TURN_API_TOKEN). Without them voice still works
wherever direct connections do.
"""

import json
import logging
import time
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

STUN = [{'urls': ['stun:stun.l.google.com:19302', 'stun:stun.cloudflare.com:3478']}]
TTL_SECONDS = 4 * 60 * 60        # each credential lasts four hours...
REFRESH_SECONDS = 60 * 60        # ...and a new one is made every hour, so any game started gets 3+ hours
RETRY_SECONDS = 60               # after Cloudflare fails, STUN alone for a minute

_cache = {'servers': None, 'until': 0.0}


def configured():
    return bool(settings.CLOUDFLARE_TURN_KEY_ID and settings.CLOUDFLARE_TURN_API_TOKEN)


def ice_servers():
    """STUN, plus Cloudflare TURN once its keys are set. Cached: one request to Cloudflare an hour."""
    if not configured():
        return STUN
    now = time.time()
    if now >= _cache['until']:
        try:
            _cache['servers'] = STUN + _fetch_turn()
            _cache['until'] = now + REFRESH_SECONDS
        except Exception:
            logger.exception('Could not get TURN credentials from Cloudflare')
            _cache['servers'] = STUN
            _cache['until'] = now + RETRY_SECONDS
    return _cache['servers']


def _fetch_turn():
    request = urllib.request.Request(
        f'https://rtc.live.cloudflare.com/v1/turn/keys/{settings.CLOUDFLARE_TURN_KEY_ID}/credentials/generate-ice-servers',
        data=json.dumps({'ttl': TTL_SECONDS}).encode(),
        headers={
            'Authorization': f'Bearer {settings.CLOUDFLARE_TURN_API_TOKEN}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        servers = json.load(response)['iceServers']
    # Browsers block port 53, so those addresses would only time out (Cloudflare's advice).
    usable = []
    for server in servers:
        urls = [server['urls']] if isinstance(server['urls'], str) else server['urls']
        urls = [url for url in urls if ':53?' not in url and not url.endswith(':53')]
        if urls:
            usable.append({**server, 'urls': urls})
    return usable


def forget():
    """For tests: no cached credentials."""
    _cache.update(servers=None, until=0.0)
