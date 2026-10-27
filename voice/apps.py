from django.apps import AppConfig


class VoiceConfig(AppConfig):
    """Voice chat: game rooms peer to peer (WebRTC), voice rooms through Cloudflare's SFU."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'voice'
