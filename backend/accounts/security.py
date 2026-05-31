from hashlib import sha256

from django.conf import settings
from django.core.cache import cache


DEFAULT_AUTH_RATE_LIMITS = {
    'login': {'limit': 5, 'window': 300},
    'signup': {'limit': 5, 'window': 1800},
    'password_change': {'limit': 5, 'window': 1800},
}


def get_client_ip(request):
    forwarded = (request.META.get('HTTP_X_FORWARDED_FOR') or '').split(',')
    if forwarded and forwarded[0].strip():
        return forwarded[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def get_rate_limit(scope):
    configured = getattr(settings, 'AUTH_RATE_LIMITS', {})
    defaults = DEFAULT_AUTH_RATE_LIMITS.get(scope, {'limit': 5, 'window': 300})
    scope_config = configured.get(scope, {})
    return {
        'limit': int(scope_config.get('limit', defaults['limit'])),
        'window': int(scope_config.get('window', defaults['window'])),
    }


def _build_key(scope, request, identity=''):
    client_ip = get_client_ip(request)
    digest = sha256((identity or '').strip().lower().encode('utf-8')).hexdigest()[:16] if identity else 'anonymous'
    return f'edumatrix-auth:{scope}:{client_ip}:{digest}'


def consume_auth_attempt(scope, request, identity=''):
    config = get_rate_limit(scope)
    key = _build_key(scope, request, identity)
    state = cache.get(key)
    if not state:
        cache.set(key, {'count': 1}, config['window'])
        return True, 0

    count = int(state.get('count', 0))
    if count >= config['limit']:
        return False, config['window']

    cache.set(key, {'count': count + 1}, config['window'])
    return True, 0


def reset_auth_attempts(scope, request, identity=''):
    cache.delete(_build_key(scope, request, identity))
