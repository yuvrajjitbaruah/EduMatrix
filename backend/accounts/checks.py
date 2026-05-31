from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def production_configuration_check(app_configs, **kwargs):
    issues = []
    using_console_email = settings.EMAIL_BACKEND.endswith('console.EmailBackend')
    using_smtp_email = settings.EMAIL_BACKEND.endswith('smtp.EmailBackend')
    using_resend_email = settings.EMAIL_BACKEND == getattr(settings, 'RESEND_EMAIL_BACKEND', '')
    resend_test_sender = '@resend.dev' in settings.DEFAULT_FROM_EMAIL.lower()

    if settings.SECRET_KEY == 'django-insecure-dev-key-change-in-production':
        issues.append(Error(
            'DJANGO_SECRET_KEY is using the development fallback.',
            hint='Generate a unique DJANGO_SECRET_KEY before production launch.',
            id='edumatrix.E001',
        ))

    if settings.EMAIL_BACKEND == getattr(settings, 'RESEND_EMAIL_BACKEND', '') and not settings.RESEND_API_KEY:
        issue_cls = Warning if settings.DEBUG else Error
        issues.append(issue_cls(
            'Resend signup email delivery is not ready.',
            hint='Set RESEND_API_KEY in the server environment so verification emails can be delivered.',
            id='edumatrix.E002' if not settings.DEBUG else 'edumatrix.W002',
        ))

    if not settings.DEBUG:
        if not settings.SESSION_COOKIE_SECURE or not settings.CSRF_COOKIE_SECURE:
            issues.append(Error(
                'Secure cookies are disabled while DJANGO_DEBUG is False.',
                hint='Set DJANGO_SECURE_COOKIES=True behind HTTPS.',
                id='edumatrix.E003',
            ))

        if using_console_email:
            issues.append(Error(
                'Console email backend is enabled while DJANGO_DEBUG is False.',
                hint='Use the Resend backend or configure SMTP before production launch.',
                id='edumatrix.E004',
            ))

        if using_smtp_email and not settings.EMAIL_HOST:
            issues.append(Error(
                'SMTP email is selected but DJANGO_EMAIL_HOST is empty.',
                hint='Configure SMTP so verification, welcome, and password reset emails can be delivered.',
                id='edumatrix.E005',
            ))

        if using_resend_email and not settings.RESEND_API_KEY:
            issues.append(Error(
                'Resend email delivery is selected but RESEND_API_KEY is empty.',
                hint='Add RESEND_API_KEY so verification, welcome, and password reset emails can be delivered.',
                id='edumatrix.E006',
            ))

        if using_resend_email and resend_test_sender:
            issues.append(Warning(
                'Resend is using the resend.dev testing sender.',
                hint='Verify your own sending domain in Resend and update DJANGO_DEFAULT_FROM_EMAIL before public launch.',
                id='edumatrix.W007',
            ))

        local_hosts = {'localhost', '127.0.0.1', 'testserver'}
        configured_hosts = set(settings.ALLOWED_HOSTS)
        if configured_hosts and configured_hosts.issubset(local_hosts):
            issues.append(Warning(
                'DJANGO_ALLOWED_HOSTS only contains local development hosts.',
                hint='Add the production domain before launch.',
                id='edumatrix.W008',
            ))

    return issues
