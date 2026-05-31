"""
Preservation Property Tests for Supabase Security Fixes

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

This test verifies that non-sensitive configuration settings remain UNCHANGED
after the security fix is applied. These tests run on UNFIXED code to establish
the baseline behavior that must be preserved.

CRITICAL: These tests MUST PASS on unfixed code - passing confirms the baseline
behavior that the fix must preserve. After the fix is implemented, these tests
should continue to PASS, validating that non-sensitive configuration is unchanged.
"""

import os
import sys
from pathlib import Path
from importlib import import_module, reload
import importlib.util


def load_settings_module():
    """
    Dynamically load the settings module to inspect its configuration.
    This allows us to test the actual settings values.
    """
    settings_path = Path(__file__).parent / 'settings.py'
    spec = importlib.util.spec_from_file_location("settings", settings_path)
    settings = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(settings)
    return settings


def test_preservation_csrf_trusted_origins():
    """
    Property 2: Preservation - CSRF_TRUSTED_ORIGINS Unchanged
    
    **Validates: Requirement 3.1**
    
    This test verifies that CSRF_TRUSTED_ORIGINS configuration for tunnel
    compatibility (localtunnel, ngrok, cloudflare) remains unchanged.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    # Expected tunnel origins that must be preserved
    expected_origins = [
        'https://*.loca.lt',
        'http://*.loca.lt',
        'https://*.ngrok-free.app',
        'http://*.ngrok-free.app',
        'https://*.ngrok.io',
        'http://*.ngrok.io',
        'https://*.trycloudflare.com',
        'http://*.trycloudflare.com',
        'http://localhost:*',
        'http://127.0.0.1:*',
    ]
    
    actual_origins = settings.CSRF_TRUSTED_ORIGINS
    
    # Verify all expected origins are present
    for origin in expected_origins:
        assert origin in actual_origins, (
            f"CSRF_TRUSTED_ORIGINS missing expected origin: {origin}\n"
            f"Expected: {expected_origins}\n"
            f"Actual: {actual_origins}"
        )
    
    # Verify the list matches exactly (order doesn't matter)
    assert set(actual_origins) == set(expected_origins), (
        f"CSRF_TRUSTED_ORIGINS has unexpected changes\n"
        f"Expected: {sorted(expected_origins)}\n"
        f"Actual: {sorted(actual_origins)}"
    )


def test_preservation_proxy_headers():
    """
    Property 2: Preservation - Proxy/Tunnel Headers Unchanged
    
    **Validates: Requirement 3.2**
    
    This test verifies that proxy/tunnel header configuration
    (SECURE_PROXY_SSL_HEADER, USE_X_FORWARDED_HOST, USE_X_FORWARDED_PORT)
    remains unchanged.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    # Expected proxy header settings
    assert settings.SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https'), (
        f"SECURE_PROXY_SSL_HEADER changed\n"
        f"Expected: ('HTTP_X_FORWARDED_PROTO', 'https')\n"
        f"Actual: {settings.SECURE_PROXY_SSL_HEADER}"
    )
    
    assert settings.USE_X_FORWARDED_HOST is True, (
        f"USE_X_FORWARDED_HOST changed\n"
        f"Expected: True\n"
        f"Actual: {settings.USE_X_FORWARDED_HOST}"
    )
    
    assert settings.USE_X_FORWARDED_PORT is True, (
        f"USE_X_FORWARDED_PORT changed\n"
        f"Expected: True\n"
        f"Actual: {settings.USE_X_FORWARDED_PORT}"
    )


