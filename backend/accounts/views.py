from datetime import timedelta
import secrets
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from dashboard.models import ActivityLog

from .models import EmailVerificationOTP, Institution, PlatformInquiry, User
from .email_branding import email_branding_context
from .security import consume_auth_attempt, reset_auth_attempts


MAX_OTP_ATTEMPTS = 5
PHONE_PATTERN = re.compile(r'^\+[1-9]\d{9,14}$')
SUPPORT_EMAIL = 'support@edumatrix.tech'
SIGNUP_TOKEN_SALT = 'edumatrix-signup-link'

PUBLIC_PAGE_DATA = {
    'about': {
        'title': 'About EduMatrix',
        'kicker': 'Built for modern institutions',
        'lede': 'EduMatrix brings academic operations, communication, performance tracking, and campus management into one connected platform.',
        'sections': [
            {
                'heading': 'What EduMatrix solves',
                'items': [
                    'Fragmented attendance, assignment, grade, and communication workflows are unified into one role-aware system.',
                    'Administrators get institutional control without taking over teacher-owned academic work.',
                    'Teachers can manage classes, publish work, grade submissions, and communicate with students.',
                    'Students can join classes, submit assignments, track progress, and stay updated from anywhere.',
                ],
            },
            {
                'heading': 'Why institutions choose it',
                'items': [
                    'Secure production data layer for readiness.',
                    'Branded email verification for safer teacher and student onboarding.',
                    'Responsive interface designed for desktop, tablet, and mobile use.',
                    'Installable PWA support so EduMatrix can feel like a native web app.',
                ],
            },
        ],
    },
    'terms': {
        'title': 'Terms & Conditions',
        'kicker': 'Use of EduMatrix',
        'lede': 'These terms describe the expected use of EduMatrix by institutions, staff, teachers, students, and guardians.',
        'sections': [
            {
                'heading': 'Access and accounts',
                'items': [
                    'Users are responsible for keeping their account credentials secure.',
                    'Teacher and student accounts must complete email verification before first use.',
                    'Institutions are responsible for assigning correct roles and permissions.',
                ],
            },
            {
                'heading': 'Platform use',
                'items': [
                    'EduMatrix should be used for lawful academic, administrative, and communication workflows.',
                    'Users must not upload harmful content, attempt unauthorized access, or misuse student data.',
                    'Feature availability may vary based on institution configuration and production deployment settings.',
                ],
            },
        ],
    },
    'privacy': {
        'title': 'Privacy Policy',
        'kicker': 'Data protection',
        'lede': 'EduMatrix is designed to handle academic and institutional data with care, clarity, and role-based access.',
        'sections': [
            {
                'heading': 'Data we handle',
                'items': [
                    'Account details such as name, email, role, phone number, roll number, and department.',
                    'Academic records such as attendance, classes, assignments, submissions, grades, notices, and reports.',
                    'Institution onboarding requests submitted through the public contact forms.',
                ],
            },
            {
                'heading': 'How data is used',
                'items': [
                    'Data is used to operate the EduMatrix platform and provide role-specific education management workflows.',
                    'Email addresses are used for account verification and important account communication.',
                    'Access to records is controlled by role, enrollment, and class ownership rules.',
                ],
            },
        ],
    },
    'contact': {
        'title': 'Contact Us',
        'kicker': 'Start with EduMatrix',
        'lede': 'Tell us about your institution and the EduMatrix support team will follow up for onboarding.',
        'sections': [
            {
                'heading': 'Direct contact',
                'items': [
                    f'Email: {SUPPORT_EMAIL}',
                    'For onboarding, include your institution name, contact person, student count, and the modules you want to use.',
                ],
            },
        ],
        'show_form': True,
    },
}


class SupabaseAuthError(Exception):
    pass


def _log_activity(user, action, description):
    try:
        ActivityLog.objects.create(user=user, action=action, description=description)
    except Exception:
        pass


