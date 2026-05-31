from django.db import models
from django.conf import settings
from academics.models import CourseClass

class AttendanceRecord(models.Model):
    STATUS_CHOICES = (
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance_records')
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)

    class Meta:
        unique_together = ('student', 'course_class', 'date')
        indexes = [
            models.Index(fields=['course_class', 'date'], name='att_record_class_date_idx'),
            models.Index(fields=['student', 'date'], name='att_record_student_date_idx'),
            models.Index(fields=['date', 'status'], name='att_record_date_status_idx'),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.course_class.name} - {self.date} ({self.status})"

class LeaveRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leave_requests')
    teachers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, 
        limit_choices_to={'role': 'teacher'},
        related_name='received_leave_requests',
        blank=True
    )
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    class Meta:
        indexes = [
            models.Index(fields=['student', 'status'], name='att_leave_student_status_idx'),
            models.Index(fields=['status', 'start_date'], name='att_leave_status_start_idx'),
        ]
    
    def __str__(self):
        return f"{self.student.username} - {self.start_date} to {self.end_date}"
