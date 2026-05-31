"""
Custom middleware for EduMatrix.
"""

from django.conf import settings


class TunnelAccessMiddleware:
    """
    Middleware hook for tunnel/proxy compatibility.

    CSRF is preserved by default; allowed tunnel hosts are handled in settings.py.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG and settings.DISABLE_CSRF_FOR_TUNNELS:
            request._dont_enforce_csrf_checks = True
        response = self.get_response(request)
        return response