def _rate_limit_message(scope):
    config = {
        'login': 'Too many login attempts. Wait a few minutes and try again.',
        'signup': 'Too many signup attempts from this connection. Wait a bit before trying again.',
        'password_change': 'Too many password change attempts. Wait a few minutes and try again.',
    }
    return config.get(scope, 'Too many attempts. Try again later.')


def _save_platform_inquiry(request):
    institute_name = (request.POST.get('institute_name') or '').strip()
    contact_name = (request.POST.get('contact_name') or '').strip()
    email = (request.POST.get('email') or '').strip().lower()
    phone = (request.POST.get('phone') or '').strip()
    student_count = (request.POST.get('student_count') or '').strip()
    message = (request.POST.get('message') or '').strip()

    if not all([institute_name, contact_name, email]):
        messages.error(request, 'Institute name, contact name, and email are required.')
        return False

    institution = _resolve_institution_from_email(request, email, preferred_name=institute_name)
    if institution is None:
        return False

    PlatformInquiry.objects.create(
        institute_name=institute_name,
        contact_name=contact_name,
        email=email,
        institution_domain=institution.domain,
        linked_institution=institution,
        verification_status='verified',
        phone=phone,
        student_count=student_count,
        message=message,
    )
    messages.success(request, f'Thanks. {institution.name} has been verified and your onboarding request has been received.')
    return True


def landing_view(request):
    if request.method == 'POST':
        _save_platform_inquiry(request)
        return redirect('home')

    return render(request, 'landing.html')


def public_page_view(request, page_slug):
    page = PUBLIC_PAGE_DATA.get(page_slug)
    if not page:
        raise Http404('Page not found')
    if request.method == 'POST' and page.get('show_form'):
        _save_platform_inquiry(request)
        return redirect(page_slug)
    return render(request, 'public_page.html', {'page': page, 'page_slug': page_slug})


