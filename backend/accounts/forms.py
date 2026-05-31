from django.contrib.auth.forms import PasswordResetForm
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .email_branding import email_branding_context


class BrandedPasswordResetForm(PasswordResetForm):
    def send_mail(
        self,
        subject_template_name,
        email_template_name,
        context,
        from_email,
        to_email,
        html_email_template_name=None,
    ):
        subject = ''.join(render_to_string(subject_template_name, context).splitlines())
        site_url = f"{context.get('protocol', 'https')}://{context.get('domain', '').strip('/')}"
        branded_context = {
            **context,
            **email_branding_context(site_url),
        }
        body = render_to_string(email_template_name, branded_context)
        email_message = EmailMultiAlternatives(subject, body, from_email, [to_email])
        if html_email_template_name:
            html_email = render_to_string(html_email_template_name, branded_context)
            email_message.attach_alternative(html_email, 'text/html')
        email_message.send()
