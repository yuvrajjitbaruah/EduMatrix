from django.contrib import admin
from .models import AttendanceRecord, LeaveRequest

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'course_class', 'date', 'status')
    list_filter = ('status', 'date', 'course_class')
    date_hierarchy = 'date'

@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'start_date', 'end_date', 'status')
    list_filter = ('status',)
