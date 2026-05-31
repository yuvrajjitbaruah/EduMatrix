# EduMatrix Production Deployment

This project is prepared for `https://edumatrix.tech`.

## Required hosting environment

Set these variables in your hosting provider. Do not commit real secret values.

```env
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<generate-a-long-random-secret>
DJANGO_ALLOWED_HOSTS=edumatrix.tech,www.edumatrix.tech
DJANGO_CSRF_TRUSTED_ORIGINS=https://edumatrix.tech,https://www.edumatrix.tech
DJANGO_PUBLIC_SITE_URL=https://edumatrix.tech
DJANGO_SECURE_COOKIES=True
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_SECURE_HSTS_SECONDS=31536000
DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS=True
DJANGO_SECURE_HSTS_PRELOAD=True

SUPABASE_DB_NAME=postgres
SUPABASE_DB_USER=<supabase-db-user>
SUPABASE_DB_PASSWORD=<supabase-db-password>
SUPABASE_DB_HOST=<supabase-pooler-host>
SUPABASE_DB_PORT=6543
SUPABASE_URL=<supabase-project-url>
SUPABASE_ANON_KEY=<supabase-anon-key>

RESEND_API_KEY=<resend-api-key>
DJANGO_DEFAULT_FROM_EMAIL=EduMatrix <support@edumatrix.tech>

GOOGLE_AI_API_KEY=<google-ai-api-key>
SARVAM_API_KEY=<sarvam-api-key>
```

## Build command

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
```

## Start command

```bash
gunicorn edumatrix.wsgi:application --bind 0.0.0.0:$PORT --workers 3 --timeout 120
```

The included `Procfile` uses the same start command.

## DNS

Point the domain records to your hosting provider:

- `edumatrix.tech`: root/apex record required by your provider
- `www.edumatrix.tech`: CNAME to the provider target

After DNS is active, add both domains to the hosting provider and enable HTTPS.

## Resend domain

Verify `edumatrix.tech` in Resend before production email:

- From address: `support@edumatrix.tech`
- DNS records: add the DKIM/SPF records shown in Resend
- Keep `RESEND_API_KEY` only in hosting environment variables

## Supabase Auth redirect

Set Supabase Auth site URL and redirect URLs to:

- `https://edumatrix.tech`
- `https://edumatrix.tech/signup/verify-email/`
- `https://www.edumatrix.tech`
- `https://www.edumatrix.tech/signup/verify-email/`

## Launch checks

Run these before pointing traffic:

```bash
python manage.py check --deploy
python manage.py migrate --check
python manage.py test edumatrix dashboard accounts academics --verbosity 1
```
