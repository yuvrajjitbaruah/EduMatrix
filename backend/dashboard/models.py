from django.db import models
from django.conf import settings


class Notice(models.Model):
    TARGET_CHOICES = (
        ('all', 'All Users'),
        ('student', 'Students Only'),
        ('teacher', 'Teachers Only'),
    )
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='authored_notices')
    target_role = models.CharField(max_length=20, choices=TARGET_CHOICES, default='all')
    target_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='class_notices', blank=True, null=True, help_text='Select if this is a classroom notice')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='normal')
    is_pinned = models.BooleanField(default=False)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['target_role', 'created_at'], name='dash_notice_role_created_idx'),
            models.Index(fields=['target_class', 'created_at'], name='dash_notice_class_date_idx'),
            models.Index(fields=['priority', 'created_at'], name='dash_notice_priority_idx'),
        ]

    def __str__(self):
        return self.title


class Event(models.Model):
    EVENT_TYPE_CHOICES = (
        ('exam', 'Exam'),
        ('assignment', 'Assignment Due'),
        ('holiday', 'Holiday'),
        ('meeting', 'Meeting'),
        ('custom', 'Custom'),
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event_date = models.DateField()
    event_type = models.CharField(max_length=20, choices=EVENT_TYPE_CHOICES, default='custom')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_events')
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='events', blank=True, null=True)
    attendees = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='attending_events', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['event_date']
        indexes = [
            models.Index(fields=['event_date', 'course_class'], name='dash_event_date_class_idx'),
            models.Index(fields=['course_class', 'event_date'], name='dash_event_class_date_idx'),
        ]

    def __str__(self):
        return f"{self.title} ({self.event_date})"


class FeeRecord(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('overdue', 'Overdue'),
    )
    PAYMENT_METHODS = (
        ('cash', 'Cash'),
        ('online', 'Online'),
        ('bank', 'Bank Transfer'),
        ('upi', 'UPI'),
        ('other', 'Other'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fee_records', limit_choices_to={'role': 'student'})
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    paid_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    receipt_no = models.CharField(max_length=50, unique=True, blank=True, null=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, blank=True, null=True)

    class Meta:
        ordering = ['-due_date']
        indexes = [
            models.Index(fields=['student', 'status', 'due_date'], name='dash_fee_stu_stat_due_idx'),
            models.Index(fields=['status', 'due_date'], name='dash_fee_status_due_idx'),
        ]

    def __str__(self):
        return f"{self.student.username} — {self.title} ({self.status})"


class LibraryResource(models.Model):
    CATEGORY_CHOICES = (
        ('textbook', 'Textbook'),
        ('notes', 'Notes'),
        ('video', 'Video'),
        ('paper', 'Research Paper'),
        ('other', 'Other'),
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    file = models.FileField(upload_to='library/', blank=True, null=True)
    url = models.URLField(blank=True, null=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_resources')
    upload_date = models.DateTimeField(auto_now_add=True)
    download_count = models.PositiveIntegerField(default=0)
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='library_resources', blank=True, null=True)
    available_copies = models.PositiveIntegerField(default=1, help_text="Number of physical copies available for issue. Use 0 for purely digital resources.")

    class Meta:
        ordering = ['-upload_date']

    def __str__(self):
        return self.title


class BookIssue(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending Approval'),
        ('issued', 'Issued'),
        ('returned', 'Returned'),
        ('overdue', 'Overdue'),
    )
    resource = models.ForeignKey(LibraryResource, on_delete=models.CASCADE, related_name='issues')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='borrowed_books', limit_choices_to={'role': 'student'})
    issue_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    return_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f"{self.student.username} - {self.resource.title}"


BADGE_CHOICES = (
    ('first_login', '🎓 First Login'),
    ('perfect_week', '⭐ Perfect Week'),
    ('streak_7', '🔥 7-Day Streak'),
    ('streak_30', '💎 30-Day Streak'),
    ('top_scorer', '🏆 Top Scorer'),
    ('helper', '🤝 Helpful Peer'),
    ('bookworm', '📚 Bookworm'),
    ('early_bird', '🐦 Early Bird'),
    ('perfect_attendance', '✅ Perfect Attendance'),
    ('assignment_ace', '📝 Assignment Ace'),
)


class Achievement(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='achievements', limit_choices_to={'role': 'student'})
    badge_type = models.CharField(max_length=30, choices=BADGE_CHOICES)
    earned_at = models.DateTimeField(auto_now_add=True)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ('student', 'badge_type')
        ordering = ['-earned_at']

    def __str__(self):
        return f"{self.student.username} — {self.get_badge_type_display()}"


class StudentXP(models.Model):
    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='xp_profile', limit_choices_to={'role': 'student'})
    total_xp = models.PositiveIntegerField(default=0)
    level = models.PositiveIntegerField(default=1)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.student.username} — Level {self.level} ({self.total_xp} XP)"


