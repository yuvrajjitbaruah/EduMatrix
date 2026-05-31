import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_academic_institutions(apps, schema_editor):
    Department = apps.get_model('academics', 'Department')
    CourseClass = apps.get_model('academics', 'CourseClass')
    User = apps.get_model('accounts', 'User')

    user_institutions = {
        row[0]: row[1]
        for row in User.objects.exclude(institution__isnull=True).values_list('id', 'institution_id')
    }

    for course_class in CourseClass.objects.all().iterator():
        institution_id = user_institutions.get(course_class.teacher_id)
        if institution_id is None:
            student_institutions = list(
                course_class.students.exclude(institution__isnull=True)
                .values_list('institution_id', flat=True)
                .distinct()[:2]
            )
            if len(student_institutions) == 1:
                institution_id = student_institutions[0]

        if institution_id and course_class.institution_id != institution_id:
            course_class.institution_id = institution_id
            course_class.save(update_fields=['institution'])

    for department in Department.objects.all().iterator():
        institution_ids = set(
            CourseClass.objects.filter(department=department.name)
            .exclude(institution__isnull=True)
            .values_list('institution_id', flat=True)
        )
        if not institution_ids and department.created_by_id:
            created_by_institution = user_institutions.get(department.created_by_id)
            if created_by_institution:
                institution_ids.add(created_by_institution)
        if not institution_ids:
            institution_ids.update(
                User.objects.filter(department=department.name)
                .exclude(institution__isnull=True)
                .values_list('institution_id', flat=True)
            )

        if len(institution_ids) == 1:
            institution_id = next(iter(institution_ids))
            if department.institution_id != institution_id:
                department.institution_id = institution_id
                department.save(update_fields=['institution'])

    department_institutions = {
        row[0]: row[1]
        for row in Department.objects.exclude(institution__isnull=True).values_list('name', 'institution_id')
    }
    for course_class in CourseClass.objects.filter(institution__isnull=True).iterator():
        institution_id = department_institutions.get(course_class.department)
        if institution_id:
            course_class.institution_id = institution_id
            course_class.save(update_fields=['institution'])


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_institution_multitenancy'),
        ('academics', '0008_department'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='courseclass',
            name='institution',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='classes', to='accounts.institution'),
        ),
        migrations.AddField(
            model_name='department',
            name='institution',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='departments', to='accounts.institution'),
        ),
        migrations.AlterField(
            model_name='department',
            name='code',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='department',
            name='created_by',
            field=models.ForeignKey(blank=True, limit_choices_to=models.Q(('role__in', ['admin', 'institution_admin'])), null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_departments', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='department',
            name='name',
            field=models.CharField(max_length=100),
        ),
        migrations.RunPython(backfill_academic_institutions, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='department',
            constraint=models.UniqueConstraint(fields=('institution', 'name'), name='unique_department_name_per_institution'),
        ),
        migrations.AddConstraint(
            model_name='department',
            constraint=models.UniqueConstraint(fields=('institution', 'code'), name='unique_department_code_per_institution'),
        ),
    ]
