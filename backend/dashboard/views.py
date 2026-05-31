from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.urls import reverse
from datetime import date, timedelta, datetime
from pathlib import Path
import secrets
from accounts.models import Institution, PlatformInquiry, User
from accounts.security import consume_auth_attempt, reset_auth_attempts
from academics.models import CourseClass, ClassSchedule, Department, Exam, Grade, StudyMaterial
from attendance.models import AttendanceRecord, LeaveRequest
from assignments.models import Assignment, Submission
from dashboard.access import is_admin_role, is_institution_admin, is_platform_admin, scoped_classes, scoped_departments, scoped_users
from forum.models import ForumThread, ForumReply
from messaging.models import Message
import json
import csv
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from dashboard.models import (
    Notice, Event, FeeRecord, LibraryResource, BookIssue, Achievement, StudentXP, 
    BADGE_CHOICES, Poll, PollOption, PollVote, TodoItem, ActivityLog, HelpFAQ, Note, ChatSession,
    HomeworkEntry, DisciplinaryRecord, ParentGuardian, HealthRecord, BusRoute, StudentTransport,
    HostelRoom, HostelAllocation, InventoryItem, VisitorLog, Certificate, Complaint, Scholarship,
    ScholarshipApplication, ExamSeat, ClassRecording, StudyGroup, StudyGroupMessage, SkillBadge,
    StudentSkill, CourseFeedback, Circular, CircularReceipt, ThoughtOfDay, FlashcardDeck, Flashcard,
    DiaryEntry, KanbanBoard, KanbanColumn, KanbanCard, PhotoAlbum, Photo, MoodEntry, Bookmark, NotificationPreference
)
from dashboard.retired import retired_feature_redirect
from django.contrib.auth import update_session_auth_hash
from django.contrib import messages
from django.views.decorators.http import require_POST
import calendar as cal_module


USERNAME_VALIDATOR = UnicodeUsernameValidator()


def _launch_status(ok, title, detail, action='', level=None):
    if level is None:
        level = 'success' if ok else 'danger'
    return {
        'ok': ok,
        'level': level,
        'title': title,
        'detail': detail,
        'action': action,
    }


def _record_activity(user, action, description):
    try:
        ActivityLog.objects.create(user=user, action=action, description=description)
    except Exception:
        pass


def _validate_username_candidate(username, *, exclude_user=None):
    username = (username or '').strip()
    errors = []
    max_length = User._meta.get_field('username').max_length

    if not username:
        errors.append('Username is required.')
        return errors

    if len(username) > max_length:
        errors.append(f'Username must be {max_length} characters or fewer.')
        return errors

    try:
        USERNAME_VALIDATOR(username)
    except ValidationError as exc:
        errors.extend(exc.messages[:2])

    qs = User.objects.filter(username__iexact=username)
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)
    if qs.exists():
        errors.append('That username is already taken.')

    return errors


def _institution_filter_q(user, *paths):
    if is_platform_admin(user):
        return None
    if is_institution_admin(user) and not getattr(user, 'institution_id', None):
        return Q(pk__isnull=True)
    if not getattr(user, 'institution_id', None):
        return None

    query = Q()
    for path in paths:
        if path:
            query |= Q(**{path: user.institution})
    return query if query.children else None


def _visible_classes_for_user(user):
    if getattr(user, 'role', '') == 'teacher':
        classes = CourseClass.objects.filter(teacher=user)
        if user.institution_id:
            classes = classes.filter(institution=user.institution)
        return classes
    if getattr(user, 'role', '') == 'student':
        classes = user.enrolled_classes.all()
        if user.institution_id:
            classes = classes.filter(institution=user.institution)
        return classes
    if is_institution_admin(user):
        return scoped_classes(user)
    return CourseClass.objects.all()


def _visible_forum_threads(user):
    threads = ForumThread.objects.select_related('author', 'course_class')
    if is_platform_admin(user):
        return threads
    if user.role in ('teacher', 'student'):
        visible_classes = _visible_classes_for_user(user)
        thread_query = Q(course_class__in=visible_classes)
        if user.institution_id:
            thread_query |= Q(course_class__isnull=True, author__institution=user.institution)
        return threads.filter(thread_query).distinct()

    institution_query = _institution_filter_q(user, 'course_class__institution', 'author__institution')
    return threads.filter(institution_query).distinct() if institution_query is not None else threads


def _build_plugin_cards(user):
    platform_admin = is_platform_admin(user)
    ai_ready = bool(settings.GOOGLE_AI_API_KEY or settings.SARVAM_API_KEY)
    resend_ready = settings.EMAIL_BACKEND == getattr(settings, 'RESEND_EMAIL_BACKEND', '') and bool(settings.RESEND_API_KEY)
    branded_sender = resend_ready and '@resend.dev' not in settings.DEFAULT_FROM_EMAIL.lower()
    platform_cards = [
        {
            'title': 'Account Access',
            'section': 'Platform Trust',
            'status': 'Live' if resend_ready else 'Needs setup',
            'tone': 'success' if resend_ready else 'warning',
            'description': 'Secure signup verification, verified accounts, and protected onboarding.',
            'features': ['Teacher signup verification', 'Student signup verification', 'Verified account activation'],
            'action_label': 'Open Launch Center',
            'action_url': reverse('launch_center') if platform_admin else reverse('profile_settings'),
        },
        {
            'title': 'Branded Notifications',
            'section': 'Communication',
            'status': 'Domain ready' if branded_sender else ('Needs domain' if resend_ready else 'Needs setup'),
            'tone': 'success' if branded_sender else ('warning' if resend_ready else 'danger'),
            'description': 'Welcome emails, password resets, and support messages use EduMatrix branding.',
            'features': ['Welcome email', 'Password reset', 'Launch status visibility'],
            'action_label': 'Review Notifications',
            'action_url': reverse('launch_center') if platform_admin else reverse('help'),
        },
        {
            'title': 'Learning Assistant',
            'section': 'Learning Tools',
            'status': 'Live' if ai_ready else 'Optional setup',
            'tone': 'success' if ai_ready else 'warning',
            'description': 'AI chat, quiz generation, summarization, translation, and TTS tools inside EduMatrix.',
            'features': ['AI study chat', 'Quiz generation', 'Translation and TTS'],
            'action_label': 'Open AI Tools',
            'action_url': reverse('ai_chat'),
        },
        {
            'title': 'Whiteboard Studio',
            'section': 'Teaching and Learning',
            'status': 'Live',
            'tone': 'success',
            'description': 'Visual explanation surface for live teaching, sketching, and rapid collaboration.',
            'features': ['Teacher explanations', 'Student brainstorming', 'Creative planning'],
            'action_label': 'Open Whiteboard',
            'action_url': reverse('whiteboard'),
        },
        {
            'title': 'Insight Analytics',
            'section': 'Operations',
            'status': 'Live',
            'tone': 'success',
            'description': 'Attendance, academic, and institutional insight surfaces for admins, teachers, and students.',
            'features': ['Department analytics', 'Teacher reports', 'Student progress tracking'],
            'action_label': 'Open Analytics',
            'action_url': reverse('analytics'),
        },
        {
            'title': 'Campus Operations Stack',
            'section': 'Operations',
            'status': 'Live',
            'tone': 'success',
            'description': 'Guardians, health, transport, hostel, complaints, scholarships, and other campus operations.',
            'features': ['Guardians and health', 'Transport and hostel', 'Complaints and scholarships'],
            'action_label': 'Explore Campus Modules',
            'action_url': reverse('guardians') if user.role == 'student' else reverse('departments'),
        },
        {
            'title': 'Institution Verification',
            'section': 'Security',
            'status': 'Live',
            'tone': 'success',
            'description': 'Institution onboarding validates academic domains and keeps users grouped under the correct campus.',
            'features': ['Allowed academic domains', 'Auto-linked institution records', 'Institution-scoped access'],
            'action_label': 'Open User Directory',
            'action_url': reverse('users_list'),
        },
        {
            'title': 'Multilingual AI',
            'section': 'Learning Tools',
            'status': 'Live' if settings.SARVAM_API_KEY else 'Optional setup',
            'tone': 'success' if settings.SARVAM_API_KEY else 'warning',
            'description': 'Translation and text-to-speech for multilingual learning workflows.',
            'features': ['Indian language translation', 'Voice playback', 'Accessible classroom content'],
            'action_label': 'Open Translator',
            'action_url': reverse('translate'),
        },
        {
            'title': 'Installable Web App',
            'section': 'Experience',
            'status': 'Live',
            'tone': 'success',
            'description': 'PWA support makes EduMatrix installable on supported desktop and mobile browsers.',
            'features': ['Offline shell', 'App icons', 'Faster repeat access'],
            'action_label': 'Open Installable Experience',
            'action_url': reverse('dashboard_home'),
        },
    ]

    teacher_cards = [
        {
            'title': 'Classroom Workspace',
            'section': 'Teaching',
            'status': 'Live',
            'tone': 'success',
            'description': 'Assignments, homework, recordings, materials, stream posts, and classroom actions in one place.',
            'features': ['Publish classwork', 'Review submissions', 'Share materials'],
            'action_label': 'Open Classrooms',
            'action_url': reverse('classes'),
        },
        {
            'title': 'Assessment Flow',
            'section': 'Teaching',
            'status': 'Live',
            'tone': 'success',
            'description': 'Grade submissions, track performance, and keep students updated without leaving the class workspace.',
            'features': ['Grades', 'Homework review', 'Progress visibility'],
            'action_label': 'Open Grades',
            'action_url': reverse('grades'),
        },
        {
            'title': 'Learning Assistant',
            'section': 'Learning Tools',
            'status': 'Live' if ai_ready else 'Optional setup',
            'tone': 'success' if ai_ready else 'warning',
            'description': 'Use AI chat, quiz generation, translation, and study support tools for classroom preparation.',
            'features': ['AI quiz generation', 'Study explanations', 'Translation tools'],
            'action_label': 'Open AI Tools',
            'action_url': reverse('ai_chat'),
        },
        {
            'title': 'Whiteboard Studio',
            'section': 'Teaching',
            'status': 'Live',
            'tone': 'success',
            'description': 'Sketch explanations, plan lessons, and support visual classroom discussion.',
            'features': ['Live explanation', 'Lesson planning', 'Student brainstorming'],
            'action_label': 'Open Whiteboard',
            'action_url': reverse('whiteboard'),
        },
    ]

    student_cards = [
        {
            'title': 'Classroom Workspace',
            'section': 'Student Portal',
            'status': 'Live',
            'tone': 'success',
            'description': 'Open your classes, view materials, complete assignments, and follow announcements.',
            'features': ['Class materials', 'Assignments', 'Homework'],
            'action_label': 'Open Classrooms',
            'action_url': reverse('classes'),
        },
        {
            'title': 'Progress Center',
            'section': 'Student Portal',
            'status': 'Live',
            'tone': 'success',
            'description': 'Track attendance, grades, submissions, and academic progress from your dashboard.',
            'features': ['My attendance', 'My grades', 'Submission status'],
            'action_label': 'View Progress',
            'action_url': reverse('grades'),
        },
        {
            'title': 'Study Assistant',
            'section': 'Learning Tools',
            'status': 'Live' if ai_ready else 'Optional setup',
            'tone': 'success' if ai_ready else 'warning',
            'description': 'Ask study questions, generate practice quizzes, translate notes, and prepare faster.',
            'features': ['Study chat', 'Practice quiz', 'Translation tools'],
            'action_label': 'Open Study Tools',
            'action_url': reverse('ai_chat'),
        },
        {
            'title': 'Messages and Notices',
            'section': 'Communication',
            'status': 'Live',
            'tone': 'success',
            'description': 'Stay updated with class messages, notices, calendar updates, and support workflows.',
            'features': ['Inbox', 'Notices', 'Calendar'],
            'action_label': 'Open Inbox',
            'action_url': reverse('inbox'),
        },
    ]

    if getattr(user, 'role', '') == 'teacher':
        return teacher_cards
    if getattr(user, 'role', '') == 'student':
        return student_cards
    return platform_cards


def _build_launch_groups():
    base_dir = Path(settings.BASE_DIR)
    local_hosts = {'localhost', '127.0.0.1', 'testserver'}
    allowed_hosts = set(settings.ALLOWED_HOSTS)
    email_is_console = settings.EMAIL_BACKEND.endswith('console.EmailBackend')
    email_is_smtp = settings.EMAIL_BACKEND.endswith('smtp.EmailBackend')
    email_is_resend = settings.EMAIL_BACKEND == getattr(settings, 'RESEND_EMAIL_BACKEND', '')
    resend_test_sender = '@resend.dev' in settings.DEFAULT_FROM_EMAIL.lower()
    email_ready = (
        (email_is_resend and bool(settings.RESEND_API_KEY))
        or (email_is_smtp and bool(settings.EMAIL_HOST))
    )
    database_engine = settings.DATABASES['default']['ENGINE']
    using_supabase_db = database_engine.endswith('postgresql') and not getattr(settings, 'USE_SQLITE', False)

    groups = [
        {
            'title': 'Core Launch',
            'items': [
                _launch_status(
                    settings.SECRET_KEY != 'django-insecure-dev-key-change-in-production',
                    'Production secret key',
                    'Django signing uses a custom secret key.',
                    'Set DJANGO_SECRET_KEY before launch.',
                ),
                _launch_status(
                    not settings.DEBUG,
                    'Debug mode disabled',
                    'Production should run with DJANGO_DEBUG=False.',
                    'Set DJANGO_DEBUG=False on hosting.',
                    level='warning' if settings.DEBUG else 'success',
                ),
                _launch_status(
                    using_supabase_db,
                    'Production database',
                    'EduMatrix is configured for the production database connection.',
                    'Set the production database host, user, password, database name, and port in environment variables.',
                ),
                _launch_status(
                    email_ready and bool(settings.PUBLIC_SITE_URL),
                    'Signup verification email',
                    'Teacher and student signup sends branded verification email and returns to EduMatrix.',
                    'Set the email delivery key and DJANGO_PUBLIC_SITE_URL.',
                ),
            ],
        },
        {
            'title': 'Security',
            'items': [
                _launch_status(
                    settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE,
                    'Secure cookies',
                    'Session and CSRF cookies are HTTPS-only.',
                    'Set DJANGO_SECURE_COOKIES=True behind HTTPS.',
                    level='warning' if not (settings.SESSION_COOKIE_SECURE and settings.CSRF_COOKIE_SECURE) else 'success',
                ),
                _launch_status(
                    settings.X_FRAME_OPTIONS == 'DENY',
                    'Clickjacking protection',
                    'X-Frame-Options is locked down.',
                    'Set DJANGO_X_FRAME_OPTIONS=DENY.',
                    level='warning' if settings.X_FRAME_OPTIONS != 'DENY' else 'success',
                ),
                _launch_status(
                    bool(allowed_hosts - local_hosts) or '*' in allowed_hosts,
                    'Production hosts',
                    'Allowed hosts include a deployable public domain or wildcard for controlled hosting.',
                    'Add your domain to DJANGO_ALLOWED_HOSTS.',
                    level='warning' if not (allowed_hosts - local_hosts or '*' in allowed_hosts) else 'success',
                ),
                _launch_status(
                    settings.SECURE_SSL_REDIRECT and settings.SECURE_HSTS_SECONDS > 0,
                    'HTTPS hardening',
                    'SSL redirect and HSTS are enabled for production.',
                    'Enable HTTPS redirect/HSTS after the domain has SSL.',
                    level='warning' if not (settings.SECURE_SSL_REDIRECT and settings.SECURE_HSTS_SECONDS > 0) else 'success',
                ),
            ],
        },
        {
            'title': 'Experience',
            'items': [
                _launch_status(
                    email_ready,
                    'Account email delivery',
                    (
                        'Welcome and password reset emails are configured.'
                        if email_is_resend else
                        'Welcome and password reset emails are configured through SMTP.'
                    ),
                    (
                        'Add the production email API key and select the email delivery backend.'
                        if not email_ready and not email_is_smtp else
                        'Configure DJANGO_EMAIL_HOST and SMTP credentials.'
                    ),
                    level='warning' if not email_ready else 'success',
                ),
                _launch_status(
                    not email_is_resend or not resend_test_sender,
                    'Verified email sender',
                    'Outgoing mail uses your branded sender domain.'
                    if not (email_is_resend and resend_test_sender)
                    else 'Outgoing mail is still using a test sender domain.',
                    'Verify a sending domain and update DJANGO_DEFAULT_FROM_EMAIL before launch.',
                    level='warning' if email_is_resend and resend_test_sender else 'success',
                ),
                _launch_status(
                    all((base_dir / path).exists() for path in [
                        'static/manifest.webmanifest',
                        'static/js/service-worker.js',
                        'static/img/edumatrix-icon-192.png',
                        'static/img/edumatrix-icon-512.png',
                    ]),
                    'PWA install assets',
                    'Manifest, service worker, and app icons are present.',
                    'Restore missing static PWA assets.',
                ),
                _launch_status(
                    bool(settings.PUBLIC_SITE_URL),
                    'Public site URL',
                    'Emails can use a stable public URL.',
                    'Set DJANGO_PUBLIC_SITE_URL to your production domain.',
                    level='warning' if not settings.PUBLIC_SITE_URL else 'success',
                ),
                _launch_status(
                    bool(settings.GOOGLE_AI_API_KEY or settings.SARVAM_API_KEY),
                    'AI integrations',
                    'AI learning tools are configured.',
                    'Configure AI service keys for learning tools.',
                    level='warning' if not (settings.GOOGLE_AI_API_KEY or settings.SARVAM_API_KEY) else 'success',
                ),
            ],
        },
    ]
    return groups

@login_required
def dashboard_home(request):
    user = request.user
    today = date.today()

    if is_admin_role(user):
        return admin_dashboard(request, user, today)
    elif user.role == 'teacher':
        return teacher_dashboard(request, user, today)
    else:
        return student_dashboard(request, user, today)


@login_required
def launch_center_view(request):
    if not is_platform_admin(request.user):
        messages.error(request, 'Launch Center is reserved for the EduMatrix platform owner.')
        return redirect('dashboard_home')

    groups = _build_launch_groups()
    checks = [item for group in groups for item in group['items']]
    success_count = sum(1 for item in checks if item['level'] == 'success')
    warning_count = sum(1 for item in checks if item['level'] == 'warning')
    blocker_count = sum(1 for item in checks if item['level'] == 'danger')
    readiness = round(success_count / len(checks) * 100) if checks else 0

    return render(request, 'dashboard/launch_center.html', {
        'groups': groups,
        'readiness': readiness,
        'success_count': success_count,
        'warning_count': warning_count,
        'blocker_count': blocker_count,
        'total_checks': len(checks),
    })


@login_required
def integrations_hub_view(request):
    if not is_platform_admin(request.user):
        messages.info(request, 'Integrations Hub is reserved for the EduMatrix platform owner.')
        return redirect('dashboard_home')

    cards = _build_plugin_cards(request.user)
    sections = []
    seen = []
    for card in cards:
        if card['section'] not in seen:
            seen.append(card['section'])
    for section in seen:
        sections.append({
            'title': section,
            'cards': [card for card in cards if card['section'] == section],
        })

    live_count = sum(1 for card in cards if card['tone'] == 'success')
    warning_count = sum(1 for card in cards if card['tone'] == 'warning')
    setup_count = sum(1 for card in cards if card['tone'] == 'danger')

    return render(request, 'dashboard/integrations_hub.html', {
        'integration_sections': sections,
        'plugin_cards': cards,
        'live_count': live_count,
        'warning_count': warning_count,
        'setup_count': setup_count,
        'total_count': len(cards),
    })


def _attendance_percent(records):
    summary = records.aggregate(
        total=Count('id'),
        present=Count('id', filter=Q(status='present')),
    )
    total = summary['total'] or 0
    present = summary['present'] or 0
    return {
        'total': total,
        'present': present,
        'percent': round((present / total * 100) if total else 0),
    }