class Poll(models.Model):
    question = models.CharField(max_length=300)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_polls')
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='polls', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.question

    @property
    def total_votes(self):
        return sum(o.vote_count for o in self.options.all())


class PollOption(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE, related_name='options')
    text = models.CharField(max_length=200)

    @property
    def vote_count(self):
        return self.votes.count()

    def __str__(self):
        return f"{self.text} ({self.vote_count} votes)"


class PollVote(models.Model):
    option = models.ForeignKey(PollOption, on_delete=models.CASCADE, related_name='votes')
    voter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='poll_votes')
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('option', 'voter')


class TodoItem(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='todos')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    is_done = models.BooleanField(default=False)
    due_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['is_done', '-priority', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_done', 'due_date'], name='dash_todo_user_done_due_idx'),
            models.Index(fields=['user', 'priority'], name='dash_todo_user_priority_idx'),
        ]

    def __str__(self):
        return f"{'✓' if self.is_done else '○'} {self.title}"


class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ('login', '🔑 Logged in'),
        ('submit', '📤 Submitted assignment'),
        ('grade', '📊 Graded work'),
        ('forum_post', '💬 Posted in forum'),
        ('message', '✉️ Sent message'),
        ('attendance', '✅ Attendance marked'),
        ('notice', '📣 Posted notice'),
        ('resource', '📁 Uploaded resource'),
        ('event', '📅 Created event'),
        ('other', '📋 Activity'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at'], name='dash_activity_user_created_idx'),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.get_action_display()}"


class HelpFAQ(models.Model):
    question = models.CharField(max_length=300)
    answer = models.TextField()
    category = models.CharField(max_length=50, default='General')
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.question


class Note(models.Model):
    COLOR_CHOICES = (
        ('indigo', 'Indigo'),
        ('rose', 'Rose'),
        ('emerald', 'Emerald'),
        ('amber', 'Amber'),
        ('cyan', 'Cyan'),
        ('purple', 'Purple'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notes')
    title = models.CharField(max_length=200)
    content = models.TextField()
    color = models.CharField(max_length=20, choices=COLOR_CHOICES, default='indigo')
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_pinned', '-updated_at']

    def __str__(self):
        return f"{self.title} — {self.user.username}"


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=200, default='New Chat')
    messages_json = models.TextField(default='[]')  # Store as JSON string
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'updated_at'], name='dash_chat_user_updated_idx'),
        ]

    def __str__(self):
        return f"{self.title} — {self.user.username}"


# ============================
# HOMEWORK DIARY
# ============================

class HomeworkEntry(models.Model):
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='homework_entries')
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='assigned_homework', limit_choices_to={'role': 'teacher'})
    description = models.TextField()
    assigned_date = models.DateField(auto_now_add=True)
    due_date = models.DateField()
    is_important = models.BooleanField(default=False)

    class Meta:
        ordering = ['-assigned_date']
        indexes = [
            models.Index(fields=['course_class', 'due_date'], name='dash_homework_class_due_idx'),
            models.Index(fields=['teacher', 'due_date'], name='dash_homework_teacher_due_idx'),
        ]

    def __str__(self):
        return f"{self.course_class.subject} — Due {self.due_date}"


