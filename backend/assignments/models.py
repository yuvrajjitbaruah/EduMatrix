from django.db import models
from django.conf import settings
from academics.models import CourseClass


class Assignment(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='assignments')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_assignments')
    due_date = models.DateTimeField()
    total_marks = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    allow_late = models.BooleanField(default=False)

    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['course_class', 'due_date'], name='assign_class_due_idx'),
            models.Index(fields=['created_by', 'due_date'], name='assign_creator_due_idx'),
        ]

    def __str__(self):
        return f"{self.title} — {self.course_class.name}"


class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submissions')
    file = models.FileField(upload_to='submissions/', blank=True, null=True)
    text_content = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_late = models.BooleanField(default=False)
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    feedback = models.TextField(blank=True)
    graded = models.BooleanField(default=False)
    is_plagiarized = models.BooleanField(default=False)
    plagiarism_note = models.TextField(blank=True)

    class Meta:
        unique_together = ('assignment', 'student')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['assignment', 'graded'], name='sub_assignment_graded_idx'),
            models.Index(fields=['student', 'submitted_at'], name='sub_student_submitted_idx'),
        ]

    def __str__(self):
        return f"{self.student.username} — {self.assignment.title}"
