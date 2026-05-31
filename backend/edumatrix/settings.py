"""
Django settings for edumatrix project.

REQUIRED ENVIRONMENT VARIABLES (Production):
- DJANGO_SECRET_KEY: Django secret key for cryptographic signing
- SUPABASE_DB_USER: Supabase database username
- SUPABASE_DB_PASSWORD: Supabase database password
- SUPABASE_DB_HOST: Supabase database host

OPTIONAL ENVIRONMENT VARIABLES:
- DJANGO_DEBUG: Enable debug mode (default: False)
- DJANGO_ALLOWED_HOSTS: Comma-separated list of allowed hosts (default: localhost,127.0.0.1)
- DJANGO_SECURE_COOKIES: Enable secure cookies (default: True in production, False in debug mode)
- DJANGO_X_FRAME_OPTIONS: X-Frame-Options header value (default: DENY)
- RESEND_API_KEY: Resend API key for transactional email delivery
- DJANGO_EMAIL_*: Optional SMTP settings if you explicitly choose SMTP delivery
- SUPABASE_DB_NAME: Database name (default: postgres)
- SUPABASE_DB_PORT: Database port (default: 6543)
- SUPABASE_URL: Supabase project URL used by Supabase Auth email OTP
- SUPABASE_ANON_KEY: Supabase anon key used by Supabase Auth email OTP
- SARVAM_API_KEY: Sarvam AI API key (default: empty string)
- GOOGLE_AI_API_KEY: Google AI API key (default: empty string)
"""

from pathlib import Path
import importlib.util
import os
import re
import sys
from django.core.exceptions import ImproperlyConfigured

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
if load_dotenv:
    load_dotenv(BASE_DIR / '.env')
else:
    env_file = BASE_DIR / '.env'
    if env_file.exists():
        for raw_line in env_file.read_text(encoding='utf-8').splitlines():
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

