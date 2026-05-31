import base64
import json
import urllib.error
import urllib.request
from email.mime.base import MIMEBase
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    """Deliver Django email messages through the configured email API."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')
        self.api_url = getattr(settings, 'RESEND_API_URL', 'https://api.resend.com/emails')
        self.user_agent = getattr(settings, 'RESEND_USER_AGENT', 'EduMatrix/2026.04')

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        if not self.api_key:
            if self.fail_silently:
                return 0
            raise ImproperlyConfigured('RESEND_API_KEY is required when using this email backend.')

        sent_count = 0
        for email_message in email_messages:
            if not email_message.recipients():
                continue
            payload = self._build_payload(email_message)
            request = urllib.request.Request(
                url=self.api_url,
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': self.user_agent,
                },
                method='POST',
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    response.read()
            except urllib.error.HTTPError as exc:
                if self.fail_silently:
                    continue
                detail = exc.read().decode('utf-8', errors='replace')
                raise RuntimeError(self._format_error_message(detail, exc.code)) from exc
            except urllib.error.URLError as exc:
                if self.fail_silently:
                    continue
                raise RuntimeError(f'Email delivery failed: could not reach the email service ({exc.reason}).') from exc
            sent_count += 1
        return sent_count

    def _format_error_message(self, detail, status_code):
        parsed = {}
        try:
            parsed = json.loads(detail) if detail else {}
        except json.JSONDecodeError:
            parsed = {}

        error = parsed.get('error') or {}
        message = parsed.get('message') or error.get('message') or ''
        code = error.get('code') or parsed.get('code')

        if str(code) == '1010':
            return (
                'Email delivery failed: the email service blocked the request before it reached the API. '
                'This usually happens when the outgoing request is missing a required header.'
            )

        if 'You can only send testing emails to your own email address' in message:
            return (
                'Email delivery failed: the sending account is still in testing mode. '
                'Verify the sending domain for support@edumatrix.tech, then try again.'
            )

        if error.get('type') == 'invalid_from_address':
            return (
                'Email delivery failed: the sender address is not ready. '
                'Verify the sending domain for the From address.'
            )

        if message:
            return f'Email delivery failed: {message}'

        host = urlparse(self.api_url).netloc or 'email service'
        return f'Email delivery failed: {host} returned HTTP {status_code}.'

    def _build_payload(self, email_message):
        html_body = None
        text_body = email_message.body or ''

        for alternative_body, mimetype in getattr(email_message, 'alternatives', []) or []:
            if mimetype == 'text/html' and html_body is None:
                html_body = alternative_body
            elif mimetype == 'text/plain' and not text_body:
                text_body = alternative_body

        payload = {
            'from': email_message.from_email or settings.DEFAULT_FROM_EMAIL,
            'to': list(email_message.to or []),
            'subject': email_message.subject or '',
            'text': text_body,
        }
        if email_message.cc:
            payload['cc'] = list(email_message.cc)
        if email_message.bcc:
            payload['bcc'] = list(email_message.bcc)
        if html_body is not None:
            payload['html'] = html_body
        if email_message.reply_to:
            payload['reply_to'] = list(email_message.reply_to)
        if email_message.extra_headers:
            payload['headers'] = {
                key: str(value)
                for key, value in email_message.extra_headers.items()
                if value is not None
            }

        attachments = [item for item in (self._serialize_attachment(a) for a in email_message.attachments) if item]
        if attachments:
            payload['attachments'] = attachments
        return payload

    def _serialize_attachment(self, attachment):
        if isinstance(attachment, dict):
            content = attachment.get('content')
            if content is None and attachment.get('path'):
                content = attachment['path']
            if content is None:
                return None
            if isinstance(content, str) and not attachment.get('path'):
                content = content.encode('utf-8')
            payload = {
                'filename': attachment.get('filename') or 'attachment',
                'content': base64.b64encode(content).decode('ascii') if isinstance(content, (bytes, bytearray)) else content,
            }
            content_id = attachment.get('content_id') or attachment.get('contentId')
            if content_id:
                payload['content_id'] = content_id
            content_type = attachment.get('content_type') or attachment.get('contentType')
            if content_type:
                payload['content_type'] = content_type
            disposition = attachment.get('content_disposition') or attachment.get('contentDisposition')
            if disposition:
                payload['content_disposition'] = disposition
            return payload

        if isinstance(attachment, MIMEBase):
            if self.fail_silently:
                return None
            raise RuntimeError('MIMEBase attachments are not supported by this email backend.')

        if isinstance(attachment, tuple):
            filename = attachment[0]
            content = attachment[1]
        else:
            filename = getattr(attachment, 'filename', 'attachment')
            content = getattr(attachment, 'content', None)

        if content is None:
            return None

        if isinstance(content, str):
            content = content.encode('utf-8')

        return {
            'filename': filename or 'attachment',
            'content': base64.b64encode(content).decode('ascii'),
        }