def service_worker_view(request):
    service_worker_path = Path(settings.BASE_DIR) / 'static' / 'js' / 'service-worker.js'
    if not service_worker_path.exists():
        raise Http404('Service worker not found')
    response = FileResponse(service_worker_path.open('rb'), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


def offline_view(request):
    return render(request, 'offline.html')


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_home')

    if request.method == 'POST':
        login_id = (request.POST.get('login_id') or '').strip()
        password = request.POST.get('password') or ''

        allowed, _ = consume_auth_attempt('login', request, login_id)
        if not allowed:
            messages.error(request, _rate_limit_message('login'))
            return render(request, 'accounts/login.html', status=429)

        user = User.objects.filter(
            Q(email__iexact=login_id) | Q(roll_no__iexact=login_id) | Q(username__iexact=login_id)
        ).first()
        if user and user.is_active and user.check_password(password):
            reset_auth_attempts('login', request, login_id)
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            _log_activity(user, 'login', 'Signed in to EduMatrix.')
            return redirect('dashboard_home')
        messages.error(request, 'Invalid credentials.')

    return render(request, 'accounts/login.html')


def _split_full_name(full_name):
    parts = (full_name or '').strip().split()
    if not parts:
        return '', ''
    return parts[0], ' '.join(parts[1:])


def _normalise_phone(phone):
    phone = (phone or '').strip()
    if not phone:
        return ''
    digits = re.sub(r'\D', '', phone)
    if phone.startswith('+') and digits:
        return f'+{digits}'
    if len(digits) == 10:
        return f'+91{digits}'
    if digits.startswith('91') and len(digits) == 12:
        return f'+{digits}'
    return phone


def _resolve_institution_from_email(request, email, *, preferred_name=''):
    institution = Institution.provision_for_email(email, preferred_name=preferred_name)
    if institution:
        return institution

    messages.error(
        request,
        'Use an institutional email address ending in .edu, .edu.in, .ac.in, or .ac so EduMatrix can verify your institution automatically.',
    )
    return None


def _user_exists(email, username, roll_no=None):
    lookup = Q(email__iexact=email) | Q(username__iexact=username)
    if roll_no:
        lookup |= Q(roll_no__iexact=roll_no)
    return User.objects.filter(lookup).exists()


def _signup_context(role):
    signup_email_missing = []
    resend_backend = getattr(settings, 'RESEND_EMAIL_BACKEND', '')
    if settings.EMAIL_BACKEND != resend_backend:
        signup_email_missing.append('email delivery setup')
    if not getattr(settings, 'RESEND_API_KEY', ''):
        signup_email_missing.append('email API key')
    if not settings.PUBLIC_SITE_URL:
        signup_email_missing.append('Public site URL')
    return {
        'signup_role': role,
        'signup_email_ready': not signup_email_missing,
        'signup_email_missing': signup_email_missing,
        'institution_domain_hint': '.edu, .edu.in, .ac.in, .ac',
    }


def _signup_email_setup_message():
    missing = []
    resend_backend = getattr(settings, 'RESEND_EMAIL_BACKEND', '')
    if settings.EMAIL_BACKEND != resend_backend:
        missing.append('email delivery setup')
    if not getattr(settings, 'RESEND_API_KEY', ''):
        missing.append('email API key')
    if not settings.PUBLIC_SITE_URL:
        missing.append('Public site URL')

    if not missing:
        return 'Email verification is not ready on this server.'

    return (
        'Email verification is not ready on this server. '
        f'Missing: {", ".join(missing)}. Update the server environment and restart EduMatrix.'
    )


def _build_public_url(request, path=''):
    if settings.PUBLIC_SITE_URL:
        base = settings.PUBLIC_SITE_URL.rstrip('/')
    elif request:
        base = request.build_absolute_uri('/').rstrip('/')
    else:
        base = ''
    if not path:
        return base
    return f'{base}{path}'


def _build_signup_link_token(otp, code):
    return signing.dumps({'otp_id': otp.pk, 'code': code}, salt=SIGNUP_TOKEN_SALT)


def _verify_signup_link_token(token):
    payload = signing.loads(token, salt=SIGNUP_TOKEN_SALT, max_age=settings.SUPABASE_OTP_TTL_MINUTES * 60)
    otp = EmailVerificationOTP.objects.filter(pk=payload.get('otp_id'), purpose='signup', is_used=False).first()
    if not otp:
        raise ValidationError('Verification session expired.')
    code = str(payload.get('code') or '').strip()
    if not code or not check_password(code, otp.code_hash):
        raise ValidationError('Verification link is invalid or has already been used.')
    return otp, code


def _send_signup_verification_email(otp, code, request):
    verification_token = _build_signup_link_token(otp, code)
    verification_path = f"{reverse('verify_signup_otp')}?signup_token={verification_token}"
    verification_link = _build_public_url(request, verification_path)
    site_url = _build_public_url(request)
    role_label = otp.get_role_display()
    branding = email_branding_context(site_url)

    html_body = render_to_string('emails/signup_verification_email.html', {
        'otp': otp,
        'code': code,
        'verification_link': verification_link,
        'site_url': site_url,
        'role_label': role_label,
        **branding,
    })
    text_body = render_to_string('emails/signup_verification_email.txt', {
        'otp': otp,
        'code': code,
        'verification_link': verification_link,
        'site_url': site_url,
        'role_label': role_label,
    })
    email = EmailMultiAlternatives(
        subject=f'Confirm your EduMatrix {role_label.lower()} account',
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[otp.email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)


def _validate_signup_input(request, *, full_name, email, password, phone='', roll_no=''):
    errors = []
    if len(full_name) > 150:
        errors.append('Full name is too long.')
    if roll_no and len(roll_no) > 50:
        errors.append('Roll number is too long.')
    try:
        validate_email(email)
    except ValidationError:
        errors.append('Enter a valid email address.')
    if phone and not PHONE_PATTERN.match(phone):
        errors.append('Enter a valid phone number with country code, for example +919876543210.')
    try:
        validate_password(password)
    except ValidationError as exc:
        errors.extend(exc.messages)

    if errors:
        messages.error(request, ' '.join(errors[:4]))
        return False
    return True


def _supabase_auth_request(endpoint, payload):
    if not settings.SUPABASE_AUTH_ENABLED:
        raise SupabaseAuthError('Email verification is disabled on this server.')
    if not settings.SUPABASE_AUTH_READY:
        raise SupabaseAuthError(_signup_email_setup_message())

    url = f"{settings.SUPABASE_URL}/auth/v1/{endpoint.lstrip('/')}"
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'apikey': settings.SUPABASE_ANON_KEY,
            'Authorization': f'Bearer {settings.SUPABASE_ANON_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(body)
            message = detail.get('msg') or detail.get('message') or detail.get('error_description') or body
        except json.JSONDecodeError:
            message = body or str(exc)
        raise SupabaseAuthError(message)
    except urllib.error.URLError as exc:
        raise SupabaseAuthError(str(exc.reason))


def _supabase_email_redirect_url(request=None):
    if settings.SUPABASE_EMAIL_REDIRECT_URL:
        return settings.SUPABASE_EMAIL_REDIRECT_URL

    verify_path = reverse('verify_signup_otp')
    if settings.PUBLIC_SITE_URL:
        return f"{settings.PUBLIC_SITE_URL}{verify_path}"
    if request:
        return request.build_absolute_uri(verify_path)
    return ''


def _supabase_get_user_from_access_token(access_token):
    if not settings.SUPABASE_AUTH_ENABLED:
        raise SupabaseAuthError('Email verification is disabled on this server.')
    if not settings.SUPABASE_AUTH_READY:
        raise SupabaseAuthError(_signup_email_setup_message())

    request = urllib.request.Request(
        url=f"{settings.SUPABASE_URL}/auth/v1/user",
        headers={
            'apikey': settings.SUPABASE_ANON_KEY,
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
        },
        method='GET',
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode('utf-8')
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            detail = json.loads(body)
            message = detail.get('msg') or detail.get('message') or detail.get('error_description') or body
        except json.JSONDecodeError:
            message = body or str(exc)
        raise SupabaseAuthError(message)
    except urllib.error.URLError as exc:
        raise SupabaseAuthError(str(exc.reason))


def _supabase_send_signup_otp(email, role, payload, request=None):
    metadata = {
        'role': role,
        'full_name': payload.get('full_name'),
        'roll_no': payload.get('roll_no'),
        'phone_number': payload.get('phone_number'),
        'source': 'edumatrix_django_signup',
    }
    request_payload = {
        'email': email,
        'create_user': True,
        'data': {key: value for key, value in metadata.items() if value},
    }
    redirect_url = _supabase_email_redirect_url(request)
    if redirect_url:
        request_payload['options'] = {
            'email_redirect_to': redirect_url,
        }
    return _supabase_auth_request('otp', request_payload)


def _supabase_verify_signup_otp(email, token):
    return _supabase_auth_request('verify', {
        'email': email,
        'token': token,
        'type': 'email',
    })


def _supabase_verify_signup_link(token_hash, verification_type='signup'):
    return _supabase_auth_request('verify', {
        'token_hash': token_hash,
        'type': verification_type or 'signup',
    })


def _send_welcome_email(user, request=None):
    site_url = _build_public_url(request)
    html_body = render_to_string('emails/welcome_email.html', {
        'user': user,
        'site_url': site_url,
        **email_branding_context(site_url),
    })
    text_body = (
        f"Welcome to EduMatrix, {user.get_full_name() or user.username}.\n\n"
        "Your account is verified and ready. Sign in to manage classes, attendance, assignments, communication, and progress from one platform.\n\n"
        "EduMatrix"
    )
    email = EmailMultiAlternatives(
        subject='Welcome to EduMatrix',
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)


def _issue_signup_otp(request, role, email, payload):
    code = f'{secrets.randbelow(1000000):06d}'
    otp = EmailVerificationOTP.objects.create(
        email=email,
        role=role,
        purpose='signup',
        code_hash=make_password(code),
        payload=payload,
        expires_at=timezone.now() + timedelta(minutes=settings.SUPABASE_OTP_TTL_MINUTES),
    )

    try:
        _send_signup_verification_email(otp, code, request)
    except Exception:
        otp.delete()
        messages.error(request, 'Could not send the EduMatrix verification email right now. Please check the email address and try again.')
        return False

    EmailVerificationOTP.objects.filter(
        email__iexact=email,
        role=role,
        purpose='signup',
        is_used=False,
    ).exclude(pk=otp.pk).update(is_used=True, used_at=timezone.now())

    request.session['pending_signup_otp_id'] = otp.pk
    request.session['pending_signup_role'] = role
    messages.success(request, 'We sent an EduMatrix verification email to your inbox.')
    return True


def signup_student_view(request):
    if request.method == 'POST':
        if _signup_context('student')['signup_email_missing']:
            messages.error(request, _signup_email_setup_message())
            return redirect('signup_student')

        full_name = (request.POST.get('full_name') or '').strip()
        email = (request.POST.get('email') or '').strip().lower()
        roll_no = (request.POST.get('roll_no') or '').strip()
        phone = _normalise_phone(request.POST.get('phone'))
        password = request.POST.get('password') or ''

        allowed, _ = consume_auth_attempt('signup', request, f'student:{email or roll_no}')
        if not allowed:
            messages.error(request, _rate_limit_message('signup'))
            return redirect('signup_student')

        if not all([full_name, email, roll_no, password]):
            messages.error(request, 'Full name, email, roll number, and password are required.')
            return redirect('signup_student')

        if not _validate_signup_input(request, full_name=full_name, email=email, password=password, phone=phone, roll_no=roll_no):
            return redirect('signup_student')

        institution = _resolve_institution_from_email(request, email)
        if institution is None:
            return redirect('signup_student')

        username = roll_no
        if _user_exists(email, username, roll_no):
            messages.error(request, 'User with this email or roll number already exists.')
            return redirect('signup_student')

        payload = {
            'full_name': full_name,
            'email': email,
            'username': username,
            'roll_no': roll_no,
            'phone_number': phone,
            'password_hash': make_password(password),
            'institution_domain': institution.domain,
            'institution_name': institution.name,
        }
        if _issue_signup_otp(request, 'student', email, payload):
            return redirect('verify_signup_otp')
        return redirect('signup_student')

    return render(request, 'accounts/signup_student.html', _signup_context('student'))


def signup_teacher_view(request):
    if request.method == 'POST':
        if _signup_context('teacher')['signup_email_missing']:
            messages.error(request, _signup_email_setup_message())
            return redirect('signup_teacher')

        full_name = (request.POST.get('full_name') or '').strip()
        email = (request.POST.get('email') or '').strip().lower()
        phone = _normalise_phone(request.POST.get('phone'))
        password = request.POST.get('password') or ''

        allowed, _ = consume_auth_attempt('signup', request, f'teacher:{email}')
        if not allowed:
            messages.error(request, _rate_limit_message('signup'))
            return redirect('signup_teacher')

        if not all([full_name, email, password]):
            messages.error(request, 'Full name, email, and password are required.')
            return redirect('signup_teacher')

        if not _validate_signup_input(request, full_name=full_name, email=email, password=password, phone=phone):
            return redirect('signup_teacher')

        institution = _resolve_institution_from_email(request, email)
        if institution is None:
            return redirect('signup_teacher')

        username = email
        if _user_exists(email, username):
            messages.error(request, 'User with this email already exists.')
            return redirect('signup_teacher')

        payload = {
            'full_name': full_name,
            'email': email,
            'username': username,
            'phone_number': phone,
            'password_hash': make_password(password),
            'institution_domain': institution.domain,
            'institution_name': institution.name,
        }
        if _issue_signup_otp(request, 'teacher', email, payload):
            return redirect('verify_signup_otp')
        return redirect('signup_teacher')

    return render(request, 'accounts/signup_teacher.html', _signup_context('teacher'))


def _create_user_from_otp(otp, supabase_user_id=None):
    payload = otp.payload
    email = payload.get('email')
    username = payload.get('username') or email
    roll_no = payload.get('roll_no') or None
    if _user_exists(email, username, roll_no):
        return None

    first_name, last_name = _split_full_name(payload.get('full_name'))
    institution = Institution.provision_for_email(email, preferred_name=payload.get('institution_name') or '')
    return User.objects.create(
        username=username,
        email=email,
        password=payload.get('password_hash'),
        first_name=first_name,
        last_name=last_name,
        role=otp.role,
        institution=institution,
        roll_no=roll_no,
        phone_number=payload.get('phone_number') or None,
        email_verified_at=timezone.now(),
        supabase_user_id=supabase_user_id,
    )


def _complete_supabase_signup(request, supabase_user):
    email = (supabase_user.get('email') or '').strip().lower()
    supabase_user_id = supabase_user.get('id')
    if not email:
        messages.error(request, 'Email verification did not return an email address.')
        return False

    existing_user = User.objects.filter(Q(supabase_user_id=supabase_user_id) | Q(email__iexact=email)).first()
    if existing_user:
        fields_to_update = []
        resolved_institution = Institution.provision_for_email(email)
        if supabase_user_id and existing_user.supabase_user_id != supabase_user_id:
            existing_user.supabase_user_id = supabase_user_id
            fields_to_update.append('supabase_user_id')
        if existing_user.email_verified_at is None:
            existing_user.email_verified_at = timezone.now()
            fields_to_update.append('email_verified_at')
        if resolved_institution and existing_user.institution_id != resolved_institution.id:
            existing_user.institution = resolved_institution
            fields_to_update.append('institution')
        if fields_to_update:
            existing_user.save(update_fields=fields_to_update)
        EmailVerificationOTP.objects.filter(
            email__iexact=email,
            purpose='signup',
            is_used=False,
        ).update(is_used=True, used_at=timezone.now())
        request.session.pop('pending_signup_otp_id', None)
        request.session.pop('pending_signup_role', None)
        login(request, existing_user, backend='django.contrib.auth.backends.ModelBackend')
        _log_activity(existing_user, 'login', 'Verified email and signed in.')
        return True

    otp = EmailVerificationOTP.objects.filter(
        email__iexact=email,
        purpose='signup',
        is_used=False,
    ).order_by('-created_at').first()
    if not otp:
        messages.error(request, 'We verified the email link, but no pending EduMatrix signup session was found for this email.')
        return False

    if otp.is_expired():
        otp.mark_used()
        messages.error(request, 'The signup verification window expired. Please request a new verification email.')
        return False

    user = _create_user_from_otp(otp, supabase_user_id=supabase_user_id)
    if user is None:
        otp.mark_used()
        messages.error(request, 'An account already exists for this email or roll number.')
        return False

    otp.mark_used()
    request.session.pop('pending_signup_otp_id', None)
    request.session.pop('pending_signup_role', None)
    reset_auth_attempts('signup', request, f'{otp.role}:{otp.email}')
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    _log_activity(user, 'login', 'Verified email and activated the account.')
    try:
        _send_welcome_email(user, request)
    except Exception:
        messages.info(request, 'Email verified. Welcome email could not be sent right now.')
    else:
        messages.success(request, 'Email verified. Your welcome email is on the way.')
    return True


def _complete_local_signup(request, otp):
    user = _create_user_from_otp(otp)
    if user is None:
        otp.mark_used()
        messages.error(request, 'An account already exists for this email or roll number.')
        return False

    otp.mark_used()
    request.session.pop('pending_signup_otp_id', None)
    request.session.pop('pending_signup_role', None)
    reset_auth_attempts('signup', request, f'{otp.role}:{otp.email}')
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    _log_activity(user, 'login', 'Verified email and activated the account.')
    try:
        _send_welcome_email(user, request)
    except Exception:
        messages.info(request, 'Email verified. Welcome email could not be sent right now.')
    else:
        messages.success(request, 'Email verified. Your welcome email is on the way.')
    return True


def verify_signup_otp_view(request):
    if request.method == 'GET':
        signup_token = (request.GET.get('signup_token') or '').strip()
        if signup_token:
            try:
                otp, _ = _verify_signup_link_token(signup_token)
            except Exception as exc:
                messages.error(request, f'Could not complete the EduMatrix verification link: {exc}')
            else:
                if otp.is_expired():
                    otp.mark_used()
                    messages.error(request, 'Verification link expired. Please request a new verification email.')
                elif _complete_local_signup(request, otp):
                    return redirect('dashboard_home')

        token_hash = (request.GET.get('token_hash') or '').strip()
        verification_type = (request.GET.get('type') or 'signup').strip()
        if token_hash:
            try:
                supabase_response = _supabase_verify_signup_link(token_hash, verification_type)
            except SupabaseAuthError:
                messages.error(request, 'Could not complete the email verification link. Please request a new verification email.')
            else:
                supabase_user = supabase_response.get('user') or supabase_response.get('data', {}).get('user') or {}
                if supabase_user and _complete_supabase_signup(request, supabase_user):
                    return redirect('dashboard_home')

    if request.method == 'POST' and request.POST.get('action') == 'complete_magic_link':
        access_token = (request.POST.get('access_token') or '').strip()
        token_hash = (request.POST.get('token_hash') or '').strip()
        verification_type = (request.POST.get('verification_type') or 'signup').strip()

        if not access_token and not token_hash:
            messages.error(request, 'No email verification token was received from the email link.')
            return redirect('login')

        try:
            if access_token:
                supabase_user = _supabase_get_user_from_access_token(access_token)
            else:
                supabase_response = _supabase_verify_signup_link(token_hash, verification_type)
                supabase_user = supabase_response.get('user') or supabase_response.get('data', {}).get('user') or {}
        except SupabaseAuthError:
            messages.error(request, 'Could not finish email verification. Please request a new verification email.')
            return redirect('login')

        if _complete_supabase_signup(request, supabase_user):
            return redirect('dashboard_home')
        return redirect('login')

    otp_id = request.session.get('pending_signup_otp_id')
    if not otp_id:
        messages.info(request, 'Please start signup before verifying your email.')
        return redirect('login')

    otp = EmailVerificationOTP.objects.filter(pk=otp_id, purpose='signup', is_used=False).first()
    if not otp:
        messages.error(request, 'Verification session expired. Please sign up again.')
        return redirect('signup_student')

    if otp.is_expired():
        otp.mark_used()
        request.session.pop('pending_signup_otp_id', None)
        request.session.pop('pending_signup_role', None)
        messages.error(request, 'Verification code expired. Please sign up again.')
        return redirect('signup_teacher' if otp.role == 'teacher' else 'signup_student')

    if request.method == 'POST':
        if request.POST.get('action') == 'resend':
            if _issue_signup_otp(request, otp.role, otp.email, otp.payload):
                messages.success(request, 'A new verification code has been sent.')
            return redirect('verify_signup_otp')

        code = (request.POST.get('otp') or '').strip().replace(' ', '')
        if not code:
            messages.error(request, 'Enter the verification code from your email.')
            return redirect('verify_signup_otp')
        if otp.attempts >= MAX_OTP_ATTEMPTS:
            otp.mark_used()
            request.session.pop('pending_signup_otp_id', None)
            request.session.pop('pending_signup_role', None)
            messages.error(request, 'Too many incorrect attempts. Please sign up again.')
            return redirect('signup_teacher' if otp.role == 'teacher' else 'signup_student')

        if not check_password(code, otp.code_hash):
            otp.attempts += 1
            otp.save(update_fields=['attempts'])
            messages.error(request, 'Incorrect or expired verification code.')
            return redirect('verify_signup_otp')
        if _complete_local_signup(request, otp):
            return redirect('dashboard_home')

    return render(request, 'accounts/verify_otp.html', {'otp': otp})


def logout_view(request):
    logout(request)
    return redirect('login')