# Helper functions for environment variable parsing
def parse_bool(value):
    """Parse boolean value from environment variable string."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ('true', '1', 'yes', 'on')

def parse_hosts(value):
    """Parse comma-separated ALLOWED_HOSTS from environment variable."""
    if not value:
        return []
    return [host.strip() for host in value.split(',') if host.strip()]

def is_placeholder(value):
    """Treat empty/example values as missing for production checks."""
    if value is None:
        return True
    normalized = str(value).strip().lower()
    if not normalized:
        return True
    return normalized.startswith('your-') or normalized in {
        'change-me',
        'changeme',
        'placeholder',
        'example',
        'none',
        'null',
    }

# SECURITY WARNING: keep the secret key used in production secret!
# Set DJANGO_SECRET_KEY environment variable in production
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = parse_bool(os.getenv('DJANGO_DEBUG', 'False'))

DEFAULT_ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    'testserver',
    'edumatrix.tech',
    'www.edumatrix.tech',
]

DEFAULT_TUNNEL_HOSTS = [
    '.loca.lt',
    '.ngrok-free.app',
    '.ngrok.io',
    '.trycloudflare.com',
]

ALLOWED_HOSTS = parse_hosts(os.getenv('DJANGO_ALLOWED_HOSTS', ','.join(DEFAULT_ALLOWED_HOSTS)))
TUNNEL_HOSTS = parse_hosts(os.getenv('DJANGO_TUNNEL_HOSTS', ','.join(DEFAULT_TUNNEL_HOSTS)))

if parse_bool(os.getenv('DJANGO_ALLOW_ANY_HOST', 'False')):
    ALLOWED_HOSTS = ['*']
else:
    for tunnel_host in TUNNEL_HOSTS:
        if tunnel_host not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(tunnel_host)

# For testing purposes, always include testserver
if 'testserver' not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append('testserver')

# Trust ALL origins for CSRF — needed for localtunnel, ngrok, cloudflare tunnels, etc.
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:*',
    'http://127.0.0.1:*',
    'https://edumatrix.tech',
    'https://www.edumatrix.tech',
]
CSRF_TRUSTED_ORIGINS.extend(parse_hosts(os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', '')))

for tunnel_host in TUNNEL_HOSTS:
    if tunnel_host.startswith('.'):
        CSRF_TRUSTED_ORIGINS.extend([
            f'https://*{tunnel_host}',
            f'http://*{tunnel_host}',
        ])
    else:
        CSRF_TRUSTED_ORIGINS.extend([
            f'https://{tunnel_host}',
            f'http://{tunnel_host}',
        ])

# Proxy / Tunnel headers
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# Cookie settings for tunnel compatibility
SESSION_COOKIE_SAMESITE = 'Lax'
# Secure cookies: default to True in production (DEBUG=False), False in development (DEBUG=True)
# Can be explicitly overridden with DJANGO_SECURE_COOKIES environment variable
SECURE_COOKIES = parse_bool(os.getenv('DJANGO_SECURE_COOKIES')) if os.getenv('DJANGO_SECURE_COOKIES') is not None else (not DEBUG)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
DISABLE_CSRF_FOR_TUNNELS = parse_bool(os.getenv('DJANGO_DISABLE_CSRF_FOR_TUNNELS', 'False'))

# Production security defaults. Local development can keep these disabled by
# running with DJANGO_DEBUG=True or explicit env overrides.
SECURE_SSL_REDIRECT = parse_bool(os.getenv('DJANGO_SECURE_SSL_REDIRECT')) if os.getenv('DJANGO_SECURE_SSL_REDIRECT') is not None else (not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = parse_bool(os.getenv('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', 'False' if DEBUG else 'True'))
SECURE_HSTS_PRELOAD = parse_bool(os.getenv('DJANGO_SECURE_HSTS_PRELOAD', 'False' if DEBUG else 'True'))
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = os.getenv('DJANGO_SECURE_REFERRER_POLICY', 'same-origin')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'academics',
    'dashboard',
    'attendance',
    'assignments',
    'forum',
    'messaging',
    'quizzes',
]

AUTH_USER_MODEL = 'accounts.User'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/login/'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'edumatrix.middleware.TunnelAccessMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if importlib.util.find_spec('whitenoise'):
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
    WHITENOISE_AUTOREFRESH = DEBUG
    WHITENOISE_USE_FINDERS = DEBUG
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }

ROOT_URLCONF = 'edumatrix.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'edumatrix.wsgi.application'

RUNNING_TESTS = any(arg == 'test' for arg in sys.argv)
if RUNNING_TESTS:
    DATABASE_BACKEND = os.getenv('DJANGO_TEST_DATABASE_BACKEND', 'sqlite').lower()
    if DATABASE_BACKEND not in {'sqlite', 'supabase'}:
        raise ImproperlyConfigured('DJANGO_TEST_DATABASE_BACKEND must be either sqlite or supabase.')
    USE_SQLITE = DATABASE_BACKEND == 'sqlite'
else:
    DATABASE_BACKEND = 'supabase'
    USE_SQLITE = False
    if os.getenv('DJANGO_DATABASE_BACKEND', 'supabase').lower() != 'supabase' or parse_bool(os.getenv('DJANGO_USE_SQLITE', 'False')):
        raise ImproperlyConfigured('EduMatrix runtime is configured for Supabase only. Remove local SQLite overrides.')

if USE_SQLITE:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': os.getenv('DJANGO_TEST_SQLITE_NAME', ':memory:'),
        }
    }
else:
    required_database_env = [
        'SUPABASE_DB_USER',
        'SUPABASE_DB_PASSWORD',
        'SUPABASE_DB_HOST',
    ]
    missing_database_env = [name for name in required_database_env if not os.environ.get(name)]
    if missing_database_env:
        raise ImproperlyConfigured(
            'Supabase database settings are required: ' + ', '.join(missing_database_env)
        )

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('SUPABASE_DB_NAME', 'postgres'),
            'USER': os.environ.get('SUPABASE_DB_USER'),
            'PASSWORD': os.environ.get('SUPABASE_DB_PASSWORD'),
            'HOST': os.environ.get('SUPABASE_DB_HOST'),
            'PORT': os.getenv('SUPABASE_DB_PORT', '6543'),
            'CONN_MAX_AGE': int(os.getenv('DJANGO_DB_CONN_MAX_AGE', '60')),
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'sslmode': 'require',
                'connect_timeout': int(os.getenv('DJANGO_DB_CONNECT_TIMEOUT', '10')),
            },
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'edumatrix-runtime-cache',
        'TIMEOUT': int(os.getenv('DJANGO_CACHE_TIMEOUT', '300')),
    }
}

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

RESEND_API_KEY = os.getenv('RESEND_API_KEY', '')
RESEND_API_URL = os.getenv('RESEND_API_URL', 'https://api.resend.com/emails')
RESEND_EMAIL_BACKEND = 'accounts.email_backend.ResendEmailBackend'

EMAIL_BACKEND = os.getenv(
    'DJANGO_EMAIL_BACKEND',
    RESEND_EMAIL_BACKEND if RESEND_API_KEY else (
        'django.core.mail.backends.console.EmailBackend' if DEBUG else 'django.core.mail.backends.smtp.EmailBackend'
    )
)
EMAIL_HOST = os.getenv('DJANGO_EMAIL_HOST', '')
EMAIL_PORT = int(os.getenv('DJANGO_EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.getenv('DJANGO_EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('DJANGO_EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = parse_bool(os.getenv('DJANGO_EMAIL_USE_TLS', 'True'))
EMAIL_USE_SSL = parse_bool(os.getenv('DJANGO_EMAIL_USE_SSL', 'False'))
DEFAULT_FROM_EMAIL = os.getenv(
    'DJANGO_DEFAULT_FROM_EMAIL',
    'EduMatrix <support@edumatrix.tech>' if EMAIL_BACKEND == RESEND_EMAIL_BACKEND else 'EduMatrix <no-reply@edumatrix.local>'
)
PUBLIC_SITE_URL = os.getenv('DJANGO_PUBLIC_SITE_URL', 'https://edumatrix.tech' if not DEBUG else '').strip().rstrip('/')
if PUBLIC_SITE_URL and '://' not in PUBLIC_SITE_URL:
    PUBLIC_SITE_URL = f'https://{PUBLIC_SITE_URL}'
SUPABASE_EMAIL_REDIRECT_URL = os.getenv('SUPABASE_EMAIL_REDIRECT_URL', '').strip().rstrip('/')

def infer_supabase_url_from_db_config():
    user = os.getenv('SUPABASE_DB_USER', '')
    user_match = re.match(r'^postgres\.([a-z0-9]{20})$', user)
    if user_match:
        return f"https://{user_match.group(1)}.supabase.co"

    host = os.getenv('SUPABASE_DB_HOST', '')
    host_match = re.match(r'^db\.([^.]+)\.supabase\.co$', host)
    return f"https://{host_match.group(1)}.supabase.co" if host_match else ''

SUPABASE_URL = (os.getenv('SUPABASE_URL') or infer_supabase_url_from_db_config()).rstrip('/')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY') or os.getenv('SUPABASE_PUBLIC_ANON_KEY', '')
SUPABASE_AUTH_ENABLED = parse_bool(os.getenv('SUPABASE_AUTH_ENABLED', 'True'))
SUPABASE_OTP_TTL_MINUTES = int(os.getenv('SUPABASE_OTP_TTL_MINUTES', '60'))
SUPABASE_AUTH_MISSING = []
if SUPABASE_AUTH_ENABLED:
    if is_placeholder(SUPABASE_URL):
        SUPABASE_AUTH_MISSING.append('Supabase project URL')
    if is_placeholder(SUPABASE_ANON_KEY):
        SUPABASE_AUTH_MISSING.append('Supabase anon public key')
SUPABASE_AUTH_READY = SUPABASE_AUTH_ENABLED and not SUPABASE_AUTH_MISSING

# X-Frame-Options header (default: DENY for security)
X_FRAME_OPTIONS = os.getenv('DJANGO_X_FRAME_OPTIONS', 'DENY')

# --- AI API Keys ---
SARVAM_API_KEY = os.environ.get('SARVAM_API_KEY', '')
GOOGLE_AI_API_KEY = os.environ.get('GOOGLE_AI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')
