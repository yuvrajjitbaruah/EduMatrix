from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


ALLOWED_INSTITUTION_DOMAIN_SUFFIXES = (
    '.edu',
    '.edu.in',
    '.ac.in',
    '.ac',
)


class Institution(models.Model):
    TYPE_CHOICES = (
        ('institution', 'Institution'),
        ('school', 'School'),
        ('college', 'College'),
        ('university', 'University'),
    )
    VERIFICATION_CHOICES = (
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )

    name = models.CharField(max_length=180)
    domain = models.CharField(max_length=180, unique=True)
    institution_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='institution')
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='verified')
    verified_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['verification_status', 'created_at'], name='acct_inst_verify_created_idx'),
        ]

    @classmethod
    def normalize_domain(cls, domain):
        domain = (domain or '').strip().lower()
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain

    @classmethod
    def domain_from_email(cls, email):
        return cls.normalize_domain((email or '').partition('@')[2])

    @classmethod
    def domain_is_allowed(cls, domain):
        normalized = cls.normalize_domain(domain)
        return any(normalized.endswith(suffix) for suffix in ALLOWED_INSTITUTION_DOMAIN_SUFFIXES)

    @classmethod
    def infer_name_from_domain(cls, domain):
        normalized = cls.normalize_domain(domain)
        for suffix in sorted(ALLOWED_INSTITUTION_DOMAIN_SUFFIXES, key=len, reverse=True):
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
                break
        label = normalized.split('.')[-1] if normalized else 'Institution'
        label = label.replace('-', ' ').replace('_', ' ').strip()
        return label.title() or 'Institution'

    @classmethod
    def provision_for_email(cls, email, *, preferred_name=''):
        domain = cls.domain_from_email(email)
        if not cls.domain_is_allowed(domain):
            return None

        institution, created = cls.objects.get_or_create(
            domain=domain,
            defaults={
                'name': preferred_name.strip() or cls.infer_name_from_domain(domain),
                'verification_status': 'verified',
                'verified_at': timezone.now(),
            },
        )
        updated_fields = []
        if preferred_name and institution.name != preferred_name.strip():
            institution.name = preferred_name.strip()
            updated_fields.append('name')
        if institution.verification_status != 'verified':
            institution.verification_status = 'verified'
            institution.verified_at = timezone.now()
            updated_fields.extend(['verification_status', 'verified_at'])
        elif created and institution.verified_at is None:
            institution.verified_at = timezone.now()
            updated_fields.append('verified_at')
        if updated_fields:
            institution.save(update_fields=updated_fields)
        return institution

    def __str__(self):
        return f"{self.name} ({self.domain})"


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('institution_admin', 'Institution Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    )

    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    institution = models.ForeignKey('Institution', on_delete=models.SET_NULL, related_name='users', blank=True, null=True)
    department = models.CharField(max_length=100, blank=True, null=True)
    profile_picture = models.FileField(upload_to='profiles/', blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    roll_no = models.CharField(max_length=50, blank=True, null=True, unique=True)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    supabase_user_id = models.CharField(max_length=80, blank=True, null=True, unique=True)

    class Meta(AbstractUser.Meta):
        indexes = [
            models.Index(fields=['role', 'institution'], name='acct_user_role_inst_idx'),
            models.Index(fields=['institution', 'date_joined'], name='acct_user_inst_joined_idx'),
            models.Index(fields=['email'], name='acct_user_email_idx'),
        ]

    @property
    def is_platform_admin(self):
        return self.role == 'admin'

    @property
    def is_institution_admin(self):
        return self.role == 'institution_admin'

    @property
    def can_manage_institution(self):
        return self.role in {'admin', 'institution_admin'}

    @property
    def institution_label(self):
        return self.institution.name if self.institution_id else ''

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"


class EmailVerificationOTP(models.Model):
    PURPOSE_CHOICES = (
        ('signup', 'Signup'),
    )

    email = models.EmailField()
    role = models.CharField(max_length=20, choices=User.ROLE_CHOICES)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default='signup')
    code_hash = models.CharField(max_length=128)
    payload = models.JSONField(default=dict)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['email', 'role', 'purpose', 'is_used']),
            models.Index(fields=['expires_at', 'is_used'], name='acct_otp_exp_used_idx'),
        ]

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def mark_used(self):
        self.is_used = True
        self.used_at = timezone.now()
        self.save(update_fields=['is_used', 'used_at'])

    def __str__(self):
        return f"{self.email} {self.role} {self.purpose}"


class PlatformInquiry(models.Model):
    STATUS_CHOICES = (
        ('new', 'New'),
        ('contacted', 'Contacted'),
        ('onboarded', 'Onboarded'),
        ('closed', 'Closed'),
    )
    VERIFICATION_CHOICES = (
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    )

    institute_name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=120)
    email = models.EmailField()
    institution_domain = models.CharField(max_length=180, blank=True)
    linked_institution = models.ForeignKey('Institution', on_delete=models.SET_NULL, related_name='inquiries', blank=True, null=True)
    verification_status = models.CharField(max_length=20, choices=VERIFICATION_CHOICES, default='pending')
    phone = models.CharField(max_length=30, blank=True)
    student_count = models.CharField(max_length=50, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'], name='acct_inq_status_created_idx'),
            models.Index(fields=['verification_status', 'created_at'], name='acct_inq_verify_created_idx'),
            models.Index(fields=['institution_domain'], name='acct_inquiry_domain_idx'),
            models.Index(fields=['linked_institution', 'status'], name='acct_inquiry_inst_status_idx'),
            models.Index(fields=['email'], name='acct_inquiry_email_idx'),
        ]

    def __str__(self):
        return f"{self.institute_name} - {self.contact_name}"