# ============================
# DISCIPLINARY RECORDS
# ============================

class DisciplinaryRecord(models.Model):
    SEVERITY_CHOICES = (
        ('minor', 'Minor'),
        ('moderate', 'Moderate'),
        ('major', 'Major'),
        ('critical', 'Critical'),
    )
    INCIDENT_TYPES = (
        ('tardiness', 'Tardiness'),
        ('disruption', 'Class Disruption'),
        ('cheating', 'Academic Dishonesty'),
        ('bullying', 'Bullying'),
        ('vandalism', 'Vandalism'),
        ('dress_code', 'Dress Code Violation'),
        ('misconduct', 'General Misconduct'),
        ('other', 'Other'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='discipline_records', limit_choices_to={'role': 'student'})
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='filed_discipline_records')
    incident_type = models.CharField(max_length=20, choices=INCIDENT_TYPES, default='other')
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='minor')
    action_taken = models.TextField(blank=True)
    date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.student.username} — {self.get_incident_type_display()} ({self.date})"


# ============================
# PARENT / GUARDIAN INFO
# ============================

class ParentGuardian(models.Model):
    RELATIONSHIP_CHOICES = (
        ('father', 'Father'),
        ('mother', 'Mother'),
        ('guardian', 'Guardian'),
        ('sibling', 'Sibling'),
        ('other', 'Other'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='guardians', limit_choices_to={'role': 'student'})
    name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=20, choices=RELATIONSHIP_CHOICES, default='father')
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    occupation = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_relationship_display()}) → {self.student.username}"


# ============================
# HEALTH RECORDS
# ============================

class HealthRecord(models.Model):
    BLOOD_GROUPS = (
        ('A+', 'A+'), ('A-', 'A-'),
        ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'),
        ('O+', 'O+'), ('O-', 'O-'),
    )
    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='health_record', limit_choices_to={'role': 'student'})
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUPS, blank=True)
    allergies = models.TextField(blank=True, help_text="Comma separated list of allergies")
    medical_conditions = models.TextField(blank=True)
    medications = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=20, blank=True)
    insurance_info = models.CharField(max_length=200, blank=True)
    last_checkup = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"Health Record — {self.student.username}"


# ============================
# TRANSPORT / BUS MANAGEMENT
# ============================

class BusRoute(models.Model):
    route_name = models.CharField(max_length=200)
    driver_name = models.CharField(max_length=200)
    driver_phone = models.CharField(max_length=20)
    vehicle_number = models.CharField(max_length=50)
    capacity = models.PositiveIntegerField(default=40)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.route_name} ({self.vehicle_number})"

    @property
    def occupancy(self):
        return self.passengers.count()


class StudentTransport(models.Model):
    student = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transport', limit_choices_to={'role': 'student'})
    route = models.ForeignKey(BusRoute, on_delete=models.CASCADE, related_name='passengers')
    pickup_point = models.CharField(max_length=200)
    pickup_time = models.TimeField()
    drop_time = models.TimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.student.username} → {self.route.route_name}"


# ============================
# HOSTEL MANAGEMENT
# ============================

class HostelRoom(models.Model):
    ROOM_TYPES = (
        ('single', 'Single'),
        ('double', 'Double'),
        ('triple', 'Triple'),
        ('dormitory', 'Dormitory'),
    )
    building = models.CharField(max_length=100)
    room_number = models.CharField(max_length=20)
    floor = models.PositiveIntegerField(default=0)
    capacity = models.PositiveIntegerField(default=2)
    room_type = models.CharField(max_length=10, choices=ROOM_TYPES, default='double')
    has_ac = models.BooleanField(default=False)
    has_attached_bath = models.BooleanField(default=False)

    class Meta:
        unique_together = ('building', 'room_number')

    def __str__(self):
        return f"{self.building} - Room {self.room_number}"

    @property
    def current_occupancy(self):
        return self.allocations.filter(check_out__isnull=True).count()

    @property
    def is_full(self):
        return self.current_occupancy >= self.capacity