def test_preservation_cookie_samesite():
    """
    Property 2: Preservation - Cookie SameSite Settings Unchanged
    
    **Validates: Requirement 3.3**
    
    This test verifies that SESSION_COOKIE_SAMESITE and CSRF_COOKIE_SAMESITE
    remain set to 'Lax' for tunnel compatibility.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    assert settings.SESSION_COOKIE_SAMESITE == 'Lax', (
        f"SESSION_COOKIE_SAMESITE changed\n"
        f"Expected: 'Lax'\n"
        f"Actual: {settings.SESSION_COOKIE_SAMESITE}"
    )
    
    assert settings.CSRF_COOKIE_SAMESITE == 'Lax', (
        f"CSRF_COOKIE_SAMESITE changed\n"
        f"Expected: 'Lax'\n"
        f"Actual: {settings.CSRF_COOKIE_SAMESITE}"
    )


def test_preservation_cookie_httponly():
    """
    Property 2: Preservation - Cookie HttpOnly Settings Unchanged
    
    **Validates: Requirement 3.4**
    
    This test verifies that SESSION_COOKIE_HTTPONLY and CSRF_COOKIE_HTTPONLY
    remain set to True and False respectively.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    assert settings.SESSION_COOKIE_HTTPONLY is True, (
        f"SESSION_COOKIE_HTTPONLY changed\n"
        f"Expected: True\n"
        f"Actual: {settings.SESSION_COOKIE_HTTPONLY}"
    )
    
    assert settings.CSRF_COOKIE_HTTPONLY is False, (
        f"CSRF_COOKIE_HTTPONLY changed\n"
        f"Expected: False\n"
        f"Actual: {settings.CSRF_COOKIE_HTTPONLY}"
    )


def test_preservation_django_app_configuration():
    """
    Property 2: Preservation - Django App Configuration Unchanged
    
    **Validates: Requirement 3.5**
    
    This test verifies that core Django configuration (INSTALLED_APPS,
    AUTH_USER_MODEL, LOGIN_URL, MIDDLEWARE, TEMPLATES, WSGI_APPLICATION,
    AUTH_PASSWORD_VALIDATORS, LANGUAGE_CODE, TIME_ZONE, STATIC_URL,
    MEDIA_URL, DEFAULT_AUTO_FIELD) remains unchanged.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    # INSTALLED_APPS
    expected_installed_apps = [
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
    assert settings.INSTALLED_APPS == expected_installed_apps, (
        f"INSTALLED_APPS changed\n"
        f"Expected: {expected_installed_apps}\n"
        f"Actual: {settings.INSTALLED_APPS}"
    )
    
    # AUTH_USER_MODEL
    assert settings.AUTH_USER_MODEL == 'accounts.User', (
        f"AUTH_USER_MODEL changed\n"
        f"Expected: 'accounts.User'\n"
        f"Actual: {settings.AUTH_USER_MODEL}"
    )
    
    # LOGIN URLs
    assert settings.LOGIN_URL == '/login/', (
        f"LOGIN_URL changed\n"
        f"Expected: '/login/'\n"
        f"Actual: {settings.LOGIN_URL}"
    )
    
    assert settings.LOGIN_REDIRECT_URL == '/dashboard/', (
        f"LOGIN_REDIRECT_URL changed\n"
        f"Expected: '/dashboard/'\n"
        f"Actual: {settings.LOGIN_REDIRECT_URL}"
    )
    
    assert settings.LOGOUT_REDIRECT_URL == '/login/', (
        f"LOGOUT_REDIRECT_URL changed\n"
        f"Expected: '/login/'\n"
        f"Actual: {settings.LOGOUT_REDIRECT_URL}"
    )
    
    # MIDDLEWARE
    expected_middleware = [
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'edumatrix.middleware.TunnelAccessMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ]
    assert settings.MIDDLEWARE == expected_middleware, (
        f"MIDDLEWARE changed\n"
        f"Expected: {expected_middleware}\n"
        f"Actual: {settings.MIDDLEWARE}"
    )
    
    # WSGI_APPLICATION
    assert settings.WSGI_APPLICATION == 'edumatrix.wsgi.application', (
        f"WSGI_APPLICATION changed\n"
        f"Expected: 'edumatrix.wsgi.application'\n"
        f"Actual: {settings.WSGI_APPLICATION}"
    )
    
    # LANGUAGE_CODE and TIME_ZONE
    assert settings.LANGUAGE_CODE == 'en-us', (
        f"LANGUAGE_CODE changed\n"
        f"Expected: 'en-us'\n"
        f"Actual: {settings.LANGUAGE_CODE}"
    )
    
    assert settings.TIME_ZONE == 'Asia/Kolkata', (
        f"TIME_ZONE changed\n"
        f"Expected: 'Asia/Kolkata'\n"
        f"Actual: {settings.TIME_ZONE}"
    )
    
    # STATIC and MEDIA URLs
    assert settings.STATIC_URL == '/static/', (
        f"STATIC_URL changed\n"
        f"Expected: '/static/'\n"
        f"Actual: {settings.STATIC_URL}"
    )
    
    assert settings.MEDIA_URL == '/media/', (
        f"MEDIA_URL changed\n"
        f"Expected: '/media/'\n"
        f"Actual: {settings.MEDIA_URL}"
    )
    
    # DEFAULT_AUTO_FIELD
    assert settings.DEFAULT_AUTO_FIELD == 'django.db.models.BigAutoField', (
        f"DEFAULT_AUTO_FIELD changed\n"
        f"Expected: 'django.db.models.BigAutoField'\n"
        f"Actual: {settings.DEFAULT_AUTO_FIELD}"
    )


def test_preservation_templates_configuration():
    """
    Property 2: Preservation - Templates Configuration Unchanged
    
    **Validates: Requirement 3.5**
    
    This test verifies that TEMPLATES configuration remains unchanged.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    # Verify TEMPLATES structure
    assert len(settings.TEMPLATES) == 1, (
        f"TEMPLATES list length changed\n"
        f"Expected: 1\n"
        f"Actual: {len(settings.TEMPLATES)}"
    )
    
    template_config = settings.TEMPLATES[0]
    
    assert template_config['BACKEND'] == 'django.template.backends.django.DjangoTemplates', (
        f"TEMPLATES BACKEND changed\n"
        f"Expected: 'django.template.backends.django.DjangoTemplates'\n"
        f"Actual: {template_config['BACKEND']}"
    )
    
    assert template_config['APP_DIRS'] is True, (
        f"TEMPLATES APP_DIRS changed\n"
        f"Expected: True\n"
        f"Actual: {template_config['APP_DIRS']}"
    )
    
    expected_context_processors = [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]
    actual_context_processors = template_config['OPTIONS']['context_processors']
    
    assert actual_context_processors == expected_context_processors, (
        f"TEMPLATES context_processors changed\n"
        f"Expected: {expected_context_processors}\n"
        f"Actual: {actual_context_processors}"
    )


