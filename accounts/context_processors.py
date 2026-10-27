from django.conf import settings


def sign_in(request):
    """Lets any template show the Google button, once GOOGLE_CLIENT_ID is set."""
    return {'GOOGLE_CLIENT_ID': settings.GOOGLE_CLIENT_ID}
