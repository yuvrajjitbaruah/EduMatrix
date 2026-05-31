#!/usr/bin/env python
"""
Bootstrap or update the primary admin account from environment variables.

Required environment variables:
- EDUMATRIX_ADMIN_USERNAME
- EDUMATRIX_ADMIN_EMAIL
- EDUMATRIX_ADMIN_PASSWORD

Optional environment variables:
- EDUMATRIX_ADMIN_FIRST_NAME
- EDUMATRIX_ADMIN_LAST_NAME
"""
import os
import sys

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'edumatrix.settings')
django.setup()

from accounts.models import User


def main():
    required = [
        'EDUMATRIX_ADMIN_USERNAME',
        'EDUMATRIX_ADMIN_EMAIL',
        'EDUMATRIX_ADMIN_PASSWORD',
    ]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print('Missing required environment variables: ' + ', '.join(missing))
        print('Set them first, then run update_admin.py again.')
        return 1

    username = os.environ['EDUMATRIX_ADMIN_USERNAME'].strip()
    email = os.environ['EDUMATRIX_ADMIN_EMAIL'].strip().lower()
    password = os.environ['EDUMATRIX_ADMIN_PASSWORD']
    first_name = os.environ.get('EDUMATRIX_ADMIN_FIRST_NAME', '').strip()
    last_name = os.environ.get('EDUMATRIX_ADMIN_LAST_NAME', '').strip()

    admin = (
        User.objects.filter(is_superuser=True).first()
        or User.objects.filter(username=username).first()
        or User.objects.filter(email__iexact=email).first()
    )

    if admin:
        admin.username = username
        admin.email = email
        admin.first_name = first_name
        admin.last_name = last_name
        admin.role = 'admin'
        admin.is_staff = True
        admin.is_superuser = True
        admin.set_password(password)
        admin.save()
        print(f'Updated admin user: {admin.username}')
    else:
        admin = User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role='admin',
        )
        print(f'Created admin user: {admin.username}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