class HostelAllocation(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='hostel_allocations', limit_choices_to={'role': 'student'})
    room = models.ForeignKey(HostelRoom, on_delete=models.CASCADE, related_name='allocations')
    check_in = models.DateField()
    check_out = models.DateField(blank=True, null=True)
    monthly_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-check_in']

    def __str__(self):
        return f"{self.student.username} → {self.room}"


# ============================
# INVENTORY / EQUIPMENT
# ============================

class InventoryItem(models.Model):
    CONDITION_CHOICES = (
        ('new', 'New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    )
    CATEGORY_CHOICES = (
        ('electronics', 'Electronics'),
        ('furniture', 'Furniture'),
        ('lab_equipment', 'Lab Equipment'),
        ('sports', 'Sports Equipment'),
        ('stationery', 'Stationery'),
        ('other', 'Other'),
    )
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    location = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(max_length=10, choices=CONDITION_CHOICES, default='good')
    purchase_date = models.DateField(blank=True, null=True)
    purchase_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    last_maintained = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['category', 'condition'], name='dash_inv_cat_cond_idx'),
            models.Index(fields=['location', 'category'], name='dash_inv_loc_cat_idx'),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()}) × {self.quantity}"


# ============================
# VISITOR LOG
# ============================

class VisitorLog(models.Model):
    visitor_name = models.CharField(max_length=200)
    purpose = models.CharField(max_length=300)
    contact_number = models.CharField(max_length=20)
    visiting_whom = models.CharField(max_length=200)
    id_proof = models.CharField(max_length=100, blank=True)
    in_time = models.DateTimeField(auto_now_add=True)
    out_time = models.DateTimeField(blank=True, null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_visitors')
    photo = models.FileField(upload_to='visitors/', blank=True, null=True)

    class Meta:
        ordering = ['-in_time']
        indexes = [
            models.Index(fields=['out_time', 'in_time'], name='dash_visitor_out_in_idx'),
            models.Index(fields=['approved_by', 'in_time'], name='dash_visitor_approver_idx'),
        ]

    def __str__(self):
        return f"{self.visitor_name} → {self.visiting_whom} ({self.in_time.strftime('%d %b %Y')})"


# ============================
# CERTIFICATE GENERATOR
# ============================

class Certificate(models.Model):
    CERT_TYPES = (
        ('merit', 'Merit Certificate'),
        ('participation', 'Participation Certificate'),
        ('achievement', 'Achievement Award'),
        ('completion', 'Course Completion'),
        ('sports', 'Sports Achievement'),
        ('custom', 'Custom'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='certificates', limit_choices_to={'role': 'student'})
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    certificate_type = models.CharField(max_length=20, choices=CERT_TYPES, default='merit')
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='issued_certificates')
    issued_date = models.DateField(auto_now_add=True)
    serial_number = models.CharField(max_length=50, unique=True, blank=True)

    class Meta:
        ordering = ['-issued_date']

    def save(self, *args, **kwargs):
        if not self.serial_number:
            import random, string
            self.serial_number = 'CERT-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} → {self.student.username}"


# ============================
# COMPLAINT / GRIEVANCE SYSTEM
# ============================

class Complaint(models.Model):
    STATUS_CHOICES = (
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    )
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    )
    CATEGORY_CHOICES = (
        ('academic', 'Academic'),
        ('infrastructure', 'Infrastructure'),
        ('hostel', 'Hostel'),
        ('transport', 'Transport'),
        ('faculty', 'Faculty'),
        ('ragging', 'Ragging'),
        ('other', 'Other'),
    )
    filed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='complaints')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    subject = models.CharField(max_length=300)
    description = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_complaints')
    resolution = models.TextField(blank=True)
    filed_date = models.DateTimeField(auto_now_add=True)
    resolved_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-filed_date']
        indexes = [
            models.Index(fields=['status', 'filed_by'], name='dash_complaint_status_file_idx'),
            models.Index(fields=['assigned_to', 'status'], name='dash_complaint_assignee_idx'),
            models.Index(fields=['priority', 'status'], name='dash_complaint_priority_idx'),
        ]

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject}"


