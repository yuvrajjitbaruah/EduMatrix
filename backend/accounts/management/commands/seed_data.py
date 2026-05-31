import os
import random
from datetime import date, timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string
from accounts.models import User
from academics.models import CourseClass
from attendance.models import AttendanceRecord, LeaveRequest

class Command(BaseCommand):
    help = 'Seeds the database with test data for EduMatrix'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Allow demo seed data creation outside DEBUG mode.',
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options['force']:
            self.stdout.write(self.style.ERROR('Refusing to seed demo data while DEBUG is False. Use --force only if you truly want demo users.'))
            return

        demo_password = os.getenv('EDUMATRIX_DEMO_PASSWORD') or get_random_string(18)

        self.stdout.write('🌱 Seeding EduMatrix database...\n')

        # --- Admin ---
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'Admin',
                'last_name': 'User',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
                'email': 'admin@edumatrix.com',
            }
        )
        if created:
            admin.set_password(demo_password)
            admin.save()
            self.stdout.write(self.style.SUCCESS('  ✓ Created admin user'))
        else:
            self.stdout.write('  – Admin user already exists')

        # --- Departments ---
        departments = ['Computer Science', 'Electronics', 'Mechanical']

        # --- Teachers ---
        teachers = []
        teacher_data = [
            ('teacher1', 'Dr. Rajesh', 'Kumar', 'Computer Science'),
            ('teacher2', 'Prof. Anita', 'Sharma', 'Electronics'),
            ('teacher3', 'Dr. Vikram', 'Singh', 'Mechanical'),
        ]
        for uname, fname, lname, dept in teacher_data:
            t, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'role': 'teacher',
                    'department': dept,
                    'email': f'{uname}@edumatrix.com',
                }
            )
            if created:
                t.set_password(demo_password)
                t.save()
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created teacher: {fname} {lname}'))
            teachers.append(t)

        # --- Students ---
        students = []
        student_names = [
            ('student1', 'Demo', 'Student', 'Computer Science'),
            ('student2', 'Chakrika', 'Gogoi', 'Computer Science'),
            ('student3', 'Aarav', 'Patel', 'Computer Science'),
            ('student4', 'Priya', 'Nair', 'Electronics'),
            ('student5', 'Rohan', 'Deshmukh', 'Electronics'),
            ('student6', 'Meera', 'Joshi', 'Electronics'),
            ('student7', 'Arjun', 'Reddy', 'Mechanical'),
            ('student8', 'Sneha', 'Iyer', 'Mechanical'),
            ('student9', 'Karan', 'Mehta', 'Mechanical'),
            ('student10', 'Diya', 'Chatterjee', 'Computer Science'),
        ]
        for uname, fname, lname, dept in student_names:
            s, created = User.objects.get_or_create(
                username=uname,
                defaults={
                    'first_name': fname,
                    'last_name': lname,
                    'role': 'student',
                    'department': dept,
                    'email': f'{uname}@edumatrix.com',
                }
            )
            if created:
                s.set_password(demo_password)
                s.save()
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created student: {fname} {lname}'))
            students.append(s)

        # --- Classes ---
        class_data = [
            ('CS-601', 'Data Structures', 'Computer Science', 'Sem 6', 0),
            ('CS-602', 'Operating Systems', 'Computer Science', 'Sem 6', 0),
            ('EC-601', 'Signal Processing', 'Electronics', 'Sem 6', 1),
            ('EC-602', 'VLSI Design', 'Electronics', 'Sem 6', 1),
            ('ME-601', 'Thermodynamics', 'Mechanical', 'Sem 6', 2),
            ('ME-602', 'Fluid Mechanics', 'Mechanical', 'Sem 6', 2),
        ]
        classes = []
        for name, subject, dept, sem, teacher_idx in class_data:
            cls, created = CourseClass.objects.get_or_create(
                name=name,
                defaults={
                    'subject': subject,
                    'department': dept,
                    'semester': sem,
                    'teacher': teachers[teacher_idx],
                }
            )
            if created:
                # Enroll students from matching department
                dept_students = [s for s in students if s.department == dept]
                cls.students.set(dept_students)
                self.stdout.write(self.style.SUCCESS(f'  ✓ Created class: {name} ({subject}) with {len(dept_students)} students'))
            classes.append(cls)

        # --- Attendance Records (last 30 days) ---
        if AttendanceRecord.objects.count() == 0:
            self.stdout.write('\n  📝 Generating attendance records...')
            today = date.today()
            statuses = ['present', 'present', 'present', 'present', 'absent', 'late']  # weighted
            count = 0
            for cls in classes:
                for student in cls.students.all():
                    for day_offset in range(30):
                        d = today - timedelta(days=day_offset)
                        if d.weekday() < 5:  # weekdays only
                            status = random.choice(statuses)
                            AttendanceRecord.objects.create(
                                student=student,
                                course_class=cls,
                                date=d,
                                status=status,
                            )
                            count += 1
            self.stdout.write(self.style.SUCCESS(f'  ✓ Created {count} attendance records'))
        else:
            self.stdout.write('  – Attendance records already exist')

        # --- Leave Requests ---
        if LeaveRequest.objects.count() == 0:
            self.stdout.write('\n  📋 Generating leave requests...')
            for s in students[:4]:
                start = date.today() + timedelta(days=random.randint(1, 10))
                end = start + timedelta(days=random.randint(1, 3))
                LeaveRequest.objects.create(
                    student=s,
                    start_date=start,
                    end_date=end,
                    reason=random.choice([
                        'Family function to attend.',
                        'Medical appointment scheduled.',
                        'Personal emergency at home.',
                        'Participating in a national-level competition.',
                    ]),
                    status='pending',
                )
            self.stdout.write(self.style.SUCCESS('  ✓ Created 4 leave requests'))

        self.stdout.write(self.style.SUCCESS('\n✅ Database seeded successfully!\n'))
        self.stdout.write('  Demo login password:')
        self.stdout.write('  ────────────────────')
        self.stdout.write(f'  Shared password for created demo users: {demo_password}')
        self.stdout.write('')
