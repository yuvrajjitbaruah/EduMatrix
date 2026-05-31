import json
import urllib.error
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.hashers import make_password
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import EmailVerificationOTP, User


class PublicSiteTests(TestCase):
    def test_public_pages_render(self):
        route_names = ['home', 'about', 'contact', 'terms', 'privacy', 'offline']
        for name in route_names:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    def test_public_pages_show_support_email_without_personal_team_content(self):
        home = self.client.get(reverse('home'))
        home_content = home.content.decode()
        self.assertIn('support@edumatrix.tech', home_content)
        self.assertNotIn('Yuvrajjit Baruah', home_content)

        about = self.client.get(reverse('about'))
        about_content = about.content.decode()
        self.assertIn('support@edumatrix.tech', about_content)
        self.assertNotIn('Yuvrajjit Baruah', about_content)
        self.assertNotIn('yjb-web.jpg', about_content)

    def test_team_page_is_not_available(self):
        response = self.client.get('/team/')
        self.assertEqual(response.status_code, 404)

    def test_password_reset_pages_render(self):
        for name in ['password_reset', 'password_reset_done', 'password_reset_complete']:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_accepts_email_without_account_disclosure(self):
        response = self.client.post(reverse('password_reset'), {'email': 'nobody@example.com'})
        self.assertRedirects(response, reverse('password_reset_done'))

    def test_signup_pages_do_not_expose_development_otp(self):
        for name in ['signup_student', 'signup_teacher']:
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                content = response.content.decode()
                self.assertEqual(response.status_code, 200)
                self.assertNotIn('Development OTP', content)
                self.assertIn('EduMatrix verification email', content)

    @override_settings(
        EMAIL_BACKEND='accounts.email_backend.ResendEmailBackend',
        RESEND_API_KEY='',
        PUBLIC_SITE_URL='',
    )
    def test_signup_is_blocked_until_resend_and_public_url_are_configured(self):
        response = self.client.get(reverse('signup_teacher'))
        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Email verification is not ready yet', content)
        self.assertIn('email API key', content)

        response = self.client.post(reverse('signup_teacher'), {
            'full_name': 'Prof Alan Smith',
            'email': 'alan@faculty.edu',
            'phone': '9876543210',
            'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(EmailVerificationOTP.objects.count(), 0)

    @override_settings(AUTH_RATE_LIMITS={'login': {'limit': 1, 'window': 60}})
    def test_login_rate_limit_blocks_repeated_failures(self):
        cache.clear()
        User.objects.create_user(
            username='rate-limit-user',
            email='rate-limit@example.com',
            password='StrongPass123!',
            role='student',
            roll_no='RL001',
        )

        first = self.client.post(reverse('login'), {
            'login_id': 'rate-limit@example.com',
            'password': 'WrongPass123!',
        })
        self.assertEqual(first.status_code, 200)

        second = self.client.post(reverse('login'), {
            'login_id': 'rate-limit@example.com',
            'password': 'WrongPass123!',
        })
        self.assertEqual(second.status_code, 429)
        self.assertIn('Too many login attempts', second.content.decode())
        cache.clear()


class ResendEmailBackendTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='accounts.email_backend.ResendEmailBackend',
        RESEND_API_KEY='re_test_key',
        DEFAULT_FROM_EMAIL='EduMatrix <onboarding@resend.dev>',
    )
    @patch('accounts.email_backend.urllib.request.urlopen')
    def test_resend_backend_sends_html_and_text_payload(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = b'{"id":"email_123"}'
        mock_urlopen.return_value.__enter__.return_value = response

        email = EmailMultiAlternatives(
            subject='Welcome to EduMatrix',
            body='Plain text body',
            from_email='EduMatrix <onboarding@resend.dev>',
            to=['student@example.com'],
        )
        email.attach_alternative('<p>HTML body</p>', 'text/html')

        sent = email.send()

        self.assertEqual(sent, 1)
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(payload['from'], 'EduMatrix <onboarding@resend.dev>')
        self.assertEqual(payload['to'], ['student@example.com'])
        self.assertEqual(payload['subject'], 'Welcome to EduMatrix')
        self.assertEqual(payload['text'], 'Plain text body')
        self.assertEqual(payload['html'], '<p>HTML body</p>')
        self.assertEqual(request.get_header('User-agent'), 'EduMatrix/2026.04')

    @override_settings(
        EMAIL_BACKEND='accounts.email_backend.ResendEmailBackend',
        RESEND_API_KEY='',
        DEFAULT_FROM_EMAIL='EduMatrix <onboarding@resend.dev>',
    )
    def test_resend_backend_requires_api_key(self):
        email = EmailMultiAlternatives(
            subject='Missing key',
            body='Body',
            to=['student@example.com'],
        )

        with self.assertRaises(ImproperlyConfigured):
            email.send()

    @override_settings(
        EMAIL_BACKEND='accounts.email_backend.ResendEmailBackend',
        RESEND_API_KEY='re_test_key',
        DEFAULT_FROM_EMAIL='EduMatrix <support@edumatrix.tech>',
    )
    @patch('accounts.email_backend.urllib.request.urlopen')
    def test_resend_backend_formats_cloudflare_1010_error_cleanly(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = (
            b'{"status":403,"error":{"code":1010,"message":"Access denied"},"message":"Access denied"}'
        )
        error = urllib.error.HTTPError(
            url='https://api.resend.com/emails',
            code=403,
            msg='Forbidden',
            hdrs=None,
            fp=response,
        )
        mock_urlopen.side_effect = error

        email = EmailMultiAlternatives(
            subject='Verify account',
            body='Body',
            to=['teacher@example.com'],
        )

        with self.assertRaises(RuntimeError) as exc:
            email.send()

        self.assertIn('email service blocked the request before it reached the API', str(exc.exception))

    @override_settings(
        EMAIL_BACKEND='accounts.email_backend.ResendEmailBackend',
        RESEND_API_KEY='re_test_key',
        DEFAULT_FROM_EMAIL='EduMatrix <support@edumatrix.tech>',
    )
    @patch('accounts.email_backend.urllib.request.urlopen')
    def test_resend_backend_formats_testing_mode_error_cleanly(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = (
            b'{"name":"validation_error","message":"You can only send testing emails to your own email address '
            b'(one@example.com). To send emails to other recipients, please verify a domain at resend.com/domains, '
            b'and change the `from` address to an email using this domain."}'
        )
        error = urllib.error.HTTPError(
            url='https://api.resend.com/emails',
            code=403,
            msg='Forbidden',
            hdrs=None,
            fp=response,
        )
        mock_urlopen.side_effect = error

        email = EmailMultiAlternatives(
            subject='Verify account',
            body='Body',
            to=['teacher@example.com'],
        )

        with self.assertRaises(RuntimeError) as exc:
            email.send()

        self.assertIn('still in testing mode', str(exc.exception))


class SignupVerificationFlowTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='accounts.email_backend.ResendEmailBackend',
        RESEND_API_KEY='re_test_key',
        DEFAULT_FROM_EMAIL='EduMatrix <support@edumatrix.tech>',
        PUBLIC_SITE_URL='https://edumatrix.tech',
    )
    @patch('accounts.email_backend.urllib.request.urlopen')
    def test_teacher_signup_sends_branded_verification_email(self, mock_urlopen):
        response = MagicMock()
        response.read.return_value = b'{"id":"email_123"}'
        mock_urlopen.return_value.__enter__.return_value = response

        response = self.client.post(reverse('signup_teacher'), {
            'full_name': 'Prof Alan Smith',
            'email': 'alan@faculty.edu',
            'phone': '9876543210',
            'password': 'StrongPass123!',
        })

        self.assertRedirects(response, reverse('verify_signup_otp'))
        self.assertEqual(EmailVerificationOTP.objects.count(), 1)
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode('utf-8'))
        self.assertEqual(payload['from'], 'EduMatrix <support@edumatrix.tech>')
        self.assertIn('https://edumatrix.tech/signup/verify-email/?signup_token=', payload['text'])
        self.assertNotIn('localhost:3000', payload['text'])
        self.assertIn('Confirm your EduMatrix teacher account', payload['subject'])

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        RESEND_API_KEY='re_test_key',
        PUBLIC_SITE_URL='https://edumatrix.tech',
    )
    @patch('accounts.views._send_welcome_email')
    def test_signup_link_completion_creates_local_user(self, mock_welcome):
        code = '246810'
        otp = EmailVerificationOTP.objects.create(
            email='teacher@example.com',
            role='teacher',
            purpose='signup',
            code_hash=make_password(code),
            payload={
                'full_name': 'Magic Link Teacher',
                'email': 'teacher@example.com',
                'username': 'teacher@example.com',
                'phone_number': '+919999999999',
                'password_hash': 'pbkdf2_sha256$260000$example$hash',
            },
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        signup_token = signing.dumps({'otp_id': otp.pk, 'code': code}, salt='edumatrix-signup-link')

        response = self.client.get(f"{reverse('verify_signup_otp')}?signup_token={signup_token}")

        self.assertRedirects(response, reverse('dashboard_home'))
        created_user = User.objects.get(email='teacher@example.com')
        self.assertIsNone(created_user.supabase_user_id)
        self.assertIsNotNone(created_user.email_verified_at)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertTrue(mock_welcome.called)