# ============================
# SCHOLARSHIP MANAGEMENT
# ============================

class Scholarship(models.Model):
    name = models.CharField(max_length=300)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    criteria = models.TextField(help_text="Eligibility criteria")
    deadline = models.DateField()
    department = models.CharField(max_length=100, blank=True)
    total_slots = models.PositiveIntegerField(default=10)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['deadline']
        indexes = [
            models.Index(fields=['is_active', 'deadline'], name='dash_scholar_active_dead_idx'),
            models.Index(fields=['department', 'deadline'], name='dash_scholar_dept_dead_idx'),
        ]

    def __str__(self):
        return f"{self.name} (₹{self.amount})"

    @property
    def applications_count(self):
        return self.applications.count()


class ScholarshipApplication(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('waitlisted', 'Waitlisted'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scholarship_applications', limit_choices_to={'role': 'student'})
    scholarship = models.ForeignKey(Scholarship, on_delete=models.CASCADE, related_name='applications')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    applied_date = models.DateTimeField(auto_now_add=True)
    statement = models.TextField(help_text="Why do you deserve this scholarship?")
    gpa = models.DecimalField(max_digits=4, decimal_places=2, blank=True, null=True)
    remarks = models.TextField(blank=True)

    class Meta:
        unique_together = ('student', 'scholarship')
        ordering = ['-applied_date']
        indexes = [
            models.Index(fields=['status', 'applied_date'], name='dash_sch_app_status_date_idx'),
        ]

    def __str__(self):
        return f"{self.student.username} → {self.scholarship.name}"


# ============================
# EXAM SEATING
# ============================

class ExamSeat(models.Model):
    exam = models.ForeignKey('academics.Exam', on_delete=models.CASCADE, related_name='seating')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exam_seats', limit_choices_to={'role': 'student'})
    room = models.CharField(max_length=50)
    seat_number = models.CharField(max_length=20)

    class Meta:
        unique_together = ('exam', 'student')
        ordering = ['room', 'seat_number']
        indexes = [
            models.Index(fields=['room', 'seat_number'], name='dash_examseat_room_idx'),
        ]

    def __str__(self):
        return f"{self.student.username} — {self.exam.title} — Room {self.room}, Seat {self.seat_number}"


# ============================
# CLASS RECORDINGS
# ============================

class ClassRecording(models.Model):
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='recordings')
    title = models.CharField(max_length=300)
    video_url = models.URLField()
    description = models.TextField(blank=True)
    recording_date = models.DateField()
    duration_minutes = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_recordings')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-recording_date']
        indexes = [
            models.Index(fields=['course_class', 'recording_date'], name='dash_record_class_date_idx'),
            models.Index(fields=['uploaded_by', 'recording_date'], name='dash_record_uploader_date_idx'),
        ]

    def __str__(self):
        return f"{self.title} ({self.course_class.subject})"


# ============================
# STUDY GROUPS
# ============================

class StudyGroup(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_study_groups')
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='study_groups', blank=True)
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='study_groups', blank=True, null=True)
    max_members = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['course_class', 'created_at'], name='dash_group_class_created_idx'),
            models.Index(fields=['created_by', 'created_at'], name='dash_group_creator_date_idx'),
        ]

    def __str__(self):
        return self.name


class StudyGroupMessage(models.Model):
    group = models.ForeignKey(StudyGroup, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='group_messages')
    content = models.TextField()
    file = models.FileField(upload_to='group_files/', blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['group', 'timestamp'], name='dash_group_msg_time_idx'),
            models.Index(fields=['sender', 'timestamp'], name='dash_group_msg_sender_idx'),
        ]

    def __str__(self):
        return f"{self.sender.username} in {self.group.name}"


