import random
import string

from django.conf import settings
from django.db import models
from django.db.models import Q


def generate_class_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))


class Department(models.Model):
    institution = models.ForeignKey('accounts.Institution', on_delete=models.CASCADE, related_name='departments', blank=True, null=True)
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, null=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_departments',
        limit_choices_to=Q(role__in=['admin', 'institution_admin']),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['institution', 'name'], name='acad_dept_inst_name_idx'),
            models.Index(fields=['institution', 'is_active'], name='acad_dept_inst_active_idx'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['institution', 'name'], name='unique_department_name_per_institution'),
            models.UniqueConstraint(fields=['institution', 'code'], name='unique_department_code_per_institution'),
        ]

    def save(self, *args, **kwargs):
        self.name = self.name.strip()
        if self.code:
            self.code = self.code.upper().strip()
        else:
            self.code = None
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CourseClass(models.Model):
    institution = models.ForeignKey('accounts.Institution', on_delete=models.CASCADE, related_name='classes', blank=True, null=True)
    name = models.CharField(max_length=100)
    department = models.CharField(max_length=100)
    subject = models.CharField(max_length=100)
    semester = models.CharField(max_length=50)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        limit_choices_to={'role': 'teacher'},
        related_name='teaching_classes',
    )
    class_code = models.CharField(max_length=10, unique=True, default=generate_class_code)
    students = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        limit_choices_to={'role': 'student'},
        related_name='enrolled_classes',
        blank=True,
    )

    class Meta:
        indexes = [
            models.Index(fields=['institution', 'teacher'], name='acad_class_inst_teacher_idx'),
            models.Index(fields=['institution', 'department'], name='acad_class_inst_dept_idx'),
            models.Index(fields=['teacher', 'subject'], name='acad_class_teacher_subject_idx'),
        ]

    def __str__(self):
        return f"{self.name} - {self.subject}"


class ClassSchedule(models.Model):
    DAY_CHOICES = [
        ('1_monday', 'Monday'),
        ('2_tuesday', 'Tuesday'),
        ('3_wednesday', 'Wednesday'),
        ('4_thursday', 'Thursday'),
        ('5_friday', 'Friday'),
        ('6_saturday', 'Saturday'),
    ]
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.CharField(max_length=15, choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_number = models.CharField(max_length=50)

    class Meta:
        ordering = ['day_of_week', 'start_time']
        indexes = [
            models.Index(fields=['course_class', 'day_of_week', 'start_time'], name='acad_sched_class_day_idx'),
        ]

    def __str__(self):
        return f"{self.course_class.name} - {self.get_day_of_week_display()} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"


class Exam(models.Model):
    EXAM_TYPE_CHOICES = (
        ('mid_sem', 'Mid Sem'),
        ('end_sem', 'End Sem'),
        ('quiz', 'Quiz'),
        ('class_test', 'Class Test'),
        ('other', 'Other'),
    )
    title = models.CharField(max_length=200)
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='exams')
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPE_CHOICES, default='other')
    date = models.DateField()
    total_marks = models.PositiveIntegerField(default=100)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['course_class', 'date'], name='acad_exam_class_date_idx'),
            models.Index(fields=['date', 'exam_type'], name='acad_exam_date_type_idx'),
        ]

    def __str__(self):
        return f"{self.title} - {self.course_class.name}"


class Grade(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='grades', limit_choices_to={'role': 'student'})
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='grades')
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2)
    remarks = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        unique_together = ('student', 'exam')
        indexes = [
            models.Index(fields=['student', 'exam'], name='acad_grade_student_exam_idx'),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.exam.title} ({self.marks_obtained}/{self.exam.total_marks})"


class StudyMaterial(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='materials')
    file = models.FileField(upload_to='materials/', blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    upload_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-upload_date']
        indexes = [
            models.Index(fields=['course_class', 'upload_date'], name='acad_material_class_date_idx'),
        ]

    def __str__(self):
        return f"{self.title} - {self.course_class.name}"