def _low_attendance_rows(students, attendance_records, *, threshold=75, limit=6):
    attendance_stats = {
        item['student_id']: item
        for item in attendance_records.values('student_id').annotate(
            total=Count('id'),
            present=Count('id', filter=Q(status='present')),
        )
    }
    rows = []
    for student in students.values('id', 'username', 'first_name', 'last_name')[:80]:
        stats = attendance_stats.get(student['id'])
        total = stats['total'] if stats else 0
        if not total:
            continue
        present = stats['present'] or 0
        percent = round(present / total * 100)
        full_name = f"{student['first_name']} {student['last_name']}".strip()
        if percent < threshold:
            rows.append({
                'label': full_name or student['username'],
                'detail': f'{present}/{total} attended',
                'value': f'{percent}%',
                'tone': 'danger' if percent < 60 else 'warning',
            })
        if len(rows) >= limit:
            break
    return rows


def _grade_average_for_student(student):
    total = 0
    usable = 0
    grade_records = Grade.objects.filter(student=student).values_list('marks_obtained', 'exam__total_marks')
    for marks_obtained, total_marks in grade_records:
        exam_total = float(total_marks or 0)
        if exam_total <= 0:
            continue
        total += float(marks_obtained) / exam_total * 100
        usable += 1
    return round(total / usable) if usable else 0


def _inquiry_scope_for_user(user):
    inquiries = PlatformInquiry.objects.exclude(status='closed').select_related('linked_institution')
    if is_platform_admin(user):
        return inquiries
    if is_institution_admin(user) and user.institution_id:
        return inquiries.filter(linked_institution_id=user.institution_id)
    return inquiries.none()


def _provision_institution_from_inquiry(inquiry):
    domain = Institution.normalize_domain(inquiry.institution_domain) or Institution.domain_from_email(inquiry.email)
    if not Institution.domain_is_allowed(domain):
        return None

    institution, created = Institution.objects.get_or_create(
        domain=domain,
        defaults={
            'name': inquiry.institute_name.strip() or Institution.infer_name_from_domain(domain),
            'verification_status': 'verified',
            'verified_at': timezone.now(),
        },
    )
    updated_fields = []
    preferred_name = (inquiry.institute_name or '').strip()
    if preferred_name and institution.name != preferred_name:
        institution.name = preferred_name
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


def _save_power_task(request, user):
    title = (request.POST.get('title') or '').strip()
    if not title:
        messages.error(request, 'Add a task title before saving it to Planner.')
        return

    due_date = date.today()
    raw_due_date = request.POST.get('due_date')
    if raw_due_date:
        try:
            due_date = date.fromisoformat(raw_due_date)
        except ValueError:
            due_date = date.today()

    description = (request.POST.get('description') or '').strip()
    priority = request.POST.get('priority', 'medium')
    if priority not in {'low', 'medium', 'high'}:
        priority = 'medium'

    duplicate = TodoItem.objects.filter(user=user, title__iexact=title, is_done=False).exists()
    if duplicate:
        messages.info(request, 'That action is already in your Planner.')
        return

    TodoItem.objects.create(
        user=user,
        title=title,
        description=description,
        priority=priority,
        due_date=due_date,
    )
    messages.success(request, 'Action saved to your Planner.')


def _save_power_tasks_from_post(request, user):
    titles = request.POST.getlist('automation_title')
    descriptions = request.POST.getlist('automation_description')
    priorities = request.POST.getlist('automation_priority')
    due_dates = request.POST.getlist('automation_due_date')
    created = 0
    skipped = 0

    for index, raw_title in enumerate(titles):
        title = (raw_title or '').strip()
        if not title:
            continue

        description = descriptions[index].strip() if index < len(descriptions) else ''
        priority = priorities[index] if index < len(priorities) else 'medium'
        if priority not in {'low', 'medium', 'high'}:
            priority = 'medium'

        due_date = date.today()
        if index < len(due_dates) and due_dates[index]:
            try:
                due_date = date.fromisoformat(due_dates[index])
            except ValueError:
                due_date = date.today()

        if TodoItem.objects.filter(user=user, title__iexact=title, is_done=False).exists():
            skipped += 1
            continue

        TodoItem.objects.create(
            user=user,
            title=title,
            description=description,
            priority=priority,
            due_date=due_date,
        )
        created += 1

    if created:
        messages.success(request, f'Automation sweep created {created} Planner task{"s" if created != 1 else ""}.')
    elif skipped:
        messages.info(request, 'Those automation actions are already waiting in your Planner.')
    else:
        messages.info(request, 'No automation actions were ready to save.')


