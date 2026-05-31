EMAIL_LOGO_URL = 'https://edumatrix.tech/logo.png'


def email_branding_context(site_url=''):
    return {
        'email_logo_url': EMAIL_LOGO_URL,
    }


def build_inline_logo_attachment():
    return None