# ============================
# SKILL TRACKER
# ============================

class SkillBadge(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=10, default='⭐')
    category = models.CharField(max_length=50, default='General')
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.icon} {self.name}"


class StudentSkill(models.Model):
    LEVEL_CHOICES = (
        (1, 'Beginner'),
        (2, 'Intermediate'),
        (3, 'Advanced'),
        (4, 'Expert'),
        (5, 'Master'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='skills', limit_choices_to={'role': 'student'})
    skill = models.ForeignKey(SkillBadge, on_delete=models.CASCADE, related_name='student_skills')
    level = models.IntegerField(choices=LEVEL_CHOICES, default=1)
    endorsed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='endorsed_skills')
    date_earned = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'skill')

    def __str__(self):
        return f"{self.student.username} — {self.skill.name} (Level {self.level})"


# ============================
# COURSE FEEDBACK
# ============================

class CourseFeedback(models.Model):
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='feedbacks')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_feedbacks', limit_choices_to={'role': 'student'})
    rating = models.PositiveIntegerField(default=5, help_text="Rating 1-5")
    review = models.TextField(blank=True)
    is_anonymous = models.BooleanField(default=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('course_class', 'student')
        ordering = ['-submitted_at']
        indexes = [
            models.Index(fields=['course_class', 'submitted_at'], name='dash_feedback_class_date_idx'),
            models.Index(fields=['student', 'submitted_at'], name='dash_feedback_student_idx'),
        ]

    def __str__(self):
        return f"{'Anonymous' if self.is_anonymous else self.student.username} → {self.course_class.name} ({self.rating}★)"


# ============================
# CIRCULARS / MEMOS
# ============================

class Circular(models.Model):
    title = models.CharField(max_length=300)
    content = models.TextField()
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='issued_circulars')
    department = models.CharField(max_length=100, blank=True)
    issued_date = models.DateTimeField(auto_now_add=True)
    is_urgent = models.BooleanField(default=False)
    attachment = models.FileField(upload_to='circulars/', blank=True, null=True)

    class Meta:
        ordering = ['-issued_date']
        indexes = [
            models.Index(fields=['department', 'issued_date'], name='dash_circular_dept_date_idx'),
            models.Index(fields=['is_urgent', 'issued_date'], name='dash_circular_urgent_idx'),
        ]

    def __str__(self):
        return self.title


class CircularReceipt(models.Model):
    circular = models.ForeignKey(Circular, on_delete=models.CASCADE, related_name='receipts')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='circular_receipts')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('circular', 'user')
        indexes = [
            models.Index(fields=['user', 'read_at'], name='dash_circ_receipt_user_idx'),
        ]


# ============================
# THOUGHT OF THE DAY
# ============================

class ThoughtOfDay(models.Model):
    quote = models.TextField()
    author = models.CharField(max_length=200)
    date = models.DateField(unique=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitted_thoughts')

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"\"{self.quote[:50]}...\" — {self.author}"


# ============================
# FLASHCARD SYSTEM
# ============================

class FlashcardDeck(models.Model):
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='flashcard_decks')
    course_class = models.ForeignKey('academics.CourseClass', on_delete=models.CASCADE, related_name='flashcard_decks', blank=True, null=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    @property
    def card_count(self):
        return self.cards.count()


class Flashcard(models.Model):
    DIFFICULTY_CHOICES = (
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    )
    deck = models.ForeignKey(FlashcardDeck, on_delete=models.CASCADE, related_name='cards')
    front = models.TextField(help_text="Question or term")
    back = models.TextField(help_text="Answer or definition")
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')

    def __str__(self):
        return f"{self.front[:40]}..."


# ============================
# STUDENT DIARY / JOURNAL
# ============================

class DiaryEntry(models.Model):
    MOOD_CHOICES = (
        ('😊', 'Happy'),
        ('😐', 'Neutral'),
        ('😔', 'Sad'),
        ('😤', 'Frustrated'),
        ('🤩', 'Excited'),
        ('😴', 'Tired'),
        ('🤔', 'Thoughtful'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='diary_entries')
    title = models.CharField(max_length=200)
    content = models.TextField()
    mood = models.CharField(max_length=5, choices=MOOD_CHOICES, default='😊')
    date = models.DateField(auto_now_add=True)
    is_private = models.BooleanField(default=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.mood} {self.title} ({self.date})"


# ============================
# KANBAN BOARD
# ============================

class KanbanBoard(models.Model):
    title = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='kanban_boards')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class KanbanColumn(models.Model):
    board = models.ForeignKey(KanbanBoard, on_delete=models.CASCADE, related_name='columns')
    title = models.CharField(max_length=100)
    position = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default='indigo')

    class Meta:
        ordering = ['position']

    def __str__(self):
        return f"{self.title} (Board: {self.board.title})"


