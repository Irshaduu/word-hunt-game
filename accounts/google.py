"""Sign in with Google: checking the credential Google hands the page.

The credential is an ID token: a JWT that Google signs with keys it publishes. A valid one was
signed by Google, was issued for this app (its audience is our client ID), hasn't expired, and
names one Google account ("sub", which never changes). Nothing else is trusted from the page.
"""

from urllib.parse import urlparse

import jwt
from django.conf import settings

CERTS_URL = 'https://www.googleapis.com/oauth2/v3/certs'
ISSUERS = ('accounts.google.com', 'https://accounts.google.com')

# Google rotates its signing keys every few days. The client caches them and fetches again
# when a token names a key it hasn't seen, so most sign-ins make no request to Google at all.
_keys = jwt.PyJWKClient(CERTS_URL, cache_keys=True, lifespan=6 * 60 * 60)


class InvalidCredential(Exception):
    pass


def verify(credential):
    """The credential's claims (sub, name, picture, ...) if Google signed it for this app."""
    if not settings.GOOGLE_CLIENT_ID:
        raise InvalidCredential('Google sign-in is not set up')
    try:
        key = _keys.get_signing_key_from_jwt(credential).key
        return jwt.decode(
            credential, key, algorithms=['RS256'],
            audience=settings.GOOGLE_CLIENT_ID, issuer=ISSUERS,
            options={'require': ['exp', 'iat', 'sub']},
            leeway=30,  # a server clock a little off from Google's
        )
    except jwt.PyJWTError as e:
        raise InvalidCredential(str(e)) from e


def picture_url(claims):
    """The account's picture, kept only if it is on Google's own CDN (it always is).

    Pages show it as-is, so this is what stops them loading anything else.
    """
    url = claims.get('picture', '')
    host = urlparse(url).hostname or ''
    if url.startswith('https://') and (host == 'googleusercontent.com' or host.endswith('.googleusercontent.com')):
        return url
    return ''
