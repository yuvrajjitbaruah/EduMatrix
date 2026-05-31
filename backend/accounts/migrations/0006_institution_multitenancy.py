import django.db.models.deletion
from django.db import migrations, models
from django.utils import timezone


ALLOWED_INSTITUTION_DOMAIN_SUFFIXES = (
    '.edu',
    '.edu.in',
    '.ac.in',
    '.ac',
)


def normalize_domain(domain):
    domain = (domain or '').strip().lower()
    if domain.startswith('www.'):
        domain = domain[4:]
    return domain


def domain_from_email(email):
    return normalize_domain((email or '').partition('@')[2])


def domain_is_allowed(domain):
    normalized = normalize_domain(domain)
    return any(normalized.endswith(suffix) for suffix in ALLOWED_INSTITUTION_DOMAIN_SUFFIXES)


def infer_name_from_domain(domain):
    normalized = normalize_domain(domain)
    for suffix in sorted(ALLOWED_INSTITUTION_DOMAIN_SUFFIXES, key=len, reverse=True):
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    label = normalized.split('.')[-1] if normalized else 'Institution'
    label = label.replace('-', ' ').replace('_', ' ').strip()
    return label.title() or 'Institution'


def backfill_institutions(apps, schema_editor):
    Institution = apps.get_model('accounts', 'Institution')
    PlatformInquiry = apps.get_model('accounts', 'PlatformInquiry')
    User = apps.get_model('accounts', 'User')

    now = timezone.now()

    def provision_from_email(email, preferred_name=''):
        domain = domain_from_email(email)
        institution = None
        if domain and domain_is_allowed(domain):
            institution, _ = Institution.objects.get_or_create(
                domain=domain,
                defaults={
                    'name': preferred_name.strip() or infer_name_from_domain(domain),
                    'verification_status': 'verified',
                    'verified_at': now,
                },
            )
            updated_fields = []
            preferred_name = preferred_name.strip()
            if preferred_name and institution.name != preferred_name:
                institution.name = preferred_name
                updated_fields.append('name')
            if institution.verification_status != 'verified':
                institution.verification_status = 'verified'
                updated_fields.append('verification_status')
            if institution.verified_at is None:
                institution.verified_at = now
                updated_fields.append('verified_at')
            if updated_fields:
                institution.save(update_fields=updated_fields)
        return institution, domain

    for user in User.objects.exclude(email='').iterator():
        if user.role == 'admin':
            continue
        institution, _domain = provision_from_email(user.email, '')
        if institution and user.institution_id != institution.id:
            user.institution_id = institution.id
            user.save(update_fields=['institution'])

    for inquiry in PlatformInquiry.objects.exclude(email='').iterator():
        institution, domain = provision_from_email(inquiry.email, inquiry.institute_name)
        updated_fields = []
        if domain and inquiry.institution_domain != domain:
            inquiry.institution_domain = domain
            updated_fields.append('institution_domain')
        if institution and inquiry.linked_institution_id != institution.id:
            inquiry.linked_institution_id = institution.id
            updated_fields.append('linked_institution')
        if institution and inquiry.verification_status != 'verified':
            inquiry.verification_status = 'verified'
            updated_fields.append('verification_status')
        if updated_fields:
            inquiry.save(update_fields=updated_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_user_supabase_user_id'),
    ]

    operations = [
        migrations.CreateModel(
            name='Institution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=180)),
                ('domain', models.CharField(max_length=180, unique=True)),
                ('institution_type', models.CharField(choices=[('institution', 'Institution'), ('school', 'School'), ('college', 'College'), ('university', 'University')], default='institution', max_length=30)),
                ('verification_status', models.CharField(choices=[('pending', 'Pending'), ('verified', 'Verified'), ('rejected', 'Rejected')], default='verified', max_length=20)),
                ('verified_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.AddField(
            model_name='platforminquiry',
            name='institution_domain',
            field=models.CharField(blank=True, default='', max_length=180),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='platforminquiry',
            name='linked_institution',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='inquiries', to='accounts.institution'),
        ),
        migrations.AddField(
            model_name='platforminquiry',
            name='verification_status',
            field=models.CharField(choices=[('pending', 'Pending'), ('verified', 'Verified'), ('rejected', 'Rejected')], default='pending', max_length=20),
        ),
        migrations.AddField(
            model_name='user',
            name='institution',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='accounts.institution'),
        ),
        migrations.AlterField(
            model_name='emailverificationotp',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('institution_admin', 'Institution Admin'), ('teacher', 'Teacher'), ('student', 'Student')], max_length=20),
        ),
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('institution_admin', 'Institution Admin'), ('teacher', 'Teacher'), ('student', 'Student')], default='student', max_length=20),
        ),
        migrations.RunPython(backfill_institutions, migrations.RunPython.noop),
    ]