def test_preservation_auth_password_validators():
    """
    Property 2: Preservation - Auth Password Validators Unchanged
    
    **Validates: Requirement 3.5**
    
    This test verifies that AUTH_PASSWORD_VALIDATORS configuration remains unchanged.
    
    EXPECTED OUTCOME ON UNFIXED CODE: PASS (establishes baseline)
    EXPECTED OUTCOME AFTER FIX: PASS (confirms preservation)
    """
    settings = load_settings_module()
    
    expected_validators = [
        {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
        {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
        {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
        {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
    ]
    
    assert settings.AUTH_PASSWORD_VALIDATORS == expected_validators, (
        f"AUTH_PASSWORD_VALIDATORS changed\n"
        f"Expected: {expected_validators}\n"
        f"Actual: {settings.AUTH_PASSWORD_VALIDATORS}"
    )


if __name__ == '__main__':
    # Run all preservation tests
    tests = [
        ("CSRF_TRUSTED_ORIGINS", test_preservation_csrf_trusted_origins),
        ("Proxy Headers", test_preservation_proxy_headers),
        ("Cookie SameSite", test_preservation_cookie_samesite),
        ("Cookie HttpOnly", test_preservation_cookie_httponly),
        ("Django App Configuration", test_preservation_django_app_configuration),
        ("Templates Configuration", test_preservation_templates_configuration),
        ("Auth Password Validators", test_preservation_auth_password_validators),
    ]
    
    passed = 0
    failed = 0
    
    print("Running Preservation Property Tests on UNFIXED code...")
    print("=" * 70)
    
    for test_name, test_func in tests:
        try:
            test_func()
            print(f"✓ PASS: {test_name}")
            passed += 1
        except AssertionError as e:
            print(f"✗ FAIL: {test_name}")
            print(f"  {str(e)}")
            failed += 1
    
    print("=" * 70)
    print(f"\nResults: {passed} passed, {failed} failed out of {len(tests)} tests")
    
    if failed > 0:
        print("\nWARNING: Preservation tests failed on unfixed code!")
        print("This indicates the baseline behavior is different than expected.")
        exit(1)
    else:
        print("\n✓ All preservation tests PASSED on unfixed code!")
        print("Baseline behavior established. These tests should continue to pass after the fix.")
