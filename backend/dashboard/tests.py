from django.test import TestCase
from django.urls import reverse

from accounts.models import Institution, PlatformInquiry, User
from academics.models import CourseClass, StudyMaterial
from dashboard.models import FlashcardDeck, TodoItem


class ProfileSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='profile-user',
            email='profile@example.com',
            password='StrongPass123!',
            role='admin',
            first_name='Profile',
            last_name='Owner',
        )
        self.other_user = User.objects.create_user(
            username='taken-name',
            email='taken@example.com',
            password='StrongPass123!',
            role='teacher',
        )
        self.client.force_login(self.user)

    def test_username_availability_endpoint_reports_taken_and_current_names(self):
        taken_response = self.client.get(reverse('username_availability'), {'username': 'taken-name'})
        self.assertEqual(taken_response.status_code, 200)
        self.assertFalse(taken_response.json()['available'])

        current_response = self.client.get(reverse('username_availability'), {'username': 'profile-user'})
        self.assertEqual(current_response.status_code, 200)
        self.assertTrue(current_response.json()['available'])
        self.assertTrue(current_response.json()['is_current'])

    def test_profile_settings_updates_username(self):
        response = self.client.post(reverse('profile_settings'), {
            'action': 'update_profile',
            'first_name': 'Profile',
            'last_name': 'Owner',
            'username': 'profile-user-updated',
            'email': 'profile@example.com',
            'phone_number': '+919876543210',
        })

        self.assertRedirects(response, reverse('profile_settings'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, 'profile-user-updated')
        self.assertEqual(self.user.phone_number, '+919876543210')


class SidebarAccessTests(TestCase):
    def test_teacher_sidebar_hides_integrations_link(self):
        institution = Institution.objects.create(
            name='Faculty Institute',
            domain='faculty.edu',
        )
        teacher = User.objects.create_user(
            username='teacher@faculty.edu',
            email='teacher@faculty.edu',
            password='StrongPass123!',
            role='teacher',
            institution=institution,
            first_name='Teach',
            last_name='User',
        )
        self.client.force_login(teacher)

        response = self.client.get(reverse('dashboard_home'))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse('integrations_hub'))
        self.assertContains(response, 'Faculty Institute')

    def test_platform_admin_sidebar_shows_integrations_link(self):
        admin_user = User.objects.create_user(
            username='platform-admin',
            email='admin@example.com',
            password='StrongPass123!',
            role='admin',
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse('dashboard_home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('integrations_hub'))


class PowerCenterRequestTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='platform-admin',
            email='admin@example.com',
            password='StrongPass123!',
            role='admin',
        )
        self.inquiry = PlatformInquiry.objects.create(
            institute_name='Northbridge Academy',
            contact_name='Avery Stone',
            email='avery@northbridge.edu',
            institution_domain='northbridge.edu',
            phone='+910000000000',
            student_count='850',
            message='We want to onboard our school.',
        )
        self.client.force_login(self.admin_user)

    def test_power_center_shows_open_request_details(self):
        response = self.client.get(reverse('smart_command_center'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Open Requests')
        self.assertContains(response, 'Northbridge Academy')
        self.assertContains(response, 'Avery Stone')
        self.assertContains(response, 'avery@northbridge.edu')
        self.assertContains(response, 'Save Verification')

    def test_power_center_can_verify_and_link_request(self):
        response = self.client.post(reverse('smart_command_center'), {
            'action': 'update_inquiry_verification',
            'inquiry_id': self.inquiry.id,
            'verification_status': 'verified',
        })

        self.assertRedirects(response, reverse('smart_command_center'))
        self.inquiry.refresh_from_db()
        self.assertEqual(self.inquiry.verification_status, 'verified')
        self.assertIsNotNone(self.inquiry.linked_institution)
        self.assertEqual(self.inquiry.linked_institution.domain, 'northbridge.edu')

    def test_power_center_shows_smart_briefing_and_action_playbook(self):
        response = self.client.get(reverse('smart_command_center'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Smart Briefing')
        self.assertContains(response, 'Action Playbook')
        self.assertContains(response, 'Review onboarding requests')
        self.assertContains(response, 'Save to Planner')
        self.assertContains(response, 'Automation Studio')
        self.assertContains(response, 'Run Sweep')
        self.assertContains(response, 'Workflow Recipes')
        self.assertContains(response, 'Launch readiness sprint')

    def test_power_center_can_save_action_to_planner(self):
        response = self.client.post(reverse('smart_command_center'), {
            'action': 'capture_power_task',
            'title': 'Review onboarding requests',
            'description': 'Open each request and move contacted leads forward.',
            'priority': 'high',
            'due_date': '2026-05-01',
        })

        self.assertRedirects(response, reverse('smart_command_center'))
        task = TodoItem.objects.get(user=self.admin_user, title='Review onboarding requests')
        self.assertEqual(task.priority, 'high')
        self.assertFalse(task.is_done)

    def test_power_center_automation_sweep_creates_planner_tasks(self):
        response = self.client.post(reverse('smart_command_center'), {
            'action': 'run_power_automation_sweep',
            'automation_title': ['Request verification sweep', 'Weekly operations digest'],
            'automation_description': [
                'Create follow-ups for every open institution request.',
                'Schedule a weekly summary across the workspace.',
            ],
            'automation_priority': ['high', 'low'],
            'automation_due_date': ['2026-05-02', '2026-05-04'],
        })

        self.assertRedirects(response, reverse('smart_command_center'))
        self.assertTrue(TodoItem.objects.filter(user=self.admin_user, title='Request verification sweep', priority='high').exists())
        self.assertTrue(TodoItem.objects.filter(user=self.admin_user, title='Weekly operations digest', priority='low').exists())

    def test_power_center_workflow_recipe_creates_planner_bundle(self):
        response = self.client.post(reverse('smart_command_center'), {
            'action': 'run_power_recipe_bundle',
            'automation_title': ['Verify open institution requests', 'Audit user and role access'],
            'automation_description': [
                'Review request details, domain eligibility, and onboarding status.',
                'Check admins, teachers, students, and institution scoping before launch.',
            ],
            'automation_priority': ['high', 'high'],
            'automation_due_date': ['2026-05-02', '2026-05-03'],
        })

        self.assertRedirects(response, reverse('smart_command_center'))
        self.assertEqual(
            TodoItem.objects.filter(
                user=self.admin_user,
                title__in=['Verify open institution requests', 'Audit user and role access'],
            ).count(),
            2,
        )


class InstitutionAdminAccessTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Faculty Institute',
            domain='faculty.edu',
        )
        self.institution_admin = User.objects.create_user(
            username='institution-admin',
            email='admin@faculty.edu',
            password='StrongPass123!',
            role='institution_admin',
            institution=self.institution,
        )
        self.client.force_login(self.institution_admin)

    def test_institution_admin_cannot_open_unscoped_platform_modules(self):
        guarded_routes = [
            'discipline',
            'guardians',
            'health_records',
            'transport',
            'hostel',
            'inventory',
            'visitors',
            'scholarships',
            'exam_seating',
            'mood',
        ]

        for route_name in guarded_routes:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertRedirects(response, reverse('dashboard_home'))

    def test_flashcards_public_decks_are_institution_scoped(self):
        other_institution = Institution.objects.create(
            name='Other Institute',
            domain='other.edu',
        )
        same_user = User.objects.create_user(
            username='teacher@faculty.edu',
            email='teacher@faculty.edu',
            password='StrongPass123!',
            role='teacher',
            institution=self.institution,
        )
        other_user = User.objects.create_user(
            username='teacher@other.edu',
            email='teacher@other.edu',
            password='StrongPass123!',
            role='teacher',
            institution=other_institution,
        )
        FlashcardDeck.objects.create(title='Same Institution Deck', created_by=same_user, is_public=True)
        FlashcardDeck.objects.create(title='Other Institution Deck', created_by=other_user, is_public=True)

        response = self.client.get(reverse('flashcards'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Same Institution Deck')
        self.assertNotContains(response, 'Other Institution Deck')


class ClassroomWorkspaceTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name='Classroom Institute',
            domain='classroom.edu',
        )
        self.teacher = User.objects.create_user(
            username='teacher@classroom.edu',
            email='teacher@classroom.edu',
            password='StrongPass123!',
            role='teacher',
            institution=self.institution,
            first_name='Class',
            last_name='Teacher',
        )
        self.student = User.objects.create_user(
            username='student@classroom.edu',
            email='student@classroom.edu',
            password='StrongPass123!',
            role='student',
            institution=self.institution,
            first_name='Class',
            last_name='Student',
        )
        self.institution_admin = User.objects.create_user(
            username='admin@classroom.edu',
            email='admin@classroom.edu',
            password='StrongPass123!',
            role='institution_admin',
            institution=self.institution,
        )
        self.other_institution_admin = User.objects.create_user(
            username='admin@other.edu',
            email='admin@other.edu',
            password='StrongPass123!',
            role='institution_admin',
            institution=Institution.objects.create(name='Other Institute', domain='other.edu'),
        )
        self.course_class = CourseClass.objects.create(
            institution=self.institution,
            name='Chemistry II',
            department='Science',
            subject='Chemistry',
            semester='2',
            teacher=self.teacher,
        )
        self.course_class.students.add(self.student)
        self.material = StudyMaterial.objects.create(
            title='Lab Safety Notes',
            description='Shared before practical class.',
            course_class=self.course_class,
            url='https://example.com/lab-safety',
        )

    def test_classroom_page_shows_classwork_materials_people_and_delete_for_teacher(self):
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('classroom_detail', args=[self.course_class.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Class Stream')
        self.assertContains(response, 'Study Materials')
        self.assertContains(response, 'People')
        self.assertContains(response, 'Delete')
        self.assertContains(response, 'Lab Safety Notes')

    def test_teacher_can_delete_study_material_from_classroom(self):
        self.client.force_login(self.teacher)

        response = self.client.post(reverse('classroom_detail', args=[self.course_class.id]), {
            'action': 'delete_material',
            'material_id': self.material.id,
        })

        self.assertRedirects(response, reverse('classroom_detail', args=[self.course_class.id]))
        self.assertFalse(StudyMaterial.objects.filter(id=self.material.id).exists())

    def test_institution_admin_can_moderate_own_classroom_material(self):
        self.client.force_login(self.institution_admin)

        response = self.client.post(reverse('classroom_detail', args=[self.course_class.id]), {
            'action': 'delete_material',
            'material_id': self.material.id,
        })

        self.assertRedirects(response, reverse('classroom_detail', args=[self.course_class.id]))
        self.assertFalse(StudyMaterial.objects.filter(id=self.material.id).exists())

    def test_student_cannot_delete_study_material(self):
        self.client.force_login(self.student)

        response = self.client.post(reverse('classroom_detail', args=[self.course_class.id]), {
            'action': 'delete_material',
            'material_id': self.material.id,
        })

        self.assertRedirects(response, reverse('classroom_detail', args=[self.course_class.id]))
        self.assertTrue(StudyMaterial.objects.filter(id=self.material.id).exists())

    def test_other_institution_admin_cannot_access_classroom(self):
        self.client.force_login(self.other_institution_admin)

        response = self.client.get(reverse('classroom_detail', args=[self.course_class.id]))

        self.assertEqual(response.status_code, 404)
