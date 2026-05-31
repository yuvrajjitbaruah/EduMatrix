from accounts.models import User
from academics.models import CourseClass, Department


ADMIN_ROLES = {'admin', 'institution_admin'}


def is_platform_admin(user):
    return getattr(user, 'role', '') == 'admin'


def is_institution_admin(user):
    return getattr(user, 'role', '') == 'institution_admin'


def is_admin_role(user):
    return getattr(user, 'role', '') in ADMIN_ROLES


def scoped_users(user):
    qs = User.objects.select_related('institution')
    if is_platform_admin(user):
        return qs
    if is_institution_admin(user):
        return qs.filter(institution=user.institution) if user.institution_id else qs.none()
    return qs


def scoped_departments(user):
    qs = Department.objects.select_related('institution', 'created_by')
    if is_platform_admin(user):
        return qs
    if is_institution_admin(user):
        return qs.filter(institution=user.institution) if user.institution_id else qs.none()
    return qs


def scoped_classes(user):
    qs = CourseClass.objects.select_related('institution', 'teacher')
    if is_platform_admin(user):
        return qs
    if is_institution_admin(user):
        return qs.filter(institution=user.institution) if user.institution_id else qs.none()
    return qs
