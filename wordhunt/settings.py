import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-insecure-key-change-in-production-abc123xyz'
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')

# DJANGO_ALLOWED_HOSTS (comma-separated, e.g. word-hunt-game.onrender.com) locks the Host header
# down; left unset, any host is accepted, as before.
ALLOWED_HOSTS = [h.strip() for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',') if h.strip()]
CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com', 'https://word-hunt-game.onrender.com']

INSTALLED_APPS = [
    'daphne',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'game',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'wordhunt.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'wordhunt.wsgi.application'
ASGI_APPLICATION = 'wordhunt.asgi.application'

# Channel Layers — InMemory (single-server, no external dependencies)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# Database — PostgreSQL on Render (env vars set), SQLite locally (for dummy testing)
if os.environ.get('DB_HOST'):
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME':     config('DB_NAME'),
            'USER':     config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST':     config('DB_HOST'),
            'PORT':     config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 60,
            'OPTIONS': {'sslmode': 'require'},
        }
    }
else:
    # Local only — dummy accounts, testing
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Sessions
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Security
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
# Browsers that have seen the site over HTTPS refuse plain HTTP to it for a month (Render is HTTPS-only).
SECURE_HSTS_SECONDS = 0 if DEBUG else 60 * 60 * 24 * 30

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Logging. With DEBUG off, Django's default mails request errors to ADMINS, and there are
# none, so a crashing page left no trace in Render's logs. Print them instead.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {'class': 'logging.StreamHandler'},
    },
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
        'game': {'handlers': ['console'], 'level': 'INFO'},
    },
}
