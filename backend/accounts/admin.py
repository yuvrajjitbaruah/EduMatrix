from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import EmailVerificationOTP, Institution, PlatformInquiry, User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'first_name', 'last_name', 'role', 'institution', 'department', 'email_verified_at', 'supabase_user_id', 'is_staff')
    list_filter = ('role', 'institution', 'department', 'email_verified_at', 'is_staff')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('EduMatrix', {'fields': ('role', 'institution', 'department', 'email_verified_at', 'supabase_user_id')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('EduMatrix', {'fields': ('role', 'institution', 'department')}),
    )


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = ('name', 'domain', 'institution_type', 'verification_status', 'verified_at', 'created_at')
    list_filter = ('institution_type', 'verification_status', 'created_at')
    search_fields = ('name', 'domain')


@admin.register(EmailVerificationOTP)
class EmailVerificationOTPAdmin(admin.ModelAdmin):
    list_display = ('email', 'role', 'purpose', 'is_used', 'attempts', 'expires_at', 'created_at')
    list_filter = ('role', 'purpose', 'is_used', 'created_at')
    search_fields = ('email',)
    readonly_fields = ('code_hash', 'payload', 'created_at', 'used_at')


@admin.register(PlatformInquiry)
class PlatformInquiryAdmin(admin.ModelAdmin):
    list_display = ('institute_name', 'institution_domain', 'contact_name', 'email', 'verification_status', 'status', 'created_at')
    list_filter = ('verification_status', 'status', 'created_at')
    search_fields = ('institute_name', 'institution_domain', 'contact_name', 'email', 'phone')
