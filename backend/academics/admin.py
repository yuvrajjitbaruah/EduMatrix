from django.contrib import admin
from .models import CourseClass, Department


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'institution', 'code', 'is_active', 'created_by', 'created_at')
    list_filter = ('institution', 'is_active', 'created_at')
    search_fields = ('name', 'institution__name', 'code', 'description')

@admin.register(CourseClass)
class CourseClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'institution', 'subject', 'department', 'semester', 'teacher')
    list_filter = ('institution', 'department', 'semester')
    filter_horizontal = ('students',)
