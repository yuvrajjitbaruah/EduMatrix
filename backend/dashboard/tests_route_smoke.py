from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from academics.models import CourseClass, Department, Exam
from assignments.models import Assignment
from dashboard.models import Event, LibraryResource
from messaging.models import Message


class DashboardRouteSmokeTests(TestCase):
    route_names = [
        'dashboard_home',
        'smart_command_center',
        'planner',
        'launch_center',
        'integrations_hub',
        'departments',
        'classes',
        'users_list',
        'reports',
        'mark_attendance',
        'my_attendance',
        'leave_requests',
        'notices',
        'timetable',
        'grades',
        'export_reports_csv',
        'profile_settings',
        'assignments',
        'forum',
        'inbox',
        'sent_messages',
        'compose_message',
        'calendar',
        'analytics',
        'fees',
        'library',
        'achievements',
        'polls',
        'todos',
        'activity',
        'help',
        'ai_chat',
        'ai_quiz',
        'translate',
        'notes',
        'homework',
        'discipline',
        'guardians',
        'health_records',
        'transport',
        'hostel',
        'inventory',
        'visitors',
        'certificates',
        'complaints',
        'scholarships',
        'exam_seating',
        'recordings',
        'study_groups',
        'skills',
        'feedback',
        'circulars',
        'flashcards',
        'diary',
        'kanban',
        'gallery',
        'mood',
        'notifications_prefs',
        'bookmarks',
        'pomodoro',
        'whiteboard',
        'quiz_list',
        'create_quiz',
    ]

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            username='admin-smoke',
            email='admin-smoke@example.com',
            password='StrongPass123!',
            role='admin',
            is_staff=True,
            is_superuser=True,
        )
        cls.teacher_user = User.objects.create_user(
            username='teacher-smoke',
            email='teacher-smoke@example.com',
            password='StrongPass123!',
            role='teacher',
            department='Computer Science',
        )
        cls.student_user = User.objects.create_user(
            username='student-smoke',
            email='student-smoke@example.com',
            password='StrongPass123!',
            role='student',
            department='Computer Science',
            roll_no='SMOKE001',
        )
        cls.department = Department.objects.create(
            name='Computer Science',
            code='CS',
            created_by=cls.admin_user,
        )
        cls.course_class = CourseClass.objects.create(
            name='CS 101',
            subject='Programming',
            department=cls.department.name,
            semester='1',
            teacher=cls.teacher_user,
        )
        cls.course_class.students.add(cls.student_user)
        cls.exam = Exam.objects.create(
            title='Smoke Test Midterm',
            course_class=cls.course_class,
            date=date.today(),
            total_marks=100,
        )
        cls.assignment = Assignment.objects.create(
            title='Smoke Assignment',
            description='Route smoke assignment',
            course_class=cls.course_class,
            created_by=cls.teacher_user,
            due_date=timezone.now() + timedelta(days=7),
        )
        cls.event = Event.objects.create(
            title='Smoke Event',
            description='Route smoke event',
            event_date=date.today() + timedelta(days=1),
            created_by=cls.admin_user,
        )
        cls.resource = LibraryResource.objects.create(
            title='Smoke Book',
            description='Route smoke resource',
            category='textbook',
            uploaded_by=cls.admin_user,
            available_copies=2,
        )
        Message.objects.create(
            sender=cls.admin_user,
            receiver=cls.student_user,
            subject='Smoke message',
            body='Testing inbox rendering.',
        )

    def test_main_modules_render_for_each_role_without_server_errors(self):
        users = [self.admin_user, self.teacher_user, self.student_user]
        for user in users:
            self.client.force_login(user)
            for route_name in self.route_names:
                with self.subTest(role=user.role, route=route_name):
                    response = self.client.get(reverse(route_name))
                    self.assertNotEqual(response.status_code, 500)
                    self.assertIn(response.status_code, {200, 302, 403})