@login_required
def smart_command_center_view(request):
    user = request.user
    today = date.today()
    now = timezone.now()
    upcoming_cutoff = today + timedelta(days=14)
    visible_classes = _visible_classes_for_user(user)
    visible_class_ids = list(visible_classes.values_list('id', flat=True))
    unread_count = Message.objects.filter(receiver=user, is_read=False).count()
    quick_links = []
    signal_cards = []
    workload_items = []
    risk_items = []
    upcoming_items = []
    open_requests = []
    power_briefing = []
    power_playbook = []
    automation_deck = []
    workflow_recipes = []

    if request.method == 'POST' and request.POST.get('action') == 'capture_power_task':
        _save_power_task(request, user)
        return redirect('smart_command_center')

    if request.method == 'POST' and request.POST.get('action') in {'run_power_automation_sweep', 'run_power_recipe_bundle'}:
        _save_power_tasks_from_post(request, user)
        return redirect('smart_command_center')

    if request.method == 'POST' and is_admin_role(user):
        action = request.POST.get('action')
        inquiry_id = request.POST.get('inquiry_id')
        inquiry = _inquiry_scope_for_user(user).filter(id=inquiry_id).first()

        if not inquiry:
            messages.error(request, 'That onboarding request is no longer available in your workspace.')
            return redirect('smart_command_center')

        if action == 'update_inquiry_status':
            next_status = request.POST.get('status')
            valid_statuses = {choice[0] for choice in PlatformInquiry.STATUS_CHOICES}
            if next_status in valid_statuses:
                inquiry.status = next_status
                inquiry.save(update_fields=['status', 'updated_at'])
                messages.success(request, f'Request status updated for {inquiry.institute_name}.')
            else:
                messages.error(request, 'Choose a valid request status.')
        elif action == 'update_inquiry_verification':
            next_verification = request.POST.get('verification_status')
            valid_verifications = {choice[0] for choice in PlatformInquiry.VERIFICATION_CHOICES}
            if next_verification in valid_verifications:
                inquiry.verification_status = next_verification
                update_fields = ['verification_status', 'updated_at']
                if next_verification == 'verified' and not inquiry.linked_institution_id:
                    institution = _provision_institution_from_inquiry(inquiry)
                    if institution:
                        inquiry.linked_institution = institution
                        update_fields.append('linked_institution')
                    else:
                        messages.warning(request, 'Verification saved, but the institution domain is not an approved academic domain.')
                inquiry.save(update_fields=update_fields)
                messages.success(request, f'Verification updated for {inquiry.institute_name}.')
            else:
                messages.error(request, 'Choose a valid verification state.')
        return redirect('smart_command_center')

    notice_qs = Notice.objects.filter(Q(target_role='all') | Q(target_role=user.role))
    event_qs = Event.objects.filter(event_date__gte=today, event_date__lte=upcoming_cutoff)
    if visible_class_ids:
        notice_qs = notice_qs.filter(Q(target_class__isnull=True) | Q(target_class_id__in=visible_class_ids)).distinct()
        event_qs = event_qs.filter(Q(course_class__isnull=True) | Q(course_class_id__in=visible_class_ids)).distinct()
    elif not is_platform_admin(user):
        notice_qs = notice_qs.filter(target_class__isnull=True)
        event_qs = event_qs.filter(course_class__isnull=True)

    event_qs = event_qs.select_related('course_class').only(
        'id', 'title', 'event_type', 'event_date', 'course_class_id'
    )
    notice_qs = notice_qs.select_related('target_class').only(
        'id', 'title', 'target_role', 'target_class_id', 'created_at'
    )

    for event in event_qs[:4]:
        upcoming_items.append({
            'label': event.title,
            'detail': event.get_event_type_display(),
            'value': event.event_date.strftime('%d %b'),
            'href': reverse('calendar'),
        })
    for notice in notice_qs[:3]:
        upcoming_items.append({
            'label': notice.title,
            'detail': 'Notice',
            'value': notice.created_at.strftime('%d %b'),
            'href': reverse('notices'),
        })

    if is_admin_role(user):
        platform_admin = is_platform_admin(user)
        institution_admin = is_institution_admin(user)
        scoped_user_qs = scoped_users(user)
        scoped_class_qs = scoped_classes(user)
        scoped_department_qs = scoped_departments(user)
        attendance_qs = AttendanceRecord.objects.all()
        assignment_qs = Assignment.objects.all()
        homework_qs = HomeworkEntry.objects.all()
        fee_qs = FeeRecord.objects.all()
        complaint_qs = Complaint.objects.exclude(status__in=['resolved', 'closed'])
        leave_qs = LeaveRequest.objects.filter(status='pending')
        inquiry_qs = PlatformInquiry.objects.exclude(status='closed')
        activity_qs = ActivityLog.objects.select_related('user')

        if institution_admin:
            if user.institution_id:
                institution_id = user.institution_id
                attendance_qs = attendance_qs.filter(
                    Q(course_class__institution_id=institution_id) |
                    Q(student__institution_id=institution_id)
                ).distinct()
                assignment_qs = assignment_qs.filter(course_class__institution_id=institution_id)
                homework_qs = homework_qs.filter(course_class__institution_id=institution_id)
                fee_qs = fee_qs.filter(student__institution_id=institution_id)
                complaint_qs = complaint_qs.filter(filed_by__institution_id=institution_id)
                leave_qs = leave_qs.filter(student__institution_id=institution_id)
                inquiry_qs = inquiry_qs.filter(linked_institution_id=institution_id)
                activity_qs = activity_qs.filter(user__institution_id=institution_id)
            else:
                attendance_qs = attendance_qs.none()
                assignment_qs = assignment_qs.none()
                homework_qs = homework_qs.none()
                fee_qs = fee_qs.none()
                complaint_qs = complaint_qs.none()
                leave_qs = leave_qs.none()
                inquiry_qs = inquiry_qs.none()
                activity_qs = activity_qs.none()

        attendance_today = _attendance_percent(attendance_qs.filter(date=today))
        students_qs = scoped_user_qs.filter(role='student')
        students_count = students_qs.count()
        teachers_count = scoped_user_qs.filter(role='teacher').count()
        class_count = scoped_class_qs.count()
        department_count = scoped_department_qs.count()
        assignment_count = assignment_qs.count()
        homework_count = homework_qs.count()
        overdue_fees = fee_qs.exclude(status='paid').filter(due_date__lt=today).count()
        pending_fees = fee_qs.exclude(status='paid').count()
        weekly_assignments = assignment_qs.filter(due_date__gte=now, due_date__lte=now + timedelta(days=7)).count()
        weekly_homework = homework_qs.filter(due_date__gte=today, due_date__lte=today + timedelta(days=7)).count()
        inquiry_qs = inquiry_qs.select_related('linked_institution').only(
            'id', 'institute_name', 'contact_name', 'email', 'phone', 'institution_domain',
            'student_count', 'message', 'status', 'verification_status', 'created_at',
            'updated_at', 'linked_institution_id', 'linked_institution__name',
        )
        inquiry_count = inquiry_qs.count()
        has_inquiries = inquiry_count > 0
        complaint_count = complaint_qs.count()
        leave_count = leave_qs.count()
        admin_queue_count = complaint_count + leave_count
        has_admin_queue = admin_queue_count > 0
        activity_qs = activity_qs.select_related('user').only(
            'id', 'action', 'description', 'created_at',
            'user__id', 'user__username', 'user__first_name', 'user__last_name',
        )
        for inquiry in inquiry_qs[:8]:
            created_age = max((now - inquiry.created_at).days, 0) if inquiry.created_at else 0
            open_requests.append({
                'id': inquiry.id,
                'institute_name': inquiry.institute_name,
                'contact_name': inquiry.contact_name,
                'email': inquiry.email,
                'phone': inquiry.phone or 'Not provided',
                'domain': inquiry.institution_domain or Institution.domain_from_email(inquiry.email) or 'Not provided',
                'student_count': inquiry.student_count or 'Not provided',
                'message': inquiry.message or 'No request note was submitted.',
                'status': inquiry.status,
                'status_label': inquiry.get_status_display(),
                'verification_status': inquiry.verification_status,
                'verification_label': inquiry.get_verification_status_display(),
                'linked_institution': inquiry.linked_institution.name if inquiry.linked_institution_id else 'Not linked yet',
                'created_at': inquiry.created_at,
                'updated_at': inquiry.updated_at,
                'age_days': created_age,
            })
        power_briefing = [
            {
                'label': 'Onboarding',
                'value': inquiry_count,
                'detail': 'Open institution request records waiting in the pipeline.',
                'href': '#open-requests',
                'tone': 'warning' if has_inquiries else 'success',
            },
            {
                'label': 'Attendance signal',
                'value': f"{attendance_today['percent']}%",
                'detail': f"{attendance_today['present']}/{attendance_today['total']} present today.",
                'href': reverse('analytics'),
                'tone': 'warning' if attendance_today['percent'] < 75 else 'success',
            },
            {
                'label': 'Finance follow-up',
                'value': pending_fees,
                'detail': f'{overdue_fees} overdue fee records need attention.',
                'href': reverse('fees'),
                'tone': 'danger' if overdue_fees else ('warning' if pending_fees else 'success'),
            },
            {
                'label': 'Academic cadence',
                'value': weekly_assignments,
                'detail': 'Assignments due in the next seven days.',
                'href': reverse('calendar'),
                'tone': 'success' if weekly_assignments else 'warning',
            },
        ]
        if has_inquiries:
            power_playbook.append({
                'label': 'Review onboarding requests',
                'detail': 'Open each request, verify the institution domain, and move contacted leads forward.',
                'href': '#open-requests',
                'value': inquiry_count,
                'priority': 'high',
            })
        if attendance_today['total'] and attendance_today['percent'] < 75:
            power_playbook.append({
                'label': 'Run attendance intervention',
                'detail': 'Open analytics, identify low-attendance students, and coordinate follow-up.',
                'href': reverse('analytics'),
                'value': f"{attendance_today['percent']}%",
                'priority': 'high',
            })
        if overdue_fees:
            power_playbook.append({
                'label': 'Review overdue fee records',
                'detail': 'Check overdue fee records and plan follow-up communication.',
                'href': reverse('fees'),
                'value': overdue_fees,
                'priority': 'medium',
            })
        if has_admin_queue:
            power_playbook.append({
                'label': 'Clear admin approvals',
                'detail': 'Resolve active complaints and pending leave approvals before they age.',
                'href': reverse('complaints') if complaint_count else reverse('leave_requests'),
                'value': admin_queue_count,
                'priority': 'high',
            })
        power_playbook.append({
            'label': 'Publish a weekly institute update',
            'detail': 'Keep everyone aligned with a short notice about schedules, reminders, or academic priorities.',
            'href': reverse('notices'),
            'value': 'Notice',
            'priority': 'low',
        })
        automation_deck = [
            {
                'label': 'Request verification sweep',
                'detail': 'Create follow-ups for every open institution request so no lead is left cold.',
                'href': '#open-requests',
                'value': inquiry_count,
                'priority': 'high' if has_inquiries else 'low',
                'cadence': 'Daily',
                'enabled': has_inquiries,
                'due_date': today,
            },
            {
                'label': 'Attendance intervention sweep',
                'detail': 'Queue a same-day attendance review when the workspace average drops below target.',
                'href': reverse('analytics'),
                'value': f"{attendance_today['percent']}%",
                'priority': 'high' if attendance_today['total'] and attendance_today['percent'] < 75 else 'medium',
                'cadence': 'Live',
                'enabled': attendance_today['total'] and attendance_today['percent'] < 75,
                'due_date': today,
            },
            {
                'label': 'Fee follow-up automation',
                'detail': 'Prepare a finance review task for unpaid and overdue fee records.',
                'href': reverse('fees'),
                'value': pending_fees,
                'priority': 'high' if overdue_fees else 'medium',
                'cadence': 'Weekly',
                'enabled': pending_fees > 0,
                'due_date': today + timedelta(days=1),
            },
            {
                'label': 'Approval queue cleaner',
                'detail': 'Create an admin approval task when complaints or leave requests are waiting.',
                'href': reverse('complaints') if complaint_count else reverse('leave_requests'),
                'value': admin_queue_count,
                'priority': 'high',
                'cadence': 'Daily',
                'enabled': has_admin_queue,
                'due_date': today,
            },
            {
                'label': 'Weekly operations digest',
                'detail': 'Schedule a weekly summary covering requests, attendance, classwork, finance, and messages.',
                'href': reverse('reports'),
                'value': 'Digest',
                'priority': 'low',
                'cadence': 'Weekly',
                'enabled': True,
                'due_date': today + timedelta(days=2),
            },
            {
                'label': 'Academic cadence monitor',
                'detail': 'Create a calendar review task for assignments and homework due this week.',
                'href': reverse('calendar'),
                'value': weekly_assignments + weekly_homework,
                'priority': 'medium',
                'cadence': 'Weekly',
                'enabled': weekly_assignments > 0 or weekly_homework > 0,
                'due_date': today + timedelta(days=1),
            },
        ]
        workflow_recipes = [
            {
                'label': 'Launch readiness sprint',
                'detail': 'A production-style admin sweep for onboarding, security, reporting, and launch health.',
                'badge': 'Admin OS',
                'href': reverse('launch_center') if platform_admin else reverse('profile_settings'),
                'tasks': [
                    {'title': 'Verify open institution requests', 'description': 'Review request details, domain eligibility, and onboarding status.', 'priority': 'high', 'due_date': today},
                    {'title': 'Audit user and role access', 'description': 'Check admins, teachers, students, and institution scoping before launch.', 'priority': 'high', 'due_date': today + timedelta(days=1)},
                    {'title': 'Review platform reporting exports', 'description': 'Open reports and confirm attendance, classroom, and user data exports are usable.', 'priority': 'medium', 'due_date': today + timedelta(days=2)},
                    {'title': 'Publish launch readiness notice', 'description': 'Send a short institution-wide update with next steps and support channels.', 'priority': 'low', 'due_date': today + timedelta(days=3)},
                ],
            },
            {
                'label': 'Student success intervention',
                'detail': 'Turns attendance, grading, and communication signals into a focused student support plan.',
                'badge': 'Success',
                'href': reverse('analytics'),
                'tasks': [
                    {'title': 'Review low-attendance learners', 'description': 'Use analytics to identify students who need attendance support.', 'priority': 'high', 'due_date': today},
                    {'title': 'Check pending academic work', 'description': 'Review assignments and homework volume before intervention messages go out.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Message support plan to stakeholders', 'description': 'Send a concise follow-up to the right class or academic team.', 'priority': 'medium', 'due_date': today + timedelta(days=2)},
                ],
            },
            {
                'label': 'Operations cleanup bundle',
                'detail': 'Clears the weekly operational clutter across approvals, fees, notices, and schedules.',
                'badge': 'Ops',
                'href': reverse('planner'),
                'tasks': [
                    {'title': 'Clear approval queue', 'description': 'Resolve pending leave requests and complaints before they age.', 'priority': 'high', 'due_date': today},
                    {'title': 'Review overdue fee records', 'description': 'Check unpaid fee records and prepare follow-up actions.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Check upcoming calendar events', 'description': 'Review academic dates, notices, and classwork due this week.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                ],
            },
        ]
        signal_cards = [
            {'label': 'Students', 'value': students_count, 'detail': 'Active learners in scope', 'tone': 'success'},
            {'label': 'Teachers', 'value': teachers_count, 'detail': 'Faculty accounts', 'tone': 'success'},
            {'label': 'Classrooms', 'value': class_count, 'detail': 'Academic rooms and sections', 'tone': 'success'},
            {'label': 'Attendance today', 'value': f"{attendance_today['percent']}%", 'detail': f"{attendance_today['present']}/{attendance_today['total']} marked present", 'tone': 'warning' if attendance_today['percent'] < 75 else 'success'},
            {'label': 'Open requests', 'value': inquiry_count, 'detail': 'Institution onboarding pipeline' if platform_admin else 'Institution requests', 'tone': 'warning' if has_inquiries else 'success'},
            {'label': 'Admin queue', 'value': admin_queue_count, 'detail': f'{complaint_count} complaints, {leave_count} leave approvals', 'tone': 'warning' if has_admin_queue else 'success'},
        ]
        workload_items = [
            {'label': 'Open institution requests', 'detail': 'Review request details, verify domains, and update onboarding status', 'value': inquiry_count, 'href': '#open-requests'},
            {'label': 'Departments configured', 'detail': 'Academic structure ready for users and classes', 'value': department_count, 'href': reverse('departments')},
            {'label': 'Assignments live', 'detail': 'Classwork currently published', 'value': assignment_count, 'href': reverse('assignments')},
            {'label': 'Homework active', 'detail': 'Homework entries in active classrooms', 'value': homework_count, 'href': reverse('homework')},
            {'label': 'Pending fees', 'detail': 'Fee records not yet marked paid', 'value': pending_fees, 'href': reverse('fees')},
            {'label': 'Unread messages', 'detail': 'Inbox items waiting for review', 'value': unread_count, 'href': reverse('inbox')},
        ]
        risk_items = _low_attendance_rows(students_qs, attendance_qs)
        if not risk_items:
            risk_items.append({'label': 'Attendance health', 'detail': 'No low-attendance learners detected in the current data.', 'value': 'Clear', 'tone': 'success'})
        quick_links = [
            {'label': 'Planner', 'detail': 'Daily schedule and task cockpit', 'href': reverse('planner')},
            {'label': 'Requests', 'detail': 'Open onboarding request board', 'href': '#open-requests'},
            {'label': 'Manage Users', 'detail': 'Create and review accounts', 'href': reverse('users_list')},
            {'label': 'Departments', 'detail': 'Structure academic teams', 'href': reverse('departments')},
            {'label': 'Classrooms', 'detail': 'Manage class spaces', 'href': reverse('classes')},
            {'label': 'Reports', 'detail': 'Export and inspect performance', 'href': reverse('reports')},
            {'label': 'Analytics', 'detail': 'Track operational trends', 'href': reverse('analytics')},
            {
                'label': 'Launch Center' if platform_admin else 'Profile Settings',
                'detail': 'Production readiness controls' if platform_admin else 'Manage your institution admin account',
                'href': reverse('launch_center') if platform_admin else reverse('profile_settings'),
            },
        ]
        recent_activity = activity_qs[:6]

    elif user.role == 'teacher':
        teacher_classes = visible_classes
        teacher_class_count = teacher_classes.count()
        has_teacher_classes = teacher_class_count > 0
        students_qs = User.objects.filter(enrolled_classes__in=teacher_classes, role='student').distinct()
        students_count = students_qs.count()
        attendance_qs = AttendanceRecord.objects.filter(course_class__in=teacher_classes)
        today_records = attendance_qs.filter(date=today)
        attendance_today = _attendance_percent(today_records)
        pending_submissions = Submission.objects.filter(assignment__course_class__in=teacher_classes, graded=False).count()
        assignment_due = Assignment.objects.filter(
            course_class__in=teacher_classes,
            due_date__gte=now,
            due_date__lte=now + timedelta(days=7),
        ).count()
        homework_due = HomeworkEntry.objects.filter(
            course_class__in=teacher_classes,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        ).count()
        recording_count = ClassRecording.objects.filter(course_class__in=teacher_classes).count()
        missing_attendance = []
        marked_class_ids = set(today_records.values_list('course_class_id', flat=True).distinct())
        for course_class in teacher_classes.only('id', 'name', 'subject')[:8]:
            if course_class.id not in marked_class_ids:
                missing_attendance.append({
                    'label': course_class.name,
                    'detail': f'{course_class.subject} attendance has not been marked today.',
                    'value': 'Pending',
                    'tone': 'warning',
                })
        power_briefing = [
            {
                'label': 'Teaching load',
                'value': teacher_class_count,
                'detail': 'Active classroom spaces assigned to you.',
                'href': reverse('classes'),
                'tone': 'success',
            },
            {
                'label': 'Attendance work',
                'value': len(missing_attendance),
                'detail': 'Classes still missing attendance today.',
                'href': reverse('mark_attendance'),
                'tone': 'warning' if missing_attendance else 'success',
            },
            {
                'label': 'Grading queue',
                'value': pending_submissions,
                'detail': 'Student submissions waiting for review.',
                'href': reverse('assignments'),
                'tone': 'warning' if pending_submissions else 'success',
            },
            {
                'label': 'Due this week',
                'value': assignment_due + homework_due,
                'detail': f'{assignment_due} assignments and {homework_due} homework items.',
                'href': reverse('planner'),
                'tone': 'warning' if assignment_due or homework_due else 'success',
            },
        ]
        if missing_attendance:
            power_playbook.append({
                'label': 'Finish today attendance',
                'detail': 'Mark missing classroom attendance before the day closes.',
                'href': reverse('mark_attendance'),
                'value': len(missing_attendance),
                'priority': 'high',
            })
        if pending_submissions:
            power_playbook.append({
                'label': 'Grade pending submissions',
                'detail': 'Open assignments and clear the ungraded submission queue.',
                'href': reverse('assignments'),
                'value': pending_submissions,
                'priority': 'high',
            })
        if has_teacher_classes:
            power_playbook.append({
                'label': 'Post a classroom update',
                'detail': 'Share a short class notice or study reminder to keep students aligned.',
                'href': reverse('classes'),
                'value': 'Notice',
                'priority': 'medium',
            })
            power_playbook.append({
                'label': 'Generate a quick revision quiz',
                'detail': 'Use the AI quiz generator for a warmup, exit ticket, or revision check.',
                'href': reverse('ai_quiz'),
                'value': 'AI',
                'priority': 'low',
            })
        automation_deck = [
            {
                'label': 'Attendance closeout automation',
                'detail': 'Create a closeout task for classes still missing today attendance.',
                'href': reverse('mark_attendance'),
                'value': len(missing_attendance),
                'priority': 'high',
                'cadence': 'Daily',
                'enabled': bool(missing_attendance),
                'due_date': today,
            },
            {
                'label': 'Grading queue automation',
                'detail': 'Queue a grading work block for ungraded submissions across your classrooms.',
                'href': reverse('assignments'),
                'value': pending_submissions,
                'priority': 'high' if pending_submissions else 'medium',
                'cadence': 'Daily',
                'enabled': pending_submissions > 0,
                'due_date': today + timedelta(days=1),
            },
            {
                'label': 'Homework cadence automation',
                'detail': 'Schedule a review of homework due this week so practice stays visible.',
                'href': reverse('homework'),
                'value': homework_due,
                'priority': 'medium',
                'cadence': 'Weekly',
                'enabled': homework_due > 0,
                'due_date': today + timedelta(days=1),
            },
            {
                'label': 'Classroom announcement automation',
                'detail': 'Add a Planner reminder to post a class update, revision note, or schedule reminder.',
                'href': reverse('classes'),
                'value': teacher_class_count,
                'priority': 'low',
                'cadence': 'Weekly',
                'enabled': has_teacher_classes,
                'due_date': today + timedelta(days=2),
            },
            {
                'label': 'AI revision generator automation',
                'detail': 'Queue a weekly AI quiz generation task for fast warmups and exit checks.',
                'href': reverse('ai_quiz'),
                'value': 'AI',
                'priority': 'low',
                'cadence': 'Weekly',
                'enabled': has_teacher_classes,
                'due_date': today + timedelta(days=3),
            },
        ]
        workflow_recipes = [
            {
                'label': 'Class week starter',
                'detail': 'A ready routine for attendance, homework, assignments, class updates, and AI warmups.',
                'badge': 'Teacher OS',
                'href': reverse('classes'),
                'tasks': [
                    {'title': 'Close attendance for active classes', 'description': 'Mark today attendance and review any missing class records.', 'priority': 'high', 'due_date': today},
                    {'title': 'Publish this week classroom update', 'description': 'Post a concise notice with class priorities, deadlines, and study guidance.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Plan assignment and homework cadence', 'description': 'Check assignment and homework timelines for the week.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Generate an AI warmup quiz', 'description': 'Create a short revision quiz for the next class session.', 'priority': 'low', 'due_date': today + timedelta(days=2)},
                ],
            },
            {
                'label': 'Grading catch-up sprint',
                'detail': 'Bundles grading, feedback, and missing-work communication into one focused workflow.',
                'badge': 'Grading',
                'href': reverse('assignments'),
                'tasks': [
                    {'title': 'Review ungraded submissions', 'description': 'Open assignment submissions and clear the highest-priority grading queue.', 'priority': 'high', 'due_date': today},
                    {'title': 'Return feedback to students', 'description': 'Add actionable comments where students need correction or next steps.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Message students with missing work', 'description': 'Send a clear reminder about incomplete assignments or homework.', 'priority': 'medium', 'due_date': today + timedelta(days=2)},
                ],
            },
            {
                'label': 'Revision week bundle',
                'detail': 'Creates a teaching plan around recordings, study material, AI quizzes, and reminders.',
                'badge': 'Revision',
                'href': reverse('ai_quiz'),
                'tasks': [
                    {'title': 'Prepare revision quiz', 'description': 'Generate questions for the next revision or quick check session.', 'priority': 'medium', 'due_date': today},
                    {'title': 'Review class recordings and materials', 'description': 'Make sure students can access the right recordings and study resources.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Post revision reminder', 'description': 'Share a classroom update with topics, schedule, and expected preparation.', 'priority': 'low', 'due_date': today + timedelta(days=2)},
                ],
            },
        ]
        signal_cards = [
            {'label': 'Teaching classes', 'value': teacher_class_count, 'detail': 'Assigned classroom spaces', 'tone': 'success'},
            {'label': 'Students', 'value': students_count, 'detail': 'Learners across your classes', 'tone': 'success'},
            {'label': 'Attendance today', 'value': f"{attendance_today['percent']}%", 'detail': f"{attendance_today['total']} attendance records today", 'tone': 'warning' if missing_attendance else 'success'},
            {'label': 'Pending grading', 'value': pending_submissions, 'detail': 'Submissions waiting for review', 'tone': 'warning' if pending_submissions else 'success'},
            {'label': 'Due this week', 'value': assignment_due + homework_due, 'detail': f'{assignment_due} assignments, {homework_due} homework', 'tone': 'warning' if assignment_due or homework_due else 'success'},
            {'label': 'Unread messages', 'value': unread_count, 'detail': 'Inbox items from your network', 'tone': 'warning' if unread_count else 'success'},
        ]
        workload_items = [
            {'label': 'Review submissions', 'detail': 'Grade pending student work', 'value': pending_submissions, 'href': reverse('assignments')},
            {'label': 'Mark attendance', 'detail': 'Complete today attendance for active classes', 'value': len(missing_attendance), 'href': reverse('mark_attendance')},
            {'label': 'Publish homework', 'detail': 'Keep class practice visible', 'value': homework_due, 'href': reverse('homework')},
            {'label': 'Recordings', 'detail': 'Upload or review lesson replays', 'value': recording_count, 'href': reverse('recordings')},
            {'label': 'Class messages', 'detail': 'Coordinate with students', 'value': unread_count, 'href': reverse('inbox')},
        ]
        risk_items = missing_attendance + _low_attendance_rows(students_qs, attendance_qs, limit=4)
        if not risk_items:
            risk_items.append({'label': 'Teaching flow', 'detail': 'No urgent class risks found for today.', 'value': 'Clear', 'tone': 'success'})
        for assignment in Assignment.objects.filter(course_class__in=teacher_classes, due_date__gte=now).select_related('course_class').order_by('due_date')[:4]:
            upcoming_items.append({'label': assignment.title, 'detail': assignment.course_class.subject, 'value': assignment.due_date.strftime('%d %b'), 'href': reverse('assignment_detail', args=[assignment.id])})
        quick_links = [
            {'label': 'Planner', 'detail': 'Plan today classes and tasks', 'href': reverse('planner')},
            {'label': 'Classrooms', 'detail': 'Open your class spaces', 'href': reverse('classes')},
            {'label': 'Attendance', 'detail': 'Mark class attendance', 'href': reverse('mark_attendance')},
            {'label': 'Assignments', 'detail': 'Publish and grade work', 'href': reverse('assignments')},
            {'label': 'Homework', 'detail': 'Plan daily practice', 'href': reverse('homework')},
            {'label': 'AI Quiz Gen', 'detail': 'Draft quick revision checks', 'href': reverse('ai_quiz')},
            {'label': 'Messages', 'detail': 'Open your inbox', 'href': reverse('inbox')},
        ]
        recent_activity = ActivityLog.objects.filter(Q(user=user) | Q(user__in=students_qs)).select_related('user').distinct()[:6]

    else:
        enrolled_classes = visible_classes
        attendance_qs = AttendanceRecord.objects.filter(student=user)
        attendance_all = _attendance_percent(attendance_qs)
        if attendance_all['total'] > 0:
            needed = max(0, round((75 * attendance_all['total'] - 100 * attendance_all['present']) / 25))
        else:
            needed = 0
        pending_assignments_qs = Assignment.objects.filter(
            course_class__in=enrolled_classes,
            due_date__gte=now,
        ).exclude(submissions__student=user)
        due_homework_qs = HomeworkEntry.objects.filter(
            course_class__in=enrolled_classes,
            due_date__gte=today,
            due_date__lte=today + timedelta(days=7),
        ).select_related('course_class').distinct()
        recordings = ClassRecording.objects.filter(course_class__in=enrolled_classes).count()
        average_grade = _grade_average_for_student(user)
        pending_assignment_count = pending_assignments_qs.count()
        has_pending_assignments = pending_assignment_count > 0
        due_homework_count = due_homework_qs.count()
        has_due_homework = due_homework_count > 0
        next_assignment = pending_assignments_qs.select_related('course_class').order_by('due_date').first()
        power_briefing = [
            {
                'label': 'Next assignment',
                'value': next_assignment.due_date.strftime('%d %b') if next_assignment else 'Clear',
                'detail': next_assignment.title if next_assignment else 'No upcoming assignment submission is pending.',
                'href': reverse('assignment_detail', args=[next_assignment.id]) if next_assignment else reverse('assignments'),
                'tone': 'warning' if next_assignment else 'success',
            },
            {
                'label': 'Attendance health',
                'value': f"{attendance_all['percent']}%",
                'detail': f"{attendance_all['present']}/{attendance_all['total']} classes attended.",
                'href': reverse('my_attendance'),
                'tone': 'warning' if attendance_all['percent'] < 75 else 'success',
            },
            {
                'label': 'Homework queue',
                'value': due_homework_count,
                'detail': 'Homework items due in the next seven days.',
                'href': reverse('homework'),
                'tone': 'warning' if has_due_homework else 'success',
            },
            {
                'label': 'Study support',
                'value': unread_count,
                'detail': 'Unread messages waiting in your inbox.',
                'href': reverse('inbox'),
                'tone': 'warning' if unread_count else 'success',
            },
        ]
        if has_pending_assignments:
            power_playbook.append({
                'label': 'Submit pending assignments',
                'detail': 'Finish the most urgent pending classwork before the due date.',
                'href': reverse('assignments'),
                'value': pending_assignment_count,
                'priority': 'high',
            })
        if attendance_all['total'] and attendance_all['percent'] < 75:
            power_playbook.append({
                'label': 'Plan attendance recovery',
                'detail': 'Use the planner to protect upcoming classes and recover your attendance percentage.',
                'href': reverse('planner'),
                'value': f"{attendance_all['percent']}%",
                'priority': 'high',
            })
        if has_due_homework:
            power_playbook.append({
                'label': 'Finish weekly homework',
                'detail': 'Review homework due soon and mark a focused work block in Planner.',
                'href': reverse('homework'),
                'value': due_homework_count,
                'priority': 'medium',
            })
        if average_grade and average_grade < 60:
            power_playbook.append({
                'label': 'Start a grade recovery plan',
                'detail': 'Open study tools, review recent work, and create a revision task.',
                'href': reverse('ai_chat'),
                'value': f'{average_grade}%',
                'priority': 'medium',
            })
        power_playbook.append({
            'label': 'Ask Study Buddy for revision help',
            'detail': 'Use AI study support to explain a difficult topic or generate a practice plan.',
            'href': reverse('ai_chat'),
            'value': 'AI',
            'priority': 'low',
        })
        automation_deck = [
            {
                'label': 'Assignment due-date automation',
                'detail': 'Create a Planner block for pending assignments before their due dates arrive.',
                'href': reverse('assignments'),
                'value': pending_assignment_count,
                'priority': 'high' if has_pending_assignments else 'medium',
                'cadence': 'Daily',
                'enabled': has_pending_assignments,
                'due_date': today,
            },
            {
                'label': 'Attendance recovery automation',
                'detail': 'Add a recovery task when attendance is under the target percentage.',
                'href': reverse('my_attendance'),
                'value': f"{attendance_all['percent']}%",
                'priority': 'high',
                'cadence': 'Live',
                'enabled': attendance_all['total'] and attendance_all['percent'] < 75,
                'due_date': today,
            },
            {
                'label': 'Homework focus automation',
                'detail': 'Schedule a focused homework session for work due in the next seven days.',
                'href': reverse('homework'),
                'value': due_homework_count,
                'priority': 'medium',
                'cadence': 'Weekly',
                'enabled': has_due_homework,
                'due_date': today + timedelta(days=1),
            },
            {
                'label': 'Grade recovery automation',
                'detail': 'Create a revision task when the recorded average needs attention.',
                'href': reverse('ai_chat'),
                'value': f'{average_grade}%',
                'priority': 'medium',
                'cadence': 'Weekly',
                'enabled': average_grade < 60,
                'due_date': today + timedelta(days=1),
            },
            {
                'label': 'Study Buddy automation',
                'detail': 'Add a weekly AI study support session for revision, explanations, and practice.',
                'href': reverse('ai_chat'),
                'value': 'AI',
                'priority': 'low',
                'cadence': 'Weekly',
                'enabled': True,
                'due_date': today + timedelta(days=2),
            },
        ]
        workflow_recipes = [
            {
                'label': 'Submission sprint',
                'detail': 'A focused plan for pending assignments, homework, messages, and due-date control.',
                'badge': 'Student OS',
                'href': reverse('assignments'),
                'tasks': [
                    {'title': 'Finish pending assignments', 'description': 'Open assignments and complete the most urgent submission first.', 'priority': 'high', 'due_date': today},
                    {'title': 'Clear weekly homework', 'description': 'Review homework due this week and schedule a focused work block.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Check teacher messages', 'description': 'Read inbox updates before submitting or revising work.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                ],
            },
            {
                'label': 'Attendance recovery plan',
                'detail': 'Turns attendance risk into a simple week-by-week recovery checklist.',
                'badge': 'Attendance',
                'href': reverse('my_attendance'),
                'tasks': [
                    {'title': 'Check attendance by subject', 'description': 'Review which classes need the most attendance recovery.', 'priority': 'high', 'due_date': today},
                    {'title': 'Protect upcoming class schedule', 'description': 'Use Planner and timetable to block upcoming classes.', 'priority': 'high', 'due_date': today + timedelta(days=1)},
                    {'title': 'Ask teacher about recovery options', 'description': 'Send a clear message if you need support improving attendance.', 'priority': 'medium', 'due_date': today + timedelta(days=2)},
                ],
            },
            {
                'label': 'Exam revision pack',
                'detail': 'Bundles recordings, AI Study Buddy, flashcards, notes, and quiz practice into one revision lane.',
                'badge': 'Revision',
                'href': reverse('ai_chat'),
                'tasks': [
                    {'title': 'Ask Study Buddy for a revision plan', 'description': 'Generate a topic-by-topic study plan for the next exam or assessment.', 'priority': 'medium', 'due_date': today},
                    {'title': 'Replay important class recordings', 'description': 'Review recordings connected to weak topics or missed classes.', 'priority': 'medium', 'due_date': today + timedelta(days=1)},
                    {'title': 'Create practice quiz session', 'description': 'Use AI Quiz Gen or flashcards for quick self-testing.', 'priority': 'low', 'due_date': today + timedelta(days=2)},
                ],
            },
        ]
        signal_cards = [
            {'label': 'Attendance', 'value': f"{attendance_all['percent']}%", 'detail': f"{attendance_all['present']}/{attendance_all['total']} classes attended", 'tone': 'warning' if attendance_all['percent'] < 75 else 'success'},
            {'label': 'Target classes', 'value': needed, 'detail': 'Classes needed to reach 75%', 'tone': 'warning' if needed else 'success'},
            {'label': 'Assignments due', 'value': pending_assignment_count, 'detail': 'Work still waiting for submission', 'tone': 'warning' if has_pending_assignments else 'success'},
            {'label': 'Homework week', 'value': due_homework_count, 'detail': 'Homework items due soon', 'tone': 'warning' if has_due_homework else 'success'},
            {'label': 'Average grade', 'value': f'{average_grade}%', 'detail': 'Current recorded exam average', 'tone': 'success' if average_grade >= 60 else 'warning'},
            {'label': 'Unread messages', 'value': unread_count, 'detail': 'Messages waiting in your inbox', 'tone': 'warning' if unread_count else 'success'},
        ]
        workload_items = [
            {'label': 'Submit assignments', 'detail': 'Finish pending classwork before due dates', 'value': pending_assignment_count, 'href': reverse('assignments')},
            {'label': 'Homework planner', 'detail': 'Review upcoming daily practice', 'value': due_homework_count, 'href': reverse('homework')},
            {'label': 'Replay recordings', 'detail': 'Lesson replays available for revision', 'value': recordings, 'href': reverse('recordings')},
            {'label': 'Study tools', 'detail': 'Open AI chat, quiz, notes, and translation', 'value': 'Open', 'href': reverse('ai_chat')},
            {'label': 'Messages', 'detail': 'Read teacher and class communication', 'value': unread_count, 'href': reverse('inbox')},
        ]
        for assignment in pending_assignments_qs.select_related('course_class').order_by('due_date')[:4]:
            upcoming_items.append({'label': assignment.title, 'detail': assignment.course_class.subject, 'value': assignment.due_date.strftime('%d %b'), 'href': reverse('assignment_detail', args=[assignment.id])})
        for homework in due_homework_qs[:4]:
            upcoming_items.append({'label': homework.course_class.subject, 'detail': homework.description[:90], 'value': homework.due_date.strftime('%d %b'), 'href': reverse('homework')})
        if attendance_all['percent'] < 75 and attendance_all['total']:
            risk_items.append({'label': 'Attendance target', 'detail': 'Attend upcoming classes to recover your percentage.', 'value': f"{attendance_all['percent']}%", 'tone': 'warning'})
        if has_pending_assignments:
            risk_items.append({'label': 'Assignment queue', 'detail': 'You still have unsubmitted assignments.', 'value': pending_assignment_count, 'tone': 'warning'})
        if not risk_items:
            risk_items.append({'label': 'Student flow', 'detail': 'No urgent academic risks found from current data.', 'value': 'Clear', 'tone': 'success'})
        quick_links = [
            {'label': 'Planner', 'detail': 'See today work and study tasks', 'href': reverse('planner')},
            {'label': 'Classrooms', 'detail': 'Open your enrolled classes', 'href': reverse('classes')},
            {'label': 'Assignments', 'detail': 'Submit classwork', 'href': reverse('assignments')},
            {'label': 'Homework', 'detail': 'Review daily tasks', 'href': reverse('homework')},
            {'label': 'Attendance', 'detail': 'Track attendance by subject', 'href': reverse('my_attendance')},
            {'label': 'Grades', 'detail': 'Check academic results', 'href': reverse('grades')},
            {'label': 'Study Buddy', 'detail': 'Get study support', 'href': reverse('ai_chat')},
        ]
        recent_activity = ActivityLog.objects.filter(user=user)[:6]

    automation_ready = [item for item in automation_deck if item.get('enabled')]
    automation_summary = {
        'ready': len(automation_ready),
        'total': len(automation_deck),
        'high': sum(1 for item in automation_ready if item.get('priority') == 'high'),
    }

    return render(request, 'dashboard/smart_command_center.html', {
        'role_label': user.get_role_display(),
        'institution_name': user.institution_label,
        'signal_cards': signal_cards,
        'workload_items': workload_items,
        'risk_items': risk_items,
        'upcoming_items': upcoming_items[:8],
        'quick_links': quick_links,
        'recent_activity': recent_activity,
        'open_requests': open_requests,
        'can_manage_requests': is_admin_role(user),
        'power_briefing': power_briefing,
        'power_playbook': power_playbook,
        'automation_deck': automation_deck,
        'automation_summary': automation_summary,
        'workflow_recipes': workflow_recipes,
        'today': today,
    })


def _planner_selected_date(request):
    raw_date = request.POST.get('planner_date') or request.GET.get('date')
    if raw_date:
        try:
            return date.fromisoformat(raw_date)
        except ValueError:
            return date.today()
    return date.today()


def _planner_due_date(value, fallback):
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


@login_required
def planner_view(request):
    user = request.user
    selected_date = _planner_selected_date(request)
    visible_classes = _visible_classes_for_user(user)

    if request.method == 'POST':
        action = request.POST.get('action')
        redirect_url = f"{reverse('planner')}?date={selected_date.isoformat()}"

        if action == 'add':
            title = (request.POST.get('title') or '').strip()
            priority = request.POST.get('priority', 'medium')
            due_date = _planner_due_date(request.POST.get('due_date'), selected_date)
            if title:
                TodoItem.objects.create(
                    user=user,
                    title=title,
                    description=(request.POST.get('description') or '').strip(),
                    priority=priority if priority in {'low', 'medium', 'high'} else 'medium',
                    due_date=due_date,
                )
                messages.success(request, 'Planner task added.')
        elif action == 'capture':
            title = (request.POST.get('title') or '').strip()
            detail = (request.POST.get('description') or '').strip()
            due_date = _planner_due_date(request.POST.get('due_date'), selected_date)
            if title and not TodoItem.objects.filter(user=user, title__iexact=title, is_done=False).exists():
                TodoItem.objects.create(user=user, title=title, description=detail, priority='medium', due_date=due_date)
                messages.success(request, 'Saved to your planner tasks.')
            elif title:
                messages.info(request, 'That task is already in your planner.')
        elif action == 'toggle':
            todo = TodoItem.objects.filter(id=request.POST.get('todo_id'), user=user).first()
            if todo:
                todo.is_done = not todo.is_done
                todo.save(update_fields=['is_done'])
        elif action == 'delete':
            TodoItem.objects.filter(id=request.POST.get('todo_id'), user=user).delete()

        return redirect(redirect_url)

    day_key = f"{selected_date.weekday() + 1}_{selected_date.strftime('%A').lower()}"
    schedules = ClassSchedule.objects.filter(
        course_class__in=visible_classes,
        day_of_week=day_key,
    ).select_related('course_class', 'course_class__teacher')

    assignment_qs = Assignment.objects.filter(course_class__in=visible_classes)
    if user.role == 'student':
        assignment_qs = assignment_qs.exclude(submissions__student=user)
    assignments_due = assignment_qs.filter(due_date__date=selected_date).select_related('course_class')[:8]

    homework_due = HomeworkEntry.objects.filter(
        course_class__in=visible_classes,
        due_date=selected_date,
    ).select_related('course_class')[:8]

    exams_today = Exam.objects.filter(
        course_class__in=visible_classes,
        date=selected_date,
    ).select_related('course_class')[:8]

    events_today = Event.objects.filter(event_date=selected_date)
    if not is_platform_admin(user):
        events_today = events_today.filter(Q(course_class__isnull=True) | Q(course_class__in=visible_classes)).distinct()
    events_today = events_today.select_related('course_class')[:8]

    attendance_qs = AttendanceRecord.objects.filter(date=selected_date)
    if user.role == 'student':
        attendance_qs = attendance_qs.filter(student=user)
    else:
        attendance_qs = attendance_qs.filter(course_class__in=visible_classes)
    attendance_summary = _attendance_percent(attendance_qs)

    todos = TodoItem.objects.filter(user=user)
    focus_tasks = todos.filter(is_done=False).filter(Q(due_date__isnull=True) | Q(due_date__lte=selected_date))[:8]
    overdue_count = todos.filter(is_done=False, due_date__lt=date.today()).count()
    completed_count = todos.filter(is_done=True).count()
    pending_count = todos.filter(is_done=False).count()

    due_items = []
    for assignment in assignments_due:
        due_items.append({
            'type': 'Assignment',
            'title': assignment.title,
            'detail': assignment.course_class.subject,
            'time': assignment.due_date.strftime('%I:%M %p'),
            'href': reverse('assignment_detail', args=[assignment.id]),
            'capture_title': f"Submit assignment: {assignment.title}",
        })
    for homework in homework_due:
        due_items.append({
            'type': 'Homework',
            'title': homework.course_class.subject,
            'detail': homework.description[:120],
            'time': 'Due today',
            'href': reverse('homework'),
            'capture_title': f"Complete homework: {homework.course_class.subject}",
        })
    for exam in exams_today:
        due_items.append({
            'type': 'Exam',
            'title': exam.title,
            'detail': f'{exam.course_class.subject} - {exam.get_exam_type_display()}',
            'time': 'Today',
            'href': reverse('exam_seating'),
            'capture_title': f"Prepare for exam: {exam.title}",
        })
    for event in events_today:
        due_items.append({
            'type': 'Event',
            'title': event.title,
            'detail': event.get_event_type_display(),
            'time': 'Today',
            'href': reverse('calendar'),
            'capture_title': f"Follow up: {event.title}",
        })

    unread_messages = Message.objects.filter(receiver=user, is_read=False).select_related('sender')[:5]
    recent_materials = StudyMaterial.objects.filter(course_class__in=visible_classes).select_related('course_class')[:5]
    class_count = visible_classes.count()
    next_date = selected_date + timedelta(days=1)
    previous_date = selected_date - timedelta(days=1)

    if focus_tasks.exists():
        next_action = 'Finish the first open planner task.'
    elif due_items:
        next_action = 'Review the first due item and capture a follow-up task if needed.'
    elif schedules.exists():
        next_action = 'Open your schedule and prepare for the next class block.'
    elif unread_messages.exists():
        next_action = 'Clear unread messages before moving on.'
    else:
        next_action = 'Your planner is clear. Add one priority task for the day.'

    planner_stats = [
        {'label': 'Classes today', 'value': schedules.count(), 'detail': 'Scheduled class blocks'},
        {'label': 'Due items', 'value': len(due_items), 'detail': 'Assignments, homework, exams, and events'},
        {'label': 'Open tasks', 'value': pending_count, 'detail': f'{completed_count} completed overall'},
        {'label': 'Attendance', 'value': f"{attendance_summary['percent']}%", 'detail': f"{attendance_summary['present']}/{attendance_summary['total']} present"},
    ]

    return render(request, 'dashboard/planner.html', {
        'selected_date': selected_date,
        'previous_date': previous_date,
        'next_date': next_date,
        'today': date.today(),
        'planner_stats': planner_stats,
        'schedules': schedules,
        'due_items': due_items,
        'focus_tasks': focus_tasks,
        'pending_count': pending_count,
        'completed_count': completed_count,
        'overdue_count': overdue_count,
        'unread_messages': unread_messages,
        'recent_materials': recent_materials,
        'next_action': next_action,
        'class_count': class_count,
    })


def admin_dashboard(request, user, today):
    platform_admin = is_platform_admin(user)
    institution_admin = is_institution_admin(user)
    institution = user.institution
    scoped_user_qs = scoped_users(user)
    scoped_class_qs = scoped_classes(user)
    scoped_department_qs = scoped_departments(user)

    total_students = scoped_user_qs.filter(role='student').count()
    total_teachers = scoped_user_qs.filter(role='teacher').count()
    total_classes = scoped_class_qs.count()
    open_inquiries_qs = PlatformInquiry.objects.exclude(status='closed')
    new_inquiries_qs = PlatformInquiry.objects.filter(status='new')
    complaints_qs = Complaint.objects.exclude(status__in=['resolved', 'closed'])
    resources_qs = LibraryResource.objects.all()
    attendance_qs = AttendanceRecord.objects.all()
    leave_qs = LeaveRequest.objects.filter(status='pending')
    assignment_qs = Assignment.objects.all()
    notices_qs = Notice.objects.all()

    if institution_admin:
        if institution_id := user.institution_id:
            open_inquiries_qs = open_inquiries_qs.filter(linked_institution_id=institution_id)
            new_inquiries_qs = new_inquiries_qs.filter(linked_institution_id=institution_id)
            complaints_qs = complaints_qs.filter(filed_by__institution_id=institution_id)
            resources_qs = resources_qs.filter(
                Q(course_class__institution_id=institution_id) |
                Q(uploaded_by__institution_id=institution_id)
            ).distinct()
            attendance_qs = attendance_qs.filter(
                Q(course_class__institution_id=institution_id) |
                Q(student__institution_id=institution_id)
            ).distinct()
            leave_qs = leave_qs.filter(student__institution_id=institution_id)
            assignment_qs = assignment_qs.filter(course_class__institution_id=institution_id)
            notices_qs = notices_qs.filter(
                Q(target_class__institution_id=institution_id) |
                Q(target_class__isnull=True, author__institution_id=institution_id)
            ).distinct()
        else:
            open_inquiries_qs = open_inquiries_qs.none()
            new_inquiries_qs = new_inquiries_qs.none()
            complaints_qs = complaints_qs.none()
            resources_qs = resources_qs.none()
            attendance_qs = attendance_qs.none()
            leave_qs = leave_qs.none()
            assignment_qs = assignment_qs.none()
            notices_qs = notices_qs.none()

    open_inquiries = open_inquiries_qs.count()
    new_inquiries = new_inquiries_qs.count()
    active_complaints = complaints_qs.count()
    total_resources = resources_qs.count()
    plugin_cards = _build_plugin_cards(user)
    department_names = list(scoped_department_qs.values_list('name', flat=True))
    legacy_department_names = [d for d in scoped_class_qs.values_list('department', flat=True).distinct() if d]
    departments = sorted(set(department_names + legacy_department_names))

    dept_data = []
    for dept in departments:
        students = scoped_user_qs.filter(role='student', department=dept).count()
        teachers = scoped_user_qs.filter(role='teacher', department=dept).count()
        classes = scoped_class_qs.filter(department=dept).count()
        dept_data.append({
            'name': dept,
            'students': students,
            'teachers': teachers,
            'classes': classes,
        })

    total_records_today = attendance_qs.filter(date=today).count()
    present_today = attendance_qs.filter(date=today, status='present').count()
    avg_attendance = round((present_today / total_records_today * 100) if total_records_today > 0 else 0)
    recent_notices = notices_qs[:3]
    dept_names_json = json.dumps([d['name'] for d in dept_data])
    dept_students_json = json.dumps([d['students'] for d in dept_data])
    dept_teachers_json = json.dumps([d['teachers'] for d in dept_data])

    trend_labels = []
    trend_present = []
    trend_absent = []
    for i in range(7):
        d = today - timedelta(days=6 - i)
        day_records = attendance_qs.filter(date=d)
        trend_labels.append(d.strftime('%d %b'))
        trend_present.append(day_records.filter(status='present').count())
        trend_absent.append(day_records.filter(status='absent').count())

    pending_leaves = leave_qs.count()
    total_assignments = assignment_qs.count()
    unread_count = Message.objects.filter(receiver=user, is_read=False).count()

    context = {
        'platform_admin': platform_admin,
        'institution_admin': institution_admin,
        'institution_name': user.institution_label,
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_classes': total_classes,
        'avg_attendance': avg_attendance,
        'dept_data': dept_data,
        'recent_notices': recent_notices,
        'dept_names_json': dept_names_json,
        'dept_students_json': dept_students_json,
        'dept_teachers_json': dept_teachers_json,
        'trend_labels_json': json.dumps(trend_labels),
        'trend_present_json': json.dumps(trend_present),
        'trend_absent_json': json.dumps(trend_absent),
        'pending_leaves': pending_leaves,
        'total_assignments': total_assignments,
        'unread_count': unread_count,
        'open_inquiries': open_inquiries,
        'new_inquiries': new_inquiries,
        'active_complaints': active_complaints,
        'total_resources': total_resources,
        'plugin_cards': plugin_cards[:4],
        'plugin_live_count': sum(1 for card in plugin_cards if card['tone'] == 'success'),
        'plugin_total_count': len(plugin_cards),
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


def teacher_dashboard(request, user, today):
    teacher_classes = CourseClass.objects.filter(teacher=user)
    if user.institution_id:
        teacher_classes = teacher_classes.filter(institution=user.institution)
    teacher_assignment_count = Assignment.objects.filter(course_class__in=teacher_classes).count()
    total_students = sum(c.students.count() for c in teacher_classes)

    # Today's attendance
    today_records = AttendanceRecord.objects.filter(date=today, course_class__in=teacher_classes)
    present_count = today_records.filter(status='present').count()
    absent_count = today_records.filter(status='absent').count()
    late_count = today_records.filter(status='late').count()
    total_today = today_records.count()
    today_pct = round((present_count / total_today * 100) if total_today > 0 else 0)

    # Pending leave requests
    pending_leaves = LeaveRequest.objects.filter(
        student__enrolled_classes__in=teacher_classes,
        status='pending'
    ).distinct().count()

    # Recent notices
    recent_notices = Notice.objects.filter(Q(target_role='all') | Q(target_role='teacher'))
    if user.institution_id:
        recent_notices = recent_notices.filter(
            Q(target_class__institution=user.institution) |
            Q(target_class__isnull=True, author__institution=user.institution)
        ).distinct()
    recent_notices = recent_notices[:3]

    # Pending submissions to grade
    pending_submissions = Submission.objects.filter(
        assignment__course_class__in=teacher_classes,
        graded=False
    ).count()

    # Unread messages
    unread_count = Message.objects.filter(receiver=user, is_read=False).count()
    assigned_homework = HomeworkEntry.objects.filter(teacher=user, due_date__gte=today).count()
    study_group_count = StudyGroup.objects.filter(Q(created_by=user) | Q(members=user)).distinct().count()
    recording_count = ClassRecording.objects.filter(course_class__in=teacher_classes, uploaded_by=user).count()
    materials_posted = StudyMaterial.objects.filter(course_class__in=teacher_classes).count()
    classroom_tool_cards = [
        {
            'section': 'Classwork',
            'title': 'Assignments',
            'status': f'{teacher_assignment_count} live',
            'tone': 'success' if teacher_assignment_count else 'warning',
            'description': 'Create, publish, and review assignment work inside each classroom.',
            'features': ['Teacher-authored tasks', 'Submission review', 'Marks and due dates'],
            'action_label': 'Open Assignments',
            'action_url': reverse('assignments'),
        },
        {
            'section': 'Classwork',
            'title': 'Homework',
            'status': f'{assigned_homework} active',
            'tone': 'success' if assigned_homework else 'warning',
            'description': 'Keep the homework planner tied to active classrooms and upcoming due dates.',
            'features': ['Daily homework flow', 'Important flags', 'Class-specific tracking'],
            'action_label': 'Open Homework',
            'action_url': reverse('homework'),
        },
        {
            'section': 'Media',
            'title': 'Recordings',
            'status': f'{recording_count} uploaded',
            'tone': 'success' if recording_count else 'warning',
            'description': 'Publish lesson recordings and supporting study materials for each class.',
            'features': ['Video links', 'Duration tracking', 'Replay access for students'],
            'action_label': 'Open Recordings',
            'action_url': reverse('recordings'),
        },
        {
            'section': 'AI',
            'title': 'AI Quiz Gen',
            'status': 'Ready',
            'tone': 'success',
            'description': 'Generate classroom quiz drafts from the subject you are teaching.',
            'features': ['Topic prompts', 'Difficulty control', 'Rapid class revision'],
            'action_label': 'Open AI Quiz',
            'action_url': reverse('ai_quiz'),
        },
    ]

    context = {
        'teacher_classes': teacher_classes,
        'total_students': total_students,
        'today_pct': today_pct,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'pending_leaves': pending_leaves,
        'recent_notices': recent_notices,
        'pending_submissions': pending_submissions,
        'unread_count': unread_count,
        'assigned_homework': assigned_homework,
        'study_group_count': study_group_count,
        'teacher_assignment_count': teacher_assignment_count,
        'recording_count': recording_count,
        'materials_posted': materials_posted,
        'classroom_tool_cards': classroom_tool_cards,
    }
    return render(request, 'dashboard/teacher_dashboard.html', context)


def student_dashboard(request, user, today):
    enrolled_classes = user.enrolled_classes.all()
    if user.institution_id:
        enrolled_classes = enrolled_classes.filter(institution=user.institution)
    all_records = AttendanceRecord.objects.filter(student=user)
    total_records = all_records.count()
    present = all_records.filter(status='present').count()
    absent = all_records.filter(status='absent').count()
    late = all_records.filter(status='late').count()
    overall_pct = round((present / total_records * 100) if total_records > 0 else 0)

    # Classes needed for 75%
    if total_records > 0:
        target = 75
        present_count = present
        needed = max(0, round((target * total_records - 100 * present_count) / (100 - target)))
    else:
        needed = 0

    # Subject-wise breakdown
    subject_data = []
    for cls in enrolled_classes:
        records = all_records.filter(course_class=cls)
        total = records.count()
        pres = records.filter(status='present').count()
        pct = round((pres / total * 100) if total > 0 else 0)
        subject_data.append({
            'id': cls.id,
            'name': cls.subject,
            'class_name': cls.name,
            'percentage': pct,
            'present': pres,
            'total': total,
        })

    # Calendar heatmap (last 28 days)
    heatmap = []
    for i in range(28):
        d = today - timedelta(days=27 - i)
        is_weekend = d.weekday() >= 5
        record = all_records.filter(date=d).first()
        status = 'weekend' if is_weekend else (record.status if record else 'empty')
        heatmap.append({'date': d, 'day': d.day, 'status': status})

    # Recent notices
    recent_notices = Notice.objects.filter(Q(target_role='all') | Q(target_role='student'))
    if user.institution_id:
        recent_notices = recent_notices.filter(
            Q(target_class__institution=user.institution) |
            Q(target_class__isnull=True, author__institution=user.institution)
        ).distinct()
    recent_notices = recent_notices[:3]

    # Pending assignments
    pending_assignments = Assignment.objects.filter(
        course_class__in=enrolled_classes,
        due_date__gte=timezone.now()
    ).exclude(
        submissions__student=user
    ).count()

    # Unread messages
    unread_count = Message.objects.filter(receiver=user, is_read=False).count()

    # XP profile
    xp_profile, _ = StudentXP.objects.get_or_create(student=user)
    grade_records = Grade.objects.filter(student=user).select_related('exam')
    average_grade_pct = 0
    if grade_records.exists():
        average_grade_pct = round(sum(float(g.marks_obtained) / float(g.exam.total_marks) * 100 for g in grade_records) / grade_records.count())
    classroom_recordings = ClassRecording.objects.filter(course_class__students=user).distinct().count()
    active_classrooms = enrolled_classes.count()
    due_homework = HomeworkEntry.objects.filter(course_class__students=user, due_date__gte=today).distinct().count()
    plugin_cards = _build_plugin_cards(user)

    context = {
        'enrolled_classes': enrolled_classes,
        'overall_pct': overall_pct,
        'present': present,
        'absent': absent,
        'late': late,
        'total_records': total_records,
        'needed': needed,
        'subject_data': subject_data,
        'heatmap': heatmap,
        'recent_notices': recent_notices,
        'pending_assignments': pending_assignments,
        'unread_count': unread_count,
        'xp_profile': xp_profile,
        'average_grade_pct': average_grade_pct,
        'classroom_recordings': classroom_recordings,
        'active_classrooms': active_classrooms,
        'due_homework': due_homework,
        'plugin_cards': plugin_cards[:4],
    }
    return render(request, 'dashboard/student_dashboard.html', context)


@login_required
def departments_view(request):
    if not is_admin_role(request.user):
        messages.error(request, 'Only administrators can manage departments.')
        return redirect('dashboard_home')

    department_qs = scoped_departments(request.user)
    if request.method == 'POST':
        action = request.POST.get('action')
        department_id = request.POST.get('department_id')
        name = (request.POST.get('name') or '').strip()
        code = (request.POST.get('code') or '').strip().upper() or None
        description = (request.POST.get('description') or '').strip()
        institution = request.user.institution if is_institution_admin(request.user) else None

        if action == 'create':
            if not name:
                messages.error(request, 'Department name is required.')
            elif department_qs.filter(name__iexact=name, institution=institution).exists():
                messages.error(request, 'A department with this name already exists.')
            elif code and department_qs.filter(code__iexact=code, institution=institution).exists():
                messages.error(request, 'A department with this code already exists.')
            else:
                Department.objects.create(
                    institution=institution,
                    name=name,
                    code=code,
                    description=description,
                    created_by=request.user,
                )
                messages.success(request, 'Department created.')
        elif action == 'update':
            department = get_object_or_404(department_qs, id=department_id)
            if not name:
                messages.error(request, 'Department name is required.')
            elif department_qs.filter(name__iexact=name, institution=department.institution).exclude(id=department.id).exists():
                messages.error(request, 'A department with this name already exists.')
            elif code and department_qs.filter(code__iexact=code, institution=department.institution).exclude(id=department.id).exists():
                messages.error(request, 'A department with this code already exists.')
            else:
                old_name = department.name
                department.name = name
                department.code = code
                department.description = description
                department.save()
                scoped_classes(request.user).filter(department=old_name).update(department=department.name)
                scoped_users(request.user).filter(department=old_name).update(department=department.name)
                messages.success(request, 'Department updated.')
        elif action == 'toggle':
            department = get_object_or_404(department_qs, id=department_id)
            department.is_active = not department.is_active
            department.save(update_fields=['is_active', 'updated_at'])
            messages.success(request, 'Department status updated.')

        return redirect('departments')

    departments = department_qs
    dept_data = []
    for dept in departments:
        dept_data.append({
            'department': dept,
            'name': dept.name,
            'code': dept.code,
            'description': dept.description,
            'is_active': dept.is_active,
            'classes': scoped_classes(request.user).filter(department=dept.name).count(),
            'teachers': scoped_users(request.user).filter(role='teacher', department=dept.name).count(),
            'students': scoped_users(request.user).filter(role='student', department=dept.name).count(),
        })
    return render(request, 'dashboard/departments.html', {
        'dept_data': dept_data,
        'can_manage_departments': is_admin_role(request.user),
        'institution_name': request.user.institution_label,
    })


@login_required
def classes_view(request):
    active_departments = scoped_departments(request.user).filter(is_active=True)
    if request.method == 'POST':
        action = request.POST.get('action')
        if is_admin_role(request.user) or request.user.role == 'teacher':
            if action == 'add':
                name = request.POST.get('name')
                subject = request.POST.get('subject')
                department = (request.POST.get('department') or '').strip()
                semester = request.POST.get('semester')
                teacher_id = request.POST.get('teacher_id') if is_admin_role(request.user) else request.user.id
                teacher = User.objects.filter(id=teacher_id, role='teacher').first()
                institution = None
                if request.user.role == 'teacher':
                    institution = request.user.institution
                elif is_institution_admin(request.user):
                    institution = request.user.institution
                    if teacher and teacher.institution_id != request.user.institution_id:
                        messages.error(request, 'Choose a teacher from your own institution.')
                        return redirect('classes')
                elif teacher:
                    institution = teacher.institution
                if not active_departments.filter(name=department).exists():
                    messages.error(request, 'Choose an active department before creating a class.')
                elif name and subject and teacher_id and teacher:
                    CourseClass.objects.create(
                        institution=institution,
                        name=name,
                        subject=subject,
                        department=department,
                        semester=semester,
                        teacher_id=teacher_id,
                    )
                    messages.success(request, 'Class created.')
            elif action == 'delete':
                class_id = request.POST.get('class_id')
                if is_platform_admin(request.user):
                    CourseClass.objects.filter(id=class_id).delete()
                elif is_institution_admin(request.user):
                    scoped_classes(request.user).filter(id=class_id).delete()
                else:
                    CourseClass.objects.filter(id=class_id, teacher=request.user).delete()
        elif request.user.role == 'student':
            if action == 'join':
                class_code = request.POST.get('class_code')
                try:
                    clsToJoin = CourseClass.objects.get(class_code=class_code)
                    if request.user.institution_id and clsToJoin.institution_id != request.user.institution_id:
                        messages.error(request, 'This classroom belongs to a different institution.')
                        return redirect('classes')
                    clsToJoin.students.add(request.user)
                    messages.success(request, 'Class joined.')
                except CourseClass.DoesNotExist:
                    messages.error(request, 'Invalid class code.')
        return redirect('classes')

    if request.user.role == 'teacher':
        classes = CourseClass.objects.filter(teacher=request.user)
        if request.user.institution_id:
            classes = classes.filter(institution=request.user.institution)
    elif request.user.role == 'student':
        classes = request.user.enrolled_classes.all()
        if request.user.institution_id:
            classes = classes.filter(institution=request.user.institution)
    elif is_institution_admin(request.user):
        classes = scoped_classes(request.user)
    else:
        classes = CourseClass.objects.all()
    teachers = scoped_users(request.user).filter(role='teacher')
    return render(request, 'dashboard/classes.html', {
        'classes': classes,
        'teachers': teachers,
        'departments': active_departments,
        'can_manage_classes': is_admin_role(request.user) or request.user.role == 'teacher',
        'institution_name': request.user.institution_label,
    })


@login_required
def users_list_view(request):
    if request.user.role not in ['admin', 'institution_admin', 'teacher']:
        return redirect('dashboard_home')

    can_manage_users = is_admin_role(request.user)

    if request.method == 'POST' and can_manage_users:
        action = request.POST.get('action')
        if action == 'add':
            username = (request.POST.get('username') or '').strip()
            first_name = (request.POST.get('first_name') or '').strip()
            last_name = (request.POST.get('last_name') or '').strip()
            email = (request.POST.get('email') or '').strip().lower()
            role = (request.POST.get('role') or '').strip()
            department = (request.POST.get('department') or '').strip()
            allowed_roles = ['student', 'teacher'] if is_institution_admin(request.user) else ['student', 'teacher', 'institution_admin', 'admin']
            institution = request.user.institution if is_institution_admin(request.user) else None
            if role not in allowed_roles:
                messages.error(request, 'You cannot assign that role.')
            elif not username or not email:
                messages.error(request, 'Username and email are required.')
            elif User.objects.filter(Q(username__iexact=username) | Q(email__iexact=email)).exists():
                messages.error(request, 'That username or email is already in use.')
            else:
                if role != 'admin':
                    institution = institution or Institution.provision_for_email(email)
                    if institution is None:
                        messages.error(request, 'Use a verified institutional email address for teachers, students, and institution admins.')
                        return redirect('users_list')
                temporary_password = secrets.token_urlsafe(12)[:16]
                User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password=temporary_password,
                    role=role,
                    institution=institution,
                    department=department or None,
                    is_staff=role == 'admin',
                )
                messages.success(request, f'User created. Temporary password: {temporary_password}')
        elif action == 'delete':
            user_id = request.POST.get('user_id')
            target_qs = scoped_users(request.user) if is_institution_admin(request.user) else User.objects.all()
            if int(user_id) != request.user.id:
                target_qs.filter(id=user_id).exclude(role='admin').delete()
        elif action == 'edit':
            user_id = request.POST.get('user_id')
            role = (request.POST.get('role') or '').strip()
            target_qs = scoped_users(request.user) if is_institution_admin(request.user) else User.objects.all()
            allowed_roles = ['student', 'teacher'] if is_institution_admin(request.user) else ['student', 'teacher', 'institution_admin', 'admin']
            if role in allowed_roles:
                target_qs.filter(id=user_id).exclude(role='admin').update(role=role)
        return redirect('users_list')

    department_filter = request.GET.get('department')
    if request.user.role == 'teacher':
        users = User.objects.filter(Q(pk=request.user.pk) | Q(role='student', enrolled_classes__teacher=request.user)).distinct()
    else:
        users = scoped_users(request.user)
    if department_filter:
        users = users.filter(department=department_filter)

    users = users.order_by('role', 'username')
    department_names = list(scoped_departments(request.user).filter(is_active=True).values_list('name', flat=True))
    legacy_user_departments = [d for d in users.values_list('department', flat=True).distinct() if d]
    departments_list = sorted(set(department_names + legacy_user_departments))

    return render(request, 'dashboard/users.html', {
        'users_list': users,
        'departments_list': departments_list,
        'selected_department': department_filter,
        'can_manage_users': can_manage_users,
        'role_options': ['student', 'teacher'] if is_institution_admin(request.user) else ['student', 'teacher', 'institution_admin', 'admin'],
        'institution_name': request.user.institution_label,
    })


@login_required
def reports_view(request):
    user = request.user
    today = date.today()

    if user.role == 'teacher':
        teacher_classes = CourseClass.objects.filter(teacher=user)
        if user.institution_id:
            teacher_classes = teacher_classes.filter(institution=user.institution)
        all_records = AttendanceRecord.objects.filter(course_class__in=teacher_classes)
        scope_classes = teacher_classes
    elif user.role == 'student':
        all_records = AttendanceRecord.objects.filter(student=user)
        scope_classes = user.enrolled_classes.all()
        if user.institution_id:
            scope_classes = scope_classes.filter(institution=user.institution)
    elif is_institution_admin(user):
        scope_classes = scoped_classes(user)
        all_records = AttendanceRecord.objects.filter(
            Q(course_class__institution=user.institution) |
            Q(student__institution=user.institution)
        ).distinct() if user.institution_id else AttendanceRecord.objects.none()
    else:
        all_records = AttendanceRecord.objects.all()
        scope_classes = CourseClass.objects.all()

    total_records = all_records.count()
    present_count = all_records.filter(status='present').count()
    absent_count = all_records.filter(status='absent').count()
    late_count = all_records.filter(status='late').count()
    overall_pct = round((present_count / total_records * 100) if total_records > 0 else 0)

    # --- Daily trend (last 14 days) ---
    trend_labels = []
    trend_present = []
    trend_absent = []
    trend_late = []
    for i in range(14):
        d = today - timedelta(days=13 - i)
        day_records = all_records.filter(date=d)
        trend_labels.append(d.strftime('%d %b'))
        trend_present.append(day_records.filter(status='present').count())
        trend_absent.append(day_records.filter(status='absent').count())
        trend_late.append(day_records.filter(status='late').count())

    # --- Class-wise breakdown ---
    class_breakdown = []
    for cls in scope_classes:
        cls_records = all_records.filter(course_class=cls)
        cls_total = cls_records.count()
        cls_present = cls_records.filter(status='present').count()
        cls_pct = round((cls_present / cls_total * 100) if cls_total > 0 else 0)
        class_breakdown.append({
            'name': cls.name,
            'subject': cls.subject,
            'department': cls.department,
            'total': cls_total,
            'present': cls_present,
            'absent': cls_records.filter(status='absent').count(),
            'late': cls_records.filter(status='late').count(),
            'percentage': cls_pct,
        })
    class_breakdown.sort(key=lambda x: x['percentage'], reverse=True)

    # --- Department-wise breakdown (admin/teacher only) ---
    dept_breakdown = []
    if user.role != 'student':
        departments = scope_classes.values_list('department', flat=True).distinct()
        for dept in departments:
            dept_records = all_records.filter(course_class__department=dept)
            dept_total = dept_records.count()
            dept_present = dept_records.filter(status='present').count()
            dept_pct = round((dept_present / dept_total * 100) if dept_total > 0 else 0)
            dept_breakdown.append({
                'name': dept,
                'total': dept_total,
                'present': dept_present,
                'percentage': dept_pct,
            })

    top_students = []
    low_students = []
    if user.role in ('admin', 'teacher', 'institution_admin'):
        student_ids = all_records.values_list('student', flat=True).distinct()
        student_stats = []
        for sid in student_ids:
            s_records = all_records.filter(student_id=sid)
            s_total = s_records.count()
            s_present = s_records.filter(status='present').count()
            s_pct = round((s_present / s_total * 100) if s_total > 0 else 0)
            try:
                student_obj = User.objects.get(id=sid)
                student_stats.append({
                    'name': student_obj.get_full_name() or student_obj.username,
                    'department': student_obj.department or 'Unassigned',
                    'total': s_total,
                    'present': s_present,
                    'percentage': s_pct,
                })
            except User.DoesNotExist:
                pass
        student_stats.sort(key=lambda x: x['percentage'], reverse=True)
        top_students = student_stats[:5]
        low_students = sorted(student_stats, key=lambda x: x['percentage'])[:5]

    context = {
        'total_records': total_records,
        'present_count': present_count,
        'absent_count': absent_count,
        'late_count': late_count,
        'overall_pct': overall_pct,
        'trend_labels_json': json.dumps(trend_labels),
        'trend_present_json': json.dumps(trend_present),
        'trend_absent_json': json.dumps(trend_absent),
        'trend_late_json': json.dumps(trend_late),
        'class_breakdown': class_breakdown,
        'dept_breakdown': dept_breakdown,
        'top_students': top_students,
        'low_students': low_students,
    }
    return render(request, 'dashboard/reports.html', context)


@login_required
def mark_attendance_view(request):
    teacher_classes = CourseClass.objects.filter(teacher=request.user)
    selected_class = None
    students = []
    
    # Date Handling
    date_str = request.GET.get('date') or request.POST.get('date')
    current_date = None
    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass

    class_id = request.GET.get('class_id') or request.POST.get('class_id')
    if class_id:
        try:
            selected_class = CourseClass.objects.get(id=class_id, teacher=request.user)
            students = selected_class.students.order_by('username')
        except CourseClass.DoesNotExist:
            pass

    if request.method == 'POST' and selected_class and current_date:
        for student in students:
            status = request.POST.get(f'status_{student.id}', 'absent')
            AttendanceRecord.objects.update_or_create(
                student=student,
                course_class=selected_class,
                date=current_date,
                defaults={'status': status}
            )
        return redirect(f"{reverse('mark_attendance')}?class_id={selected_class.id}&date={current_date.strftime('%Y-%m-%d')}&saved=1")

    saved = request.GET.get('saved') == '1'

    # Get existing records for chosen date
    existing = {}
    if selected_class and current_date:
        for rec in AttendanceRecord.objects.filter(course_class=selected_class, date=current_date):
            existing[rec.student_id] = rec.status

    # --- Matrix Calculation ---
    matrix_dates = []
    matrix_data = []
    if selected_class:
        # Get all distinct dates where attendance was marked for this class
        records = AttendanceRecord.objects.filter(course_class=selected_class)
        matrix_dates = list(records.values_list('date', flat=True).distinct().order_by('date'))
        
        for student in students:
            student_records = records.filter(student=student)
            student_total = student_records.count()
            student_present = student_records.filter(status='present').count()
            student_pct = round((student_present / student_total * 100) if student_total > 0 else 0)
            
            row = {
                'student': student,
                'statuses': [],
                'present': student_present,
                'total': student_total,
                'percentage': student_pct
            }
            
            # Get status for each date
            for d in matrix_dates:
                rec = student_records.filter(date=d).first()
                row['statuses'].append(rec.status if rec else '—')
                
            matrix_data.append(row)

    context = {
        'teacher_classes': teacher_classes,
        'selected_class': selected_class,
        'students': students,
        'current_date': current_date,
        'saved': saved,
        'existing': existing,
        'matrix_dates': matrix_dates,
        'matrix_data': matrix_data,
    }
    return render(request, 'dashboard/mark_attendance.html', context)


@login_required
def my_attendance_view(request):
    class_id = request.GET.get('class_id')
    records = AttendanceRecord.objects.filter(student=request.user)
    if class_id:
        records = records.filter(course_class_id=class_id)
    records = records.order_by('-date')
    
    enrolled_classes = request.user.enrolled_classes.all()
    selected_class_id = int(class_id) if class_id and class_id.isdigit() else None
    
    return render(request, 'dashboard/my_attendance.html', {
        'records': records, 
        'enrolled_classes': enrolled_classes,
        'selected_class': selected_class_id
    })


@login_required
def leave_requests_view(request):
    user = request.user

    if request.method == 'POST':
        if user.role == 'student':
            req = LeaveRequest.objects.create(
                student=user,
                start_date=request.POST.get('start_date'),
                end_date=request.POST.get('end_date'),
                reason=request.POST.get('reason'),
            )
            teacher_ids = request.POST.getlist('teachers')
            if teacher_ids:
                req.teachers.set(teacher_ids)
            return redirect('leave_requests')
        elif user.role == 'teacher':
            leave_id = request.POST.get('leave_id')
            action = request.POST.get('action')
            if leave_id and action in ('approved', 'rejected'):
                leave = LeaveRequest.objects.get(id=leave_id)
                leave.status = action
                leave.save()
            return redirect('leave_requests')

    if user.role == 'student':
        leaves = LeaveRequest.objects.filter(student=user).order_by('-start_date')
    elif user.role == 'teacher':
        leaves = LeaveRequest.objects.filter(teachers=user).order_by('-start_date')
    else:
        leaves = LeaveRequest.objects.all().order_by('-start_date')

    all_teachers = User.objects.filter(role='teacher') if user.role == 'student' else []
    return render(request, 'dashboard/leave_requests.html', {'leaves': leaves, 'all_teachers': all_teachers})

@login_required
def notices_view(request):
    user = request.user
    
    if request.method == 'POST' and user.role in ('admin', 'institution_admin', 'teacher'):
        title = request.POST.get('title')
        content = request.POST.get('content')
        target_role = request.POST.get('target_role', 'all')
        if title and content:
            Notice.objects.create(
                title=title,
                content=content,
                author=user,
                target_role=target_role
            )
            return redirect('notices')

    if user.role == 'student':
        notices = Notice.objects.filter(Q(target_role='all') | Q(target_role='student'))
    elif user.role == 'teacher':
        notices = Notice.objects.filter(Q(target_role='all') | Q(target_role='teacher'))
    elif is_institution_admin(user):
        notices = Notice.objects.filter(
            Q(target_class__institution=user.institution) |
            Q(target_class__isnull=True, author__institution=user.institution)
        ).distinct() if user.institution_id else Notice.objects.none()
    else:
        notices = Notice.objects.all()

    return render(request, 'dashboard/notices.html', {'notices': notices})

@login_required
def timetable_view(request):
    user = request.user
    
    if request.method == 'POST' and (user.role in ['teacher', 'admin'] or is_institution_admin(user)):
        class_id = request.POST.get('class_id')
        day_of_week = request.POST.get('day_of_week')
        start_time = request.POST.get('start_time')
        end_time = request.POST.get('end_time')
        room_number = request.POST.get('room_number')
        
        if class_id and day_of_week and start_time and end_time and room_number:
            course_class = CourseClass.objects.filter(id=class_id).first()
            if course_class and (
                user.role == 'admin' or
                (is_institution_admin(user) and course_class.institution_id == user.institution_id) or
                course_class.teacher == user
            ):
                ClassSchedule.objects.create(
                    course_class=course_class,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                    room_number=room_number
                )
        return redirect('timetable')

    today_day = date.today().weekday()
    day_map = {0: '1_monday', 1: '2_tuesday', 2: '3_wednesday', 3: '4_thursday', 4: '5_friday', 5: '6_saturday', 6: '1_monday'}
    current_day = day_map.get(today_day, '1_monday')

    if user.role == 'teacher':
        schedules = ClassSchedule.objects.filter(course_class__teacher=user)
        teacher_classes = CourseClass.objects.filter(teacher=user)
    elif user.role == 'student':
        schedules = ClassSchedule.objects.filter(course_class__in=user.enrolled_classes.all())
        teacher_classes = None
    elif is_institution_admin(user):
        schedules = ClassSchedule.objects.filter(course_class__institution=user.institution) if user.institution_id else ClassSchedule.objects.none()
        teacher_classes = scoped_classes(user)
    else:
        schedules = ClassSchedule.objects.all()
        teacher_classes = CourseClass.objects.all()

    days = ClassSchedule.DAY_CHOICES
    timetable_data = {day[0]: {'name': day[1], 'classes': []} for day in days}
    
    for schedule in schedules:
        timetable_data[schedule.day_of_week]['classes'].append(schedule)

    return render(request, 'dashboard/timetable.html', {
        'timetable': timetable_data,
        'current_day': current_day,
        'teacher_classes': teacher_classes,
        'days': days
    })

@login_required
def grades_view(request):
    user = request.user

    if user.role == 'admin':
        messages.info(request, 'Grades are entered by teachers and reviewed by students. Use Reports or Analytics for admin oversight.')
        return redirect('dashboard_home')
    
    if user.role == 'teacher':
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'create_exam':
                title = request.POST.get('title')
                class_id = request.POST.get('class_id')
                exam_date = request.POST.get('date')
                total_marks = request.POST.get('total_marks', 100)
                exam_type = request.POST.get('exam_type', 'other')
                
                if title and class_id and exam_date and CourseClass.objects.filter(id=class_id, teacher=user).exists():
                    Exam.objects.create(
                        title=title,
                        course_class_id=class_id,
                        date=exam_date,
                        total_marks=total_marks,
                        exam_type=exam_type
                    )
            elif action == 'add_grade':
                exam_id = request.POST.get('exam_id')
                student_id = request.POST.get('student_id')
                marks = request.POST.get('marks')
                remarks = request.POST.get('remarks', '')
                
                exam = Exam.objects.filter(id=exam_id, course_class__teacher=user).first()
                if exam and student_id and marks and exam.course_class.students.filter(id=student_id).exists():
                    Grade.objects.update_or_create(
                        exam=exam,
                        student_id=student_id,
                        defaults={'marks_obtained': marks, 'remarks': remarks}
                    )
            return redirect('grades')
            
        exams = Exam.objects.filter(course_class__teacher=user).prefetch_related('grades', 'course_class__students')
        teacher_classes = CourseClass.objects.filter(teacher=user).prefetch_related('students')
        
        # Inject ungraded students to avoid missing template filters crash
        for exam in exams:
            graded_ids = set(g.student_id for g in exam.grades.all())
            exam.ungraded_students = [s for s in exam.course_class.students.all() if s.id not in graded_ids]
            
        return render(request, 'dashboard/grades.html', {'exams': exams, 'teacher_classes': teacher_classes})

    elif user.role == 'student':
        grades = Grade.objects.filter(student=user).select_related('exam__course_class').order_by('-exam__date')
        return render(request, 'dashboard/grades.html', {'grades': grades})
    
    return redirect('dashboard_home')

@login_required
def export_reports_csv(request):
    if request.user.role not in ['admin', 'institution_admin', 'teacher']:
        return redirect('dashboard_home')
        
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="edumatrix_attendance_report_{date.today()}.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['Student', 'Role', 'Date', 'Class', 'Subject', 'Status']) # Headers
    
    if request.user.role == 'admin':
        records = AttendanceRecord.objects.select_related('student', 'course_class').all().order_by('-date')
    elif is_institution_admin(request.user):
        records = AttendanceRecord.objects.select_related('student', 'course_class').filter(
            Q(course_class__institution=request.user.institution) |
            Q(student__institution=request.user.institution)
        ).distinct().order_by('-date')
    else:
        # Teacher: only their classes
        records = AttendanceRecord.objects.filter(course_class__teacher=request.user).select_related('student', 'course_class').order_by('-date')
        
    for record in records:
        writer.writerow([
            record.student.get_full_name() or record.student.username,
            record.student.role,
            record.date.strftime('%Y-%m-%d'),
            record.course_class.name,
            record.course_class.subject,
            record.status.upper()
        ])
        
    return response

@login_required
def profile_settings_view(request):
    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action', 'update_profile')
        
        if action == 'change_password':
            current_password = request.POST.get('current_password') or ''
            new_password = request.POST.get('new_password') or ''
            confirm_password = request.POST.get('confirm_password') or ''
            allowed, _ = consume_auth_attempt('password_change', request, str(user.pk))

            if not allowed:
                messages.error(request, 'Too many password change attempts. Wait a few minutes and try again.')
                return redirect('profile_settings')
            
            if not user.check_password(current_password):
                messages.error(request, 'Current password is incorrect.')
            elif new_password != confirm_password:
                messages.error(request, 'New passwords do not match.')
            else:
                try:
                    validate_password(new_password, user=user)
                except ValidationError as exc:
                    messages.error(request, ' '.join(exc.messages[:3]))
                else:
                    user.set_password(new_password)
                    user.save()
                    update_session_auth_hash(request, user)
                    reset_auth_attempts('password_change', request, str(user.pk))
                    _record_activity(user, 'other', 'Password updated from profile settings.')
                    messages.success(request, 'Password changed successfully.')
            return redirect('profile_settings')

        username = (request.POST.get('username', user.username) or '').strip()
        email = (request.POST.get('email', user.email) or '').strip().lower()
        username_errors = _validate_username_candidate(username, exclude_user=user)
        if username_errors:
            messages.error(request, username_errors[0])
            return redirect('profile_settings')
        if email and User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
            messages.error(request, 'That email address is already being used by another account.')
            return redirect('profile_settings')
        if user.role != 'admin':
            institution = Institution.provision_for_email(email)
            if institution is None:
                messages.error(request, 'Use your institutional email address ending in .edu, .edu.in, .ac.in, or .ac.')
                return redirect('profile_settings')
            user.institution = institution

        user.username = username
        user.first_name = (request.POST.get('first_name', user.first_name) or '').strip()
        user.last_name = (request.POST.get('last_name', user.last_name) or '').strip()
        user.email = email
        user.phone_number = (request.POST.get('phone_number', user.phone_number) or '').strip()
        
        # Profile Picture
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
            
        user.save()
        _record_activity(user, 'other', 'Profile settings updated.')
        messages.success(request, 'Profile updated successfully.')
        return redirect('profile_settings')

    last_password_change = (
        ActivityLog.objects.filter(user=user, description__icontains='Password updated')
        .order_by('-created_at')
        .first()
    )
    recent_security_events = ActivityLog.objects.filter(user=user).order_by('-created_at')[:6]
    security_cards = [
        {
            'label': 'Email verification',
            'value': 'Verified' if user.email_verified_at else 'Pending',
            'tone': 'success' if user.email_verified_at else 'warning',
            'detail_label': 'Primary email',
            'detail': user.email or 'No email on file',
            'meta': user.email_verified_at.strftime('%d %b %Y, %I:%M %p') if user.email_verified_at else 'Waiting for email confirmation.',
        },
        {
            'label': 'Account status',
            'value': 'Active' if user.email_verified_at else 'Pending',
            'tone': 'success' if user.email_verified_at else 'warning',
            'detail_label': 'Verification source',
            'detail': 'This EduMatrix account has completed email verification.' if user.email_verified_at else 'Complete the verification email to activate this account.',
            'meta': 'Verified through EduMatrix email delivery.' if user.email_verified_at else 'Activation completes after email confirmation.',
        },
        {
            'label': 'Last login',
            'value': user.last_login.strftime('%d %b %Y') if user.last_login else 'Not yet',
            'tone': 'neutral',
            'detail_label': 'Login time',
            'detail': user.last_login.strftime('%I:%M %p') if user.last_login else 'No completed sign-in recorded yet.',
            'meta': 'Most recent authenticated access for this account.',
        },
        {
            'label': 'Institution',
            'value': user.institution.name if user.institution_id else 'Unassigned',
            'tone': 'success' if user.institution_id else 'warning',
            'detail_label': 'Domain verification',
            'detail': user.institution.domain if user.institution_id else 'Link an academic email domain to unlock institution-aware access.',
            'meta': 'EduMatrix uses your institution record to scope dashboards, users, departments, and classrooms.',
        },
        {
            'label': 'Password update',
            'value': last_password_change.created_at.strftime('%d %b %Y') if last_password_change else 'No change',
            'tone': 'neutral',
            'detail_label': 'Change time',
            'detail': last_password_change.created_at.strftime('%I:%M %p') if last_password_change else 'Use the secure form below to rotate your password.',
            'meta': 'Updated through the EduMatrix security form.' if last_password_change else 'Password rotation has not been recorded yet.',
        },
    ]

    return render(request, 'dashboard/profile_settings.html', {
        'security_cards': security_cards,
        'recent_security_events': recent_security_events,
    })


@login_required
def username_availability_view(request):
    username = (request.GET.get('username') or '').strip()
    if not username:
        return JsonResponse({
            'available': False,
            'is_current': False,
            'message': 'Enter a username to check availability.',
        })

    if username.lower() == request.user.username.lower():
        return JsonResponse({
            'available': True,
            'is_current': True,
            'message': 'This is your current username.',
        })

    errors = _validate_username_candidate(username, exclude_user=request.user)
    return JsonResponse({
        'available': not errors,
        'is_current': False,
        'message': 'Username is available.' if not errors else errors[0],
    })

@login_required
def public_profile_view(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    return render(request, 'dashboard/public_profile.html', {'target_user': target_user})

@login_required
def classroom_detail_view(request, class_id):
    classroom = get_object_or_404(
        _visible_classes_for_user(request.user).select_related('teacher'),
        id=class_id,
    )

    is_teacher_owner = request.user.role == 'teacher' and classroom.teacher_id == request.user.id
    is_student_member = request.user.role == 'student' and classroom.students.filter(id=request.user.id).exists()
    can_create_classwork = is_teacher_owner
    can_moderate_classroom = is_teacher_owner or is_platform_admin(request.user) or is_institution_admin(request.user)
    can_manage_classroom = can_create_classwork

    if request.user.role == 'teacher' and not is_teacher_owner:
        messages.error(request, 'You can only manage classrooms assigned to you.')
        return redirect('classes')

    if request.user.role == 'student' and not is_student_member:
        return redirect('dashboard_home')

    if request.method == 'POST':
        action = request.POST.get('action')
        create_actions = {'post_notice', 'upload_material', 'create_assignment', 'create_homework', 'create_recording'}
        moderate_actions = {'delete_assignment', 'delete_homework', 'delete_recording', 'delete_material', 'delete_notice'}
        if action in create_actions and not can_create_classwork:
            messages.error(request, 'Only the class teacher can publish new classroom work.')
            return redirect('classroom_detail', class_id=classroom.id)
        if action in moderate_actions and not can_moderate_classroom:
            messages.error(request, 'You do not have permission to change this classroom item.')
            return redirect('classroom_detail', class_id=classroom.id)

        if action == 'post_notice':
            title = request.POST.get('title')
            content = request.POST.get('content')
            if title and content:
                Notice.objects.create(
                    title=title,
                    content=content,
                    author=request.user,
                    target_role='student',
                    target_class=classroom
                )
                messages.success(request, 'Class notice posted.')
        elif action == 'delete_notice':
            Notice.objects.filter(
                id=request.POST.get('notice_id'),
                target_class=classroom,
            ).delete()
            messages.info(request, 'Class notice removed.')
        elif action == 'upload_material':
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            url = request.POST.get('url', '')
            file = request.FILES.get('file')
            if title and (url or file):
                StudyMaterial.objects.create(
                    title=title,
                    description=description,
                    course_class=classroom,
                    file=file,
                    url=url
                )
                messages.success(request, 'Study material uploaded.')
            else:
                messages.error(request, 'Add a title and either a file or link for the material.')
        elif action == 'delete_material':
            material = StudyMaterial.objects.filter(
                id=request.POST.get('material_id'),
                course_class=classroom,
            ).first()
            if material:
                if material.file:
                    material.file.delete(save=False)
                material.delete()
                messages.info(request, 'Study material deleted.')
        elif action == 'create_assignment':
            title = request.POST.get('title')
            due_date = request.POST.get('due_date')
            if title and due_date:
                Assignment.objects.create(
                    title=title,
                    description=request.POST.get('description', ''),
                    course_class=classroom,
                    created_by=request.user,
                    due_date=due_date,
                    total_marks=request.POST.get('total_marks', 100) or 100,
                    allow_late=request.POST.get('allow_late') == 'on',
                )
                messages.success(request, 'Assignment added to the classroom.')
        elif action == 'delete_assignment':
            Assignment.objects.filter(
                id=request.POST.get('assignment_id'),
                course_class=classroom,
            ).delete()
            messages.info(request, 'Assignment removed from the classroom.')
        elif action == 'create_homework':
            description = request.POST.get('description')
            due_date = request.POST.get('due_date')
            if description and due_date:
                HomeworkEntry.objects.create(
                    course_class=classroom,
                    teacher=request.user,
                    description=description,
                    due_date=due_date,
                    is_important=request.POST.get('is_important') == 'on',
                )
                messages.success(request, 'Homework added to the classroom.')
        elif action == 'delete_homework':
            HomeworkEntry.objects.filter(
                id=request.POST.get('homework_id'),
                course_class=classroom,
            ).delete()
            messages.info(request, 'Homework removed from the classroom.')
        elif action == 'create_recording':
            title = request.POST.get('title')
            video_url = request.POST.get('video_url')
            recording_date = request.POST.get('recording_date')
            if title and video_url and recording_date:
                ClassRecording.objects.create(
                    course_class=classroom,
                    title=title,
                    video_url=video_url,
                    description=request.POST.get('description', ''),
                    recording_date=recording_date,
                    duration_minutes=request.POST.get('duration_minutes') or 0,
                    uploaded_by=request.user,
                )
                messages.success(request, 'Recording added to the classroom.')
        elif action == 'delete_recording':
            ClassRecording.objects.filter(
                id=request.POST.get('recording_id'),
                course_class=classroom,
            ).delete()
            messages.info(request, 'Recording removed from the classroom.')
        return redirect('classroom_detail', class_id=classroom.id)

    global_notice_q = Q(target_role='all', target_class__isnull=True)
    if classroom.institution_id:
        global_notice_q &= Q(author__institution=classroom.institution)
    else:
        global_notice_q &= Q(author__institution__isnull=True)
    class_notices = Notice.objects.filter(
        Q(target_class=classroom) | global_notice_q
    ).select_related('author').only(
        'id', 'title', 'content', 'priority', 'created_at', 'author__id',
        'author__username', 'author__first_name', 'author__last_name',
    ).order_by('-created_at')[:6]
    materials_qs = StudyMaterial.objects.filter(course_class=classroom).order_by('-upload_date')
    assignments_qs = Assignment.objects.filter(course_class=classroom).select_related('created_by').annotate(
        submission_count=Count('submissions')
    ).order_by('due_date')
    homework_entries = HomeworkEntry.objects.filter(course_class=classroom).select_related('teacher').order_by('due_date')
    recordings = ClassRecording.objects.filter(course_class=classroom).select_related('uploaded_by').order_by('-recording_date')
    schedules = ClassSchedule.objects.filter(course_class=classroom)
    student_roster = classroom.students.order_by('first_name', 'last_name', 'username')
    assignments_page = list(assignments_qs[:6])

    student_stats = None
    grades = None
    if request.user.role == 'student':
        records = AttendanceRecord.objects.filter(course_class=classroom, student=request.user)
        stats = records.aggregate(
            total=Count('id'),
            present=Count('id', filter=Q(status='present')),
            absent=Count('id', filter=Q(status='absent')),
            late=Count('id', filter=Q(status='late')),
        )
        total = stats['total'] or 0
        present = stats['present'] or 0
        absent = stats['absent'] or 0
        late = stats['late'] or 0
        pct = round((present / total * 100)) if total > 0 else 0
        student_stats = {'total': total, 'present': present, 'absent': absent, 'late': late, 'pct': pct}
        grades = Grade.objects.filter(exam__course_class=classroom, student=request.user).select_related('exam').order_by('-exam__date')
        my_submissions = {
            submission.assignment_id: submission
            for submission in Submission.objects.filter(
                assignment_id__in=[assignment.id for assignment in assignments_page],
                student=request.user,
            ).only('id', 'assignment_id', 'graded', 'marks_obtained', 'feedback', 'submitted_at')
        }
        for assignment in assignments_page:
            assignment.my_submission = my_submissions.get(assignment.id)

    now = timezone.now()
    upcoming_homework = homework_entries.filter(due_date__gte=date.today()).count()
    active_assignments = assignments_qs.filter(due_date__gte=now).count()
    recording_total = recordings.count()
    materials_total = materials_qs.count()
    student_total = student_roster.count()
    assignment_total = assignments_qs.count()
    submitted_total = Submission.objects.filter(assignment__course_class=classroom).count()
    total_possible_submissions = assignment_total * student_total
    submission_rate = round((submitted_total / total_possible_submissions) * 100) if total_possible_submissions else 0
    next_schedule = schedules.first()
    ai_quiz_link = f"{reverse('ai_quiz')}?topic={classroom.subject}"

    context = {
        'classroom': classroom,
        'can_manage_classroom': can_manage_classroom,
        'can_create_classwork': can_create_classwork,
        'can_moderate_classroom': can_moderate_classroom,
        'student_stats': student_stats,
        'grades': grades,
        'class_notices': class_notices,
        'materials': materials_qs[:8],
        'assignments': assignments_page,
        'homework_entries': homework_entries[:6],
        'recordings': recordings[:6],
        'active_assignments': active_assignments,
        'upcoming_homework': upcoming_homework,
        'recording_total': recording_total,
        'materials_total': materials_total,
        'student_total': student_total,
        'assignment_total': assignment_total,
        'submitted_total': submitted_total,
        'submission_rate': submission_rate,
        'ai_quiz_link': ai_quiz_link,
        'schedules': schedules,
        'next_schedule': next_schedule,
        'student_roster': student_roster[:12],
    }
    return render(request, 'dashboard/classroom.html', context)


# ============================
# ASSIGNMENTS VIEWS
# ============================

@login_required
def assignments_view(request):
    user = request.user

    if user.role == 'admin':
        messages.info(request, 'Assignments are created by teachers and completed by students.')
        return redirect('dashboard_home')
    
    if user.role == 'teacher':
        if request.method == 'POST':
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            class_id = request.POST.get('class_id')
            due_date = request.POST.get('due_date')
            total_marks = request.POST.get('total_marks', 100)
            allow_late = request.POST.get('allow_late') == 'on'
            
            if title and class_id and due_date and CourseClass.objects.filter(id=class_id, teacher=user).exists():
                Assignment.objects.create(
                    title=title,
                    description=description,
                    course_class_id=class_id,
                    created_by=user,
                    due_date=due_date,
                    total_marks=total_marks,
                    allow_late=allow_late
                )
            return redirect('assignments')
        
        teacher_classes = CourseClass.objects.filter(teacher=user)
        assignments = Assignment.objects.filter(course_class__in=teacher_classes)
    elif user.role == 'student':
        enrolled = user.enrolled_classes.all()
        assignments = Assignment.objects.filter(course_class__in=enrolled)
    else:
        assignments = Assignment.objects.all()
    
    # Annotate submission info for students
    if user.role == 'student':
        for a in assignments:
            a.my_submission = a.submissions.filter(student=user).first()
    
    teacher_classes = CourseClass.objects.filter(teacher=user) if user.role == 'teacher' else None
    
    return render(request, 'dashboard/assignments.html', {
        'assignments': assignments,
        'teacher_classes': teacher_classes,
    })


@login_required
def assignment_detail_view(request, assignment_id):
    assignment = get_object_or_404(Assignment, id=assignment_id)
    user = request.user

    if user.role == 'admin':
        messages.info(request, 'Assignment workflows belong to teachers and students.')
        return redirect('dashboard_home')
    if user.role == 'teacher' and assignment.course_class.teacher_id != user.id:
        messages.error(request, 'You can only manage assignments for your own classes.')
        return redirect('assignments')
    if user.role == 'student' and not assignment.course_class.students.filter(id=user.id).exists():
        messages.error(request, 'You are not enrolled in this assignment class.')
        return redirect('assignments')
    
    if user.role == 'student':
        # Submit assignment
        if request.method == 'POST':
            text_content = request.POST.get('text_content', '')
            file = request.FILES.get('file')
            now = timezone.now()
            is_late = now > assignment.due_date
            if is_late and not assignment.allow_late:
                messages.error(request, 'This assignment is closed for late submissions.')
                return redirect('assignment_detail', assignment_id=assignment.id)
            
            Submission.objects.update_or_create(
                assignment=assignment,
                student=user,
                defaults={
                    'text_content': text_content,
                    'file': file if file else None,
                    'is_late': is_late,
                }
            )
            return redirect('assignment_detail', assignment_id=assignment.id)
        
        my_submission = assignment.submissions.filter(student=user).first()
        return render(request, 'dashboard/assignment_detail.html', {
            'assignment': assignment,
            'my_submission': my_submission,
        })
    
    elif user.role == 'teacher':
        # Grade submissions
        if request.method == 'POST':
            submission_id = request.POST.get('submission_id')
            marks = request.POST.get('marks')
            feedback = request.POST.get('feedback', '')
            
            if submission_id and marks:
                sub = get_object_or_404(Submission, id=submission_id, assignment=assignment)
                sub.marks_obtained = marks
                sub.feedback = feedback
                sub.graded = True
                sub.save()
            return redirect('assignment_detail', assignment_id=assignment.id)
        
        submissions = assignment.submissions.select_related('student').all()
        all_students = assignment.course_class.students.all()
        submitted_ids = set(s.student_id for s in submissions)
        not_submitted = [s for s in all_students if s.id not in submitted_ids]
        
        return render(request, 'dashboard/assignment_detail.html', {
            'assignment': assignment,
            'submissions': submissions,
            'not_submitted': not_submitted,
        })
    
    else:
        # Admin view
        submissions = assignment.submissions.select_related('student').all()
        return render(request, 'dashboard/assignment_detail.html', {
            'assignment': assignment,
            'submissions': submissions,
        })


# ============================
# FORUM VIEWS
# ============================

@login_required
def forum_view(request):
    user = request.user
    visible_classes = _visible_classes_for_user(user)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        content = request.POST.get('content')
        class_id = request.POST.get('class_id')
        
        if title and content:
            if class_id and not visible_classes.filter(id=class_id).exists() and not is_platform_admin(user):
                messages.error(request, 'Choose a classroom that belongs to your workspace.')
                return redirect('forum')
            ForumThread.objects.create(
                title=title,
                content=content,
                author=user,
                course_class_id=class_id if class_id else None
            )
        return redirect('forum')
    
    class_filter = request.GET.get('class_id')
    threads = _visible_forum_threads(user)
    
    if class_filter:
        threads = threads.filter(course_class_id=class_filter)

    return render(request, 'dashboard/forum.html', {
        'threads': threads,
        'user_classes': visible_classes,
        'selected_class': class_filter,
    })


@login_required
def forum_thread_view(request, thread_id):
    thread = get_object_or_404(_visible_forum_threads(request.user), id=thread_id)
    
    if request.method == 'POST' and not thread.is_locked:
        content = request.POST.get('content')
        if content:
            ForumReply.objects.create(
                thread=thread,
                author=request.user,
                content=content
            )
        return redirect('forum_thread', thread_id=thread.id)
    
    replies = thread.replies.select_related('author').all()
    
    return render(request, 'dashboard/forum_thread.html', {
        'thread': thread,
        'replies': replies,
    })


# ============================
# MESSAGING VIEWS
# ============================

@login_required
def inbox_view(request):
    messages_list = Message.objects.filter(receiver=request.user, parent__isnull=True).select_related('sender')
    unread_count = messages_list.filter(is_read=False).count()
    
    return render(request, 'dashboard/inbox.html', {
        'messages_list': messages_list,
        'unread_count': unread_count,
        'view_type': 'inbox',
    })


@login_required
def sent_messages_view(request):
    messages_list = Message.objects.filter(sender=request.user, parent__isnull=True).select_related('receiver')
    
    return render(request, 'dashboard/inbox.html', {
        'messages_list': messages_list,
        'view_type': 'sent',
    })


@login_required
def compose_message_view(request):
    recipients = User.objects.exclude(id=request.user.id)
    if is_institution_admin(request.user) and not request.user.institution_id:
        recipients = recipients.none()
    elif not is_platform_admin(request.user) and request.user.institution_id:
        recipients = recipients.filter(institution=request.user.institution)

    if request.method == 'POST':
        receiver_id = request.POST.get('receiver_id')
        subject = request.POST.get('subject')
        body = request.POST.get('body')
        
        if receiver_id and subject and body:
            receiver = recipients.filter(id=receiver_id).first()
            if receiver is None:
                messages.error(request, 'Choose a recipient from your institution workspace.')
                return redirect('compose_message')
            Message.objects.create(
                sender=request.user,
                receiver=receiver,
                subject=subject,
                body=body
            )
            return redirect('inbox')
    
    users = recipients.order_by('role', 'username')
    reply_to = request.GET.get('reply_to')
    prefill = {}
    if reply_to:
        original = Message.objects.filter(id=reply_to).first()
        if original:
            prefill = {
                'receiver_id': original.sender_id,
                'subject': f"Re: {original.subject}",
                'parent_id': original.id,
            }
    
    return render(request, 'dashboard/compose_message.html', {
        'users': users,
        'prefill': prefill,
    })


@login_required
def message_detail_view(request, message_id):
    message = get_object_or_404(Message, id=message_id)
    
    # Mark as read
    if message.receiver == request.user and not message.is_read:
        message.is_read = True
        message.save()
    
    # Get thread replies
    replies = Message.objects.filter(parent=message).select_related('sender', 'receiver')
    
    # Handle reply
    if request.method == 'POST':
        body = request.POST.get('body')
        if body:
            receiver = message.sender if request.user == message.receiver else message.receiver
            Message.objects.create(
                sender=request.user,
                receiver=receiver,
                subject=f"Re: {message.subject}",
                body=body,
                parent=message
            )
        return redirect('message_detail', message_id=message.id)
    
    return render(request, 'dashboard/message_detail.html', {
        'message': message,
        'replies': replies,
    })


# ============================
# CALENDAR & EVENTS
# ============================

@login_required
def calendar_view(request):
    user = request.user
    today = date.today()
    visible_classes = _visible_classes_for_user(user)
    
    # Get month/year from query params or default to current
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    # Upcoming events for RSVP list
    upcoming_events = Event.objects.filter(event_date__gte=today)
    upcoming_query = _institution_filter_q(user, 'course_class__institution', 'created_by__institution')
    if upcoming_query is not None:
        upcoming_events = upcoming_events.filter(upcoming_query).distinct()
    upcoming_events = upcoming_events.order_by('event_date')[:10]
    for event in upcoming_events:
        event.is_attending = event.attendees.filter(id=user.id).exists()
    
    # Handle event creation
    if request.method == 'POST' and user.role in ('admin', 'teacher', 'institution_admin'):
        title = request.POST.get('title')
        event_date = request.POST.get('event_date')
        event_type = request.POST.get('event_type', 'custom')
        description = request.POST.get('description', '')
        class_id = request.POST.get('class_id')
        
        if title and event_date:
            if class_id and not visible_classes.filter(id=class_id).exists() and not is_platform_admin(user):
                messages.error(request, 'Choose a classroom from your institution workspace.')
                return redirect(f"{reverse('calendar')}?year={year}&month={month}")
            Event.objects.create(
                title=title,
                event_date=event_date,
                event_type=event_type,
                description=description,
                created_by=user,
                course_class_id=class_id if class_id else None
            )
        return redirect(f"{reverse('calendar')}?year={year}&month={month}")
    
    # Build calendar data
    month_cal = cal_module.monthcalendar(year, month)
    month_name = cal_module.month_name[month]
    
    # Get events for this month
    events = Event.objects.filter(event_date__year=year, event_date__month=month)
    event_query = _institution_filter_q(user, 'course_class__institution', 'created_by__institution')
    if event_query is not None:
        events = events.filter(event_query).distinct()
    
    # Get exams for this month
    if user.role == 'teacher':
        exams = Exam.objects.filter(course_class__teacher=user, date__year=year, date__month=month)
        if user.institution_id:
            exams = exams.filter(course_class__institution=user.institution)
        user_classes = visible_classes
    elif user.role == 'student':
        exams = Exam.objects.filter(course_class__in=visible_classes, date__year=year, date__month=month)
        user_classes = None
    elif is_institution_admin(user):
        exams = Exam.objects.filter(course_class__institution=user.institution, date__year=year, date__month=month) if user.institution_id else Exam.objects.none()
        user_classes = visible_classes
    else:
        exams = Exam.objects.filter(date__year=year, date__month=month)
        user_classes = CourseClass.objects.all()
    
    # Get assignments due this month
    if user.role == 'teacher':
        assignments_due = Assignment.objects.filter(course_class__teacher=user, due_date__year=year, due_date__month=month)
        if user.institution_id:
            assignments_due = assignments_due.filter(course_class__institution=user.institution)
    elif user.role == 'student':
        assignments_due = Assignment.objects.filter(course_class__in=visible_classes, due_date__year=year, due_date__month=month)
    elif is_institution_admin(user):
        assignments_due = Assignment.objects.filter(course_class__institution=user.institution, due_date__year=year, due_date__month=month) if user.institution_id else Assignment.objects.none()
    else:
        assignments_due = Assignment.objects.filter(due_date__year=year, due_date__month=month)
    
    # Build events by day
    day_events = {}
    for event in events:
        day = event.event_date.day
        day_events.setdefault(day, []).append({
            'title': event.title,
            'type': event.event_type,
            'color': {'exam': 'rose', 'assignment': 'amber', 'holiday': 'emerald', 'meeting': 'indigo', 'custom': 'cyan'}.get(event.event_type, 'indigo')
        })
    for exam in exams:
        day = exam.date.day
        day_events.setdefault(day, []).append({
            'title': exam.title,
            'type': 'exam',
            'color': 'rose'
        })
    for a in assignments_due:
        day = a.due_date.day
        day_events.setdefault(day, []).append({
            'title': f"Due: {a.title}",
            'type': 'assignment',
            'color': 'amber'
        })
    
    # Navigation
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    context = {
        'month_cal': month_cal,
        'month_name': month_name,
        'year': year,
        'month': month,
        'today': today,
        'day_events': day_events,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'user_classes': user_classes,
        'upcoming_events': upcoming_events,
    }
    return render(request, 'dashboard/calendar.html', context)


@login_required
def toggle_rsvp(request, event_id):
    event_qs = Event.objects.all()
    event_query = _institution_filter_q(request.user, 'course_class__institution', 'created_by__institution')
    if event_query is not None:
        event_qs = event_qs.filter(event_query).distinct()
    event = get_object_or_404(event_qs, id=event_id)
    if event.attendees.filter(id=request.user.id).exists():
        event.attendees.remove(request.user)
        action = 'removed'
    else:
        event.attendees.add(request.user)
        action = 'added'
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'action': action, 'count': event.attendees.count()})
    
    return redirect('calendar')



# ============================
# ANALYTICS
# ============================

@login_required
def analytics_view(request):
    user = request.user
    today = date.today()
    
    if user.role == 'student':
        enrolled = user.enrolled_classes.all()
        
        # Subject-wise marks data
        subjects = []
        marks_data = []
        for cls in enrolled:
            grades = Grade.objects.filter(student=user, exam__course_class=cls)
            avg_marks = 0
            if grades.exists():
                total_pct = sum(float(g.marks_obtained) / float(g.exam.total_marks) * 100 for g in grades)
                avg_marks = round(total_pct / grades.count())
            subjects.append(cls.subject)
            marks_data.append(avg_marks)
        
        # Attendance trend (last 30 days)
        att_labels = []
        att_data = []
        for i in range(30):
            d = today - timedelta(days=29 - i)
            records = AttendanceRecord.objects.filter(student=user, date=d)
            total = records.count()
            present = records.filter(status='present').count()
            att_labels.append(d.strftime('%d'))
            att_data.append(1 if present > 0 else (0 if total > 0 else -1))
        
        # Overall grade distribution
        all_grades = Grade.objects.filter(student=user)
        grade_dist = {'A+': 0, 'A': 0, 'B+': 0, 'B': 0, 'C': 0, 'F': 0}
        for g in all_grades:
            pct = float(g.marks_obtained) / float(g.exam.total_marks) * 100
            if pct >= 90: grade_dist['A+'] += 1
            elif pct >= 80: grade_dist['A'] += 1
            elif pct >= 70: grade_dist['B+'] += 1
            elif pct >= 60: grade_dist['B'] += 1
            elif pct >= 50: grade_dist['C'] += 1
            else: grade_dist['F'] += 1
        
        context = {
            'subjects_json': json.dumps(subjects),
            'marks_json': json.dumps(marks_data),
            'att_labels_json': json.dumps(att_labels),
            'att_data_json': json.dumps(att_data),
            'grade_dist_json': json.dumps(list(grade_dist.values())),
            'grade_labels_json': json.dumps(list(grade_dist.keys())),
        }
    
    elif user.role == 'teacher':
        teacher_classes = CourseClass.objects.filter(teacher=user)
        if user.institution_id:
            teacher_classes = teacher_classes.filter(institution=user.institution)
        
        # Class-wise average attendance
        class_names = []
        class_att = []
        for cls in teacher_classes:
            records = AttendanceRecord.objects.filter(course_class=cls)
            total = records.count()
            present = records.filter(status='present').count()
            pct = round((present / total * 100) if total > 0 else 0)
            class_names.append(cls.subject)
            class_att.append(pct)
        
        # Class-wise average grades
        class_grades = []
        for cls in teacher_classes:
            grades = Grade.objects.filter(exam__course_class=cls)
            if grades.exists():
                avg = round(sum(float(g.marks_obtained) / float(g.exam.total_marks) * 100 for g in grades) / grades.count())
            else:
                avg = 0
            class_grades.append(avg)
        
        context = {
            'class_names_json': json.dumps(class_names),
            'class_att_json': json.dumps(class_att),
            'class_grades_json': json.dumps(class_grades),
        }
    
    else:
        class_qs = scoped_classes(user) if is_institution_admin(user) else CourseClass.objects.all()
        student_qs = scoped_users(user).filter(role='student') if is_institution_admin(user) else User.objects.filter(role='student')
        departments = list(class_qs.values_list('department', flat=True).distinct())
        dept_att = []
        dept_grades = []
        for dept in departments:
            records = AttendanceRecord.objects.filter(course_class__department=dept)
            if is_institution_admin(user) and user.institution_id:
                records = records.filter(course_class__institution=user.institution)
            total = records.count()
            present = records.filter(status='present').count()
            dept_att.append(round((present / total * 100) if total > 0 else 0))
            
            grades = Grade.objects.filter(exam__course_class__department=dept)
            if is_institution_admin(user) and user.institution_id:
                grades = grades.filter(exam__course_class__institution=user.institution)
            if grades.exists():
                avg = round(sum(float(g.marks_obtained) / float(g.exam.total_marks) * 100 for g in grades) / grades.count())
            else:
                avg = 0
            dept_grades.append(avg)

        # Enrollment trend (monthly for current year)
        enrollment_labels = []
        enrollment_data = []
        for m in range(1, 13):
            enrollment_labels.append(cal_module.month_abbr[m])
            enrollment_data.append(student_qs.filter(date_joined__year=today.year, date_joined__month=m).count())
        
        context = {
            'departments_json': json.dumps(departments),
            'dept_att_json': json.dumps(dept_att),
            'dept_grades_json': json.dumps(dept_grades),
            'enrollment_labels_json': json.dumps(enrollment_labels),
            'enrollment_data_json': json.dumps(enrollment_data),
        }
    
    return render(request, 'dashboard/analytics.html', context)


# ============================
# FEE MANAGEMENT
# ============================

@login_required
def fees_view(request):
    user = request.user
    
    if user.role == 'admin':
        if request.method == 'POST':
            action = request.POST.get('action')
            if action == 'create':
                student_id = request.POST.get('student_id')
                title = request.POST.get('title')
                amount = request.POST.get('amount')
                due_date = request.POST.get('due_date')
                
                if student_id and title and amount and due_date:
                    import random, string
                    receipt = 'RCP-' + ''.join(random.choices(string.digits, k=8))
                    FeeRecord.objects.create(
                        student_id=student_id,
                        title=title,
                        amount=amount,
                        due_date=due_date,
                        receipt_no=receipt
                    )
            elif action == 'mark_paid':
                fee_id = request.POST.get('fee_id')
                payment_method = request.POST.get('payment_method', 'other')
                fee = FeeRecord.objects.filter(id=fee_id).first()
                if fee:
                    fee.status = 'paid'
                    fee.paid_date = date.today()
                    fee.payment_method = payment_method
                    fee.save()
            return redirect('fees')
        
        fees = FeeRecord.objects.select_related('student').all()
        students = User.objects.filter(role='student')
        
        total_amount = sum(f.amount for f in fees)
        paid_amount = sum(f.amount for f in fees if f.status == 'paid')
        pending_amount = sum(f.amount for f in fees if f.status != 'paid')
        
        return render(request, 'dashboard/fees.html', {
            'fees': fees,
            'students': students,
            'total_amount': total_amount,
            'paid_amount': paid_amount,
            'pending_amount': pending_amount,
        })
    
    elif user.role == 'student':
        fees = FeeRecord.objects.filter(student=user)
        total_due = sum(f.amount for f in fees if f.status != 'paid')
        total_paid = sum(f.amount for f in fees if f.status == 'paid')
        
        return render(request, 'dashboard/fees.html', {
            'fees': fees,
            'total_due': total_due,
            'total_paid': total_paid,
        })
    
    return redirect('dashboard_home')


# ============================
# LIBRARY / RESOURCES
# ============================

@login_required
def library_view(request):
    return retired_feature_redirect(
        request,
        'Library',
        redirect_to='dashboard_home',
        extra_message='Classwork resources now live inside Classrooms.',
    )

    user = request.user
    
    if request.method == 'POST' and user.role in ('admin', 'teacher'):
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        category = request.POST.get('category', 'other')
        url = request.POST.get('url', '')
        file = request.FILES.get('file')
        class_id = request.POST.get('class_id')
        
        if title:
            LibraryResource.objects.create(
                title=title,
                description=description,
                category=category,
                url=url if url else None,
                file=file if file else None,
                uploaded_by=user,
                course_class_id=class_id if class_id else None,
                available_copies=request.POST.get('copies', 1)
            )
        return redirect('library')
    
    resources = LibraryResource.objects.select_related('uploaded_by', 'course_class').all()
    
    # Filters
    category_filter = request.GET.get('category')
    search = request.GET.get('search')
    if category_filter:
        resources = resources.filter(category=category_filter)
    if search:
        resources = resources.filter(Q(title__icontains=search) | Q(description__icontains=search))
    
    my_issues = BookIssue.objects.filter(student=user) if user.role == 'student' else None
    all_issues = BookIssue.objects.select_related('resource', 'student').all() if user.role in ('admin', 'teacher') else None
    
    if user.role == 'teacher':
        user_classes = CourseClass.objects.filter(teacher=user)
    elif user.role == 'admin':
        user_classes = CourseClass.objects.all()
    else:
        user_classes = None

    context = {
        'resources': resources,
        'my_issues': my_issues,
        'all_issues': all_issues,
        'categories': LibraryResource.CATEGORY_CHOICES,
        'user_classes': user_classes,
        'selected_category': category_filter,
        'search_query': search,
    }
    return render(request, 'dashboard/library.html', context)


@login_required
def request_book(request, resource_id):
    return retired_feature_redirect(
        request,
        'Library',
        redirect_to='dashboard_home',
        extra_message='Classwork resources now live inside Classrooms.',
    )

    resource = get_object_or_404(LibraryResource, id=resource_id)
    if resource.available_copies < 1:
        messages.error(request, "No copies available at the moment.")
        return redirect('library')
    
    # Check if student already has a pending or issued request for this
    existing = BookIssue.objects.filter(resource=resource, student=request.user, status__in=['pending', 'issued']).exists()
    if existing:
        messages.warning(request, "You already have a pending request or an issued copy of this book.")
        return redirect('library')
    
    # Create request
    BookIssue.objects.create(
        resource=resource,
        student=request.user,
        due_date=date.today() + timedelta(days=14) # Default 2 weeks
    )
    messages.success(request, f"Request for '{resource.title}' submitted.")
    return redirect('library')


@login_required
def manage_book_issue(request, issue_id):
    return retired_feature_redirect(
        request,
        'Library',
        redirect_to='dashboard_home',
        extra_message='Classwork resources now live inside Classrooms.',
    )

    if request.user.role not in ('admin', 'teacher'):
        return redirect('dashboard_home')
        
    issue = get_object_or_404(BookIssue, id=issue_id)
    action = request.POST.get('action')
    
    if action == 'issue':
        if issue.resource.available_copies > 0:
            issue.status = 'issued'
            issue.issue_date = date.today()
            issue.resource.available_copies -= 1
            issue.resource.save()
            issue.save()
            messages.success(request, f"Book issued to {issue.student.username}")
        else:
            messages.error(request, "Insufficient copies to issue.")
    elif action == 'return':
        issue.status = 'returned'
        issue.return_date = date.today()
        issue.resource.available_copies += 1
        issue.resource.save()
        issue.save()
        messages.success(request, "Book marked as returned.")
    elif action == 'cancel':
        issue.delete()
        messages.info(request, "Request cancelled.")
        
    return redirect('library')



# ============================
# ACHIEVEMENTS & GAMIFICATION
# ============================

@login_required
def achievements_view(request):
    user = request.user
    
    if user.role != 'student':
        return redirect('dashboard_home')
    
    # Get or create XP profile
    xp_profile, _ = StudentXP.objects.get_or_create(student=user)
    
    # Check and award badges
    _check_badges(user, xp_profile)
    
    # Get achievements
    achievements = Achievement.objects.filter(student=user)
    earned_types = set(a.badge_type for a in achievements)
    
    # Build badge gallery
    all_badges = []
    for badge_key, badge_label in BADGE_CHOICES:
        all_badges.append({
            'type': badge_key,
            'label': badge_label,
            'earned': badge_key in earned_types,
            'icon': badge_label.split(' ')[0],
            'name': ' '.join(badge_label.split(' ')[1:]),
        })
    
    # Leaderboard (top 10 students by XP)
    leaderboard = StudentXP.objects.select_related('student').order_by('-total_xp')[:10]
    
    # Level progress
    xp_for_next = (xp_profile.level) * 500
    xp_progress = min(100, round(xp_profile.total_xp / xp_for_next * 100)) if xp_for_next > 0 else 0
    
    return render(request, 'dashboard/achievements.html', {
        'xp_profile': xp_profile,
        'all_badges': all_badges,
        'leaderboard': leaderboard,
        'xp_for_next': xp_for_next,
        'xp_progress': xp_progress,
        'achievements_count': achievements.count(),
        'total_badges': len(BADGE_CHOICES),
    })


def _check_badges(user, xp_profile):
    """Auto-check and award badges based on user activity."""
    records = AttendanceRecord.objects.filter(student=user)
    
    # Perfect attendance badge
    total = records.count()
    present = records.filter(status='present').count()
    if total >= 20 and present == total:
        Achievement.objects.get_or_create(student=user, badge_type='perfect_attendance', defaults={'description': 'Never missed a class!'})
        xp_profile.total_xp = max(xp_profile.total_xp, present * 10)
    
    # Streak badges
    if xp_profile.current_streak >= 7:
        Achievement.objects.get_or_create(student=user, badge_type='streak_7', defaults={'description': '7-day attendance streak!'})
    if xp_profile.current_streak >= 30:
        Achievement.objects.get_or_create(student=user, badge_type='streak_30', defaults={'description': '30-day attendance streak!'})
    
    # Assignment ace
    graded_subs = Submission.objects.filter(student=user, graded=True)
    perfect_count = sum(1 for s in graded_subs if s.marks_obtained and float(s.marks_obtained) >= float(s.assignment.total_marks) * 0.9)
    if perfect_count >= 3:
        Achievement.objects.get_or_create(student=user, badge_type='assignment_ace', defaults={'description': 'Scored 90%+ on 3 assignments!'})
    
    # Top scorer
    top_grades = Grade.objects.filter(student=user)
    if top_grades.exists():
        avg_pct = sum(float(g.marks_obtained) / float(g.exam.total_marks) * 100 for g in top_grades) / top_grades.count()
        if avg_pct >= 85:
            Achievement.objects.get_or_create(student=user, badge_type='top_scorer', defaults={'description': 'Average score above 85%!'})
    
    # Bookworm - downloaded/viewed library resources (simplified: check if user has any submissions)
    if Submission.objects.filter(student=user).count() >= 5:
        Achievement.objects.get_or_create(student=user, badge_type='bookworm', defaults={'description': 'Submitted 5+ assignments!'})
    
    # Update XP based on activities
    xp_from_attendance = present * 10
    xp_from_submissions = Submission.objects.filter(student=user).count() * 25
    xp_from_grades = sum(float(g.marks_obtained) for g in Grade.objects.filter(student=user) if g.marks_obtained)
    
    new_xp = int(xp_from_attendance + xp_from_submissions + xp_from_grades)
    if new_xp > xp_profile.total_xp:
        xp_profile.total_xp = new_xp
        xp_profile.level = max(1, new_xp // 500 + 1)
        xp_profile.save()


# ============================
# POLLS / VOTING
# ============================

@login_required
def polls_view(request):
    user = request.user
    visible_classes = _visible_classes_for_user(user)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create' and user.role in ('admin', 'teacher'):
            question = request.POST.get('question')
            options = request.POST.getlist('option')
            class_id = request.POST.get('class_id')
            if question and len(options) >= 2:
                if class_id and not visible_classes.filter(id=class_id).exists() and not is_platform_admin(user):
                    messages.error(request, 'Choose a classroom from your institution workspace.')
                    return redirect('polls')
                poll = Poll.objects.create(
                    question=question,
                    created_by=user,
                    course_class_id=class_id if class_id else None
                )
                for opt_text in options:
                    if opt_text.strip():
                        PollOption.objects.create(poll=poll, text=opt_text.strip())
                ActivityLog.objects.create(user=user, action='other', description=f'Created poll: {question}')
        elif action == 'vote':
            option_id = request.POST.get('option_id')
            if option_id:
                option = PollOption.objects.filter(id=option_id).first()
                if option:
                    # Check if user already voted on this poll
                    already_voted = PollVote.objects.filter(
                        option__poll=option.poll, voter=user
                    ).exists()
                    if not already_voted:
                        PollVote.objects.create(option=option, voter=user)
        return redirect('polls')
    
    polls = Poll.objects.filter(is_active=True).prefetch_related('options__votes')
    if not is_platform_admin(user):
        if user.role in ('teacher', 'student'):
            poll_query = Q(course_class__in=visible_classes)
            if user.institution_id:
                poll_query |= Q(course_class__isnull=True, created_by__institution=user.institution)
            polls = polls.filter(poll_query).distinct()
        else:
            poll_query = _institution_filter_q(user, 'course_class__institution', 'created_by__institution')
            if poll_query is not None:
                polls = polls.filter(poll_query).distinct()
    
    # Annotate user's vote status
    for poll in polls:
        poll.user_voted = PollVote.objects.filter(option__poll=poll, voter=user).exists()
        poll.user_vote = PollVote.objects.filter(option__poll=poll, voter=user).first()
    
    if user.role == 'teacher':
        user_classes = visible_classes
    elif user.role == 'admin':
        user_classes = CourseClass.objects.all()
    elif is_institution_admin(user):
        user_classes = visible_classes
    else:
        user_classes = None
    
    return render(request, 'dashboard/polls.html', {
        'polls': polls,
        'user_classes': user_classes,
    })


# ============================
# TODO LIST
# ============================

@login_required
def todos_view(request):
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            title = request.POST.get('title')
            priority = request.POST.get('priority', 'medium')
            due_date = request.POST.get('due_date') or None
            if title:
                TodoItem.objects.create(user=user, title=title, priority=priority, due_date=due_date)
        elif action == 'toggle':
            todo_id = request.POST.get('todo_id')
            todo = TodoItem.objects.filter(id=todo_id, user=user).first()
            if todo:
                todo.is_done = not todo.is_done
                todo.save()
        elif action == 'delete':
            todo_id = request.POST.get('todo_id')
            TodoItem.objects.filter(id=todo_id, user=user).delete()
        return redirect('todos')
    
    todos = TodoItem.objects.filter(user=user)
    pending = todos.filter(is_done=False).count()
    completed = todos.filter(is_done=True).count()
    
    return render(request, 'dashboard/todos.html', {
        'todos': todos,
        'pending': pending,
        'completed': completed,
    })


# ============================
# ACTIVITY FEED
# ============================

@login_required
def activity_view(request):
    user = request.user
    
    if user.role == 'admin':
        activities = ActivityLog.objects.select_related('user').all()[:50]
    elif is_institution_admin(user) and user.institution_id:
        activities = ActivityLog.objects.select_related('user').filter(user__institution=user.institution)[:50]
    else:
        activities = ActivityLog.objects.filter(user=user)[:30]
    
    return render(request, 'dashboard/activity.html', {'activities': activities})


# ============================
# HELP & FAQ
# ============================

@login_required
def help_view(request):
    faqs = HelpFAQ.objects.all()
    # Group by category
    categories = {}
    for faq in faqs:
        categories.setdefault(faq.category, []).append(faq)
    
    return render(request, 'dashboard/help.html', {'categories': categories})


# ============================
# AI STUDY BUDDY (Gemini Chat)
# ============================

@login_required
def ai_chat_view(request):
    user = request.user
    sessions = ChatSession.objects.filter(user=user)[:20]
    
    session_id = request.GET.get('session')
    current_session = None
    chat_messages = []
    
    if session_id:
        current_session = ChatSession.objects.filter(id=session_id, user=user).first()
        if current_session:
            chat_messages = json.loads(current_session.messages_json)
    
    return render(request, 'dashboard/ai_chat.html', {
        'sessions': sessions,
        'current_session': current_session,
        'chat_messages': chat_messages,
    })


@login_required
@require_POST
def ai_chat_send(request):
    """AJAX endpoint for sending chat messages."""
    from dashboard.ai_services import gemini_chat
    
    user = request.user
    user_message = request.POST.get('message', '').strip()
    session_id = request.POST.get('session_id')
    
    if not user_message:
        return JsonResponse({'error': 'Empty message'}, status=400)
    
    # Get or create session
    if session_id:
        session = ChatSession.objects.filter(id=session_id, user=user).first()
    else:
        session = None
    
    if not session:
        title = user_message[:50] + ('...' if len(user_message) > 50 else '')
        session = ChatSession.objects.create(user=user, title=title)
    
    # Load existing messages
    messages_list = json.loads(session.messages_json)
    messages_list.append({'role': 'user', 'text': user_message})
    
    # Call Gemini
    result = gemini_chat(messages_list)
    
    if result['success']:
        ai_response = result['text']
        messages_list.append({'role': 'model', 'text': ai_response})
        session.messages_json = json.dumps(messages_list)
        session.save()
        return JsonResponse({
            'success': True,
            'response': ai_response,
            'session_id': session.id,
        })
    else:
        return JsonResponse({'success': False, 'error': result['error']})


@login_required
@require_POST
def ai_chat_new(request):
    """Create a new chat session."""
    session = ChatSession.objects.create(user=request.user)
    return JsonResponse({'success': True, 'session_id': session.id})


# ============================
# AI QUIZ GENERATOR (Gemini)
# ============================

@login_required
def ai_quiz_view(request):
    return render(request, 'dashboard/ai_quiz.html')


@login_required
@require_POST
def ai_quiz_generate(request):
    """AJAX endpoint to generate a quiz using Gemini."""
    from dashboard.ai_services import gemini_generate
    
    topic = request.POST.get('topic', '').strip()
    num_questions = min(int(request.POST.get('num_questions', 5)), 10)  # Max 10
    difficulty = request.POST.get('difficulty', 'medium')
    
    if not topic:
        return JsonResponse({'error': 'Topic is required'}, status=400)
    
    prompt = f"""Generate exactly {num_questions} multiple-choice quiz questions about "{topic}" at {difficulty} difficulty level.

Return ONLY a valid JSON array. Each question object must have:
- "question": the question text
- "options": array of exactly 4 option strings  
- "correct": index of the correct option (0-3)
- "explanation": a brief 1-sentence explanation

Example format:
[{{"question":"What is 2+2?","options":["3","4","5","6"],"correct":1,"explanation":"2+2 equals 4."}}]

Return ONLY the JSON array, no markdown, no code blocks, no other text."""
    
    result = gemini_generate(prompt, system_instruction="You are a quiz generator. Return ONLY valid JSON arrays. No markdown formatting, no code blocks, no explanations outside the JSON.", max_tokens=1000)
    
    if result['success']:
        text = result['text'].strip()
        # Clean up any markdown code blocks
        if text.startswith('```'):
            text = text.split('\n', 1)[-1]
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0]
        text = text.strip()
        
        try:
            questions = json.loads(text)
            return JsonResponse({'success': True, 'questions': questions})
        except json.JSONDecodeError:
            return JsonResponse({'success': True, 'raw_text': text, 'parse_error': True})
    else:
        return JsonResponse({'success': False, 'error': result['error']})


# ============================
# AI SUMMARIZER (Gemini)
# ============================

@login_required
@require_POST
def ai_summarize(request):
    """AJAX endpoint to summarize text using Gemini."""
    from dashboard.ai_services import gemini_generate
    
    text = request.POST.get('text', '').strip()
    if not text:
        return JsonResponse({'error': 'No text provided'}, status=400)
    
    prompt = f"Summarize the following text in 3-5 concise bullet points:\n\n{text[:2000]}"
    result = gemini_generate(prompt, max_tokens=300)
    
    if result['success']:
        return JsonResponse({'success': True, 'summary': result['text']})
    return JsonResponse({'success': False, 'error': result['error']})


# ============================
# TRANSLATOR (Sarvam AI)
# ============================

@login_required
def translate_view(request):
    from dashboard.ai_services import SARVAM_LANGUAGES
    return render(request, 'dashboard/translate.html', {
        'languages': SARVAM_LANGUAGES,
    })


@login_required
@require_POST
def translate_api(request):
    """AJAX endpoint for translation."""
    from dashboard.ai_services import sarvam_translate
    
    text = request.POST.get('text', '').strip()
    source = request.POST.get('source_lang', 'en-IN')
    target = request.POST.get('target_lang', 'hi-IN')
    
    if not text:
        return JsonResponse({'error': 'No text provided'}, status=400)
    
    result = sarvam_translate(text, source, target)
    return JsonResponse(result)


# ============================
# TEXT-TO-SPEECH (Sarvam AI)
# ============================

@login_required
@require_POST
def tts_api(request):
    """AJAX endpoint for text-to-speech."""
    from dashboard.ai_services import sarvam_tts
    
    text = request.POST.get('text', '').strip()
    language = request.POST.get('language', 'hi-IN')
    
    if not text:
        return JsonResponse({'error': 'No text provided'}, status=400)
    
    result = sarvam_tts(text, language)
    return JsonResponse(result)


# ============================
# PERSONAL NOTES
# ============================

@login_required
def notes_view(request):
    user = request.user
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            title = request.POST.get('title', 'Untitled')
            content = request.POST.get('content', '')
            color = request.POST.get('color', 'indigo')
            Note.objects.create(user=user, title=title, content=content, color=color)
        elif action == 'update':
            note_id = request.POST.get('note_id')
            note = Note.objects.filter(id=note_id, user=user).first()
            if note:
                note.title = request.POST.get('title', note.title)
                note.content = request.POST.get('content', note.content)
                note.color = request.POST.get('color', note.color)
                note.save()
        elif action == 'delete':
            note_id = request.POST.get('note_id')
            Note.objects.filter(id=note_id, user=user).delete()
        elif action == 'pin':
            note_id = request.POST.get('note_id')
            note = Note.objects.filter(id=note_id, user=user).first()
            if note:
                note.is_pinned = not note.is_pinned
                note.save()
        return redirect('notes')
    
    notes = Note.objects.filter(user=user)
    return render(request, 'dashboard/notes.html', {'notes': notes})