class KanbanCard(models.Model):
    PRIORITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    )
    column = models.ForeignKey(KanbanColumn, on_delete=models.CASCADE, related_name='cards')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    position = models.PositiveIntegerField(default=0)
    color = models.CharField(max_length=20, default='indigo')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position']

    def __str__(self):
        return self.title


# ============================
# PHOTO GALLERY
# ============================

class PhotoAlbum(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    event = models.ForeignKey(Event, on_delete=models.SET_NULL, null=True, blank=True, related_name='albums')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='photo_albums')
    date = models.DateField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['created_by', 'date'], name='dash_album_creator_date_idx'),
            models.Index(fields=['event', 'date'], name='dash_album_event_date_idx'),
        ]

    def __str__(self):
        return self.title

    @property
    def photo_count(self):
        return self.photos.count()

    @property
    def cover_photo(self):
        return self.photos.first()


class Photo(models.Model):
    album = models.ForeignKey(PhotoAlbum, on_delete=models.CASCADE, related_name='photos')
    image = models.FileField(upload_to='gallery/')
    caption = models.CharField(max_length=300, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='uploaded_photos')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['album', 'uploaded_at'], name='dash_photo_album_date_idx'),
            models.Index(fields=['uploaded_by', 'uploaded_at'], name='dash_photo_user_date_idx'),
        ]

    def __str__(self):
        return self.caption or f"Photo in {self.album.title}"


# ============================
# MOOD TRACKER
# ============================

class MoodEntry(models.Model):
    MOOD_CHOICES = (
        ('😊', 'Happy'),
        ('😐', 'Neutral'),
        ('😔', 'Sad'),
        ('😤', 'Angry'),
        ('🤩', 'Excited'),
        ('😴', 'Tired'),
        ('😰', 'Anxious'),
        ('🥰', 'Loved'),
    )
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mood_entries')
    mood = models.CharField(max_length=5, choices=MOOD_CHOICES)
    note = models.TextField(blank=True)
    date = models.DateField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.student.username}: {self.mood} ({self.date})"


# ============================
# NOTIFICATION PREFERENCES
# ============================

class NotificationPreference(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_prefs')
    notice_enabled = models.BooleanField(default=True)
    message_enabled = models.BooleanField(default=True)
    assignment_enabled = models.BooleanField(default=True)
    grade_enabled = models.BooleanField(default=True)
    attendance_enabled = models.BooleanField(default=True)
    event_enabled = models.BooleanField(default=True)
    forum_enabled = models.BooleanField(default=True)

    def __str__(self):
        return f"Notification Prefs — {self.user.username}"


# ============================
# BOOKMARK SYSTEM
# ============================

class Bookmark(models.Model):
    CONTENT_TYPES = (
        ('assignment', 'Assignment'),
        ('resource', 'Library Resource'),
        ('thread', 'Forum Thread'),
        ('recording', 'Class Recording'),
        ('material', 'Study Material'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookmarks')
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES)
    object_id = models.PositiveIntegerField()
    title = models.CharField(max_length=300)
    url = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at'], name='dash_bookmark_user_date_idx'),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.title}"
