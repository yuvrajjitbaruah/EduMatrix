from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Avg, DecimalField, ExpressionWrapper, F, Q, Sum
from datetime import date, timedelta
from .models import (
    HomeworkEntry, DisciplinaryRecord, ParentGuardian, HealthRecord, BusRoute, StudentTransport,
    HostelRoom, HostelAllocation, InventoryItem, VisitorLog, Certificate, Complaint, Scholarship,
    ScholarshipApplication, ExamSeat, ClassRecording, StudyGroup, StudyGroupMessage, SkillBadge,
    StudentSkill, CourseFeedback, Circular, CircularReceipt, ThoughtOfDay, FlashcardDeck, Flashcard,
    DiaryEntry, KanbanBoard, KanbanColumn, KanbanCard, PhotoAlbum, Photo, MoodEntry, Bookmark, NotificationPreference
)
from academics.models import CourseClass, Exam
from accounts.models import User
from dashboard.access import is_institution_admin, is_platform_admin, scoped_classes, scoped_users
from dashboard.retired import retired_feature_redirect


def _feature_classes_for_user(user):
    if user.role == 'teacher':
        classes = CourseClass.objects.filter(teacher=user)
        if user.institution_id:
            classes = classes.filter(institution=user.institution)
        return classes
    if user.role == 'student':
        classes = user.enrolled_classes.all()
        if user.institution_id:
            classes = classes.filter(institution=user.institution)
        return classes
    if is_institution_admin(user):
        return scoped_classes(user)
    return CourseClass.objects.all()


def _feature_students_for_user(user):
    if is_platform_admin(user):
        return User.objects.filter(role='student')
    if is_institution_admin(user):
        return scoped_users(user).filter(role='student')
    if user.role == 'teacher':
        return User.objects.filter(role='student', enrolled_classes__teacher=user).distinct()
    return None


def _institution_admin_module_guard(request):
    if is_institution_admin(request.user):
        messages.info(request, 'This module is not enabled for institution administrators. Use your institution dashboard, users, departments, classrooms, reports, and communication tools.')
        return redirect('dashboard_home')
    return None


# ============================
# 1. HOMEWORK DIARY
# ============================

@login_required
def homework_view(request):
    user = request.user

    if user.role == 'admin':
        messages.info(request, 'Homework is assigned by teachers and completed by students.')
        return redirect('dashboard_home')

    if request.method == 'POST' and user.role == 'teacher':
        action = request.POST.get('action')
        if action == 'create':
            class_id = request.POST.get('class_id')
            description = request.POST.get('description')
            due_date = request.POST.get('due_date')
            is_important = request.POST.get('is_important') == 'on'
            if class_id and description and due_date and CourseClass.objects.filter(id=class_id, teacher=user).exists():
                HomeworkEntry.objects.create(
                    course_class_id=class_id,
                    teacher=user,
                    description=description,
                    due_date=due_date,
                    is_important=is_important
                )
                messages.success(request, 'Homework assigned successfully!')
        elif action == 'delete':
            hw_id = request.POST.get('hw_id')
            HomeworkEntry.objects.filter(id=hw_id, teacher=user).delete()
            messages.success(request, 'Homework entry deleted.')
        return redirect('homework')

    if user.role == 'student':
        entries = HomeworkEntry.objects.filter(course_class__students=user).select_related('course_class', 'teacher').order_by('due_date')
    else:
        entries = HomeworkEntry.objects.filter(teacher=user).select_related('course_class').order_by('-assigned_date')

    teacher_classes = CourseClass.objects.filter(teacher=user) if user.role == 'teacher' else None

    today = date.today()
    upcoming = entries.filter(due_date__gte=today).count()
    overdue = entries.filter(due_date__lt=today).count()

    return render(request, 'dashboard/features/homework.html', {
        'entries': entries,
        'teacher_classes': teacher_classes,
        'upcoming': upcoming,
        'overdue': overdue,
        'total': entries.count(),
    })


# ============================
# 2. DISCIPLINARY RECORDS
# ============================

@login_required
def discipline_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST' and user.role in ('teacher', 'admin'):
        action = request.POST.get('action')
        if action == 'create':
            student_id = request.POST.get('student_id')
            incident_type = request.POST.get('incident_type')
            description = request.POST.get('description')
            severity = request.POST.get('severity', 'minor')
            action_taken = request.POST.get('action_taken', '')
            if student_id and incident_type and description:
                DisciplinaryRecord.objects.create(
                    student_id=student_id,
                    reported_by=user,
                    incident_type=incident_type,
                    description=description,
                    severity=severity,
                    action_taken=action_taken
                )
                messages.success(request, 'Disciplinary record created.')
        elif action == 'update':
            record_id = request.POST.get('record_id')
            record = DisciplinaryRecord.objects.filter(id=record_id).first()
            if record:
                record.action_taken = request.POST.get('action_taken', record.action_taken)
                record.save()
                messages.success(request, 'Record updated.')
        return redirect('discipline')

    if user.role == 'student':
        records = DisciplinaryRecord.objects.filter(student=user).select_related('reported_by')
    else:
        records = DisciplinaryRecord.objects.all().select_related('student', 'reported_by')

    students = User.objects.filter(role='student') if user.role in ('teacher', 'admin') else None

    return render(request, 'dashboard/features/discipline.html', {
        'records': records,
        'students': students,
        'total': records.count(),
        'critical_count': records.filter(severity='critical').count(),
        'major_count': records.filter(severity='major').count(),
    })


# ============================
# 3. PARENT / GUARDIAN INFO
# ============================

@login_required
def guardians_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create' and user.role in ('student', 'admin'):
            student_id = user.id if user.role == 'student' else request.POST.get('student_id')
            name = request.POST.get('name')
            relationship = request.POST.get('relationship')
            phone = request.POST.get('phone')
            email = request.POST.get('email', '')
            occupation = request.POST.get('occupation', '')
            address = request.POST.get('address', '')
            if student_id and name and relationship and phone:
                ParentGuardian.objects.create(
                    student_id=student_id, name=name, relationship=relationship,
                    phone=phone, email=email, occupation=occupation, address=address
                )
                messages.success(request, 'Guardian added successfully!')
        elif action == 'delete':
            g_id = request.POST.get('guardian_id')
            if user.role == 'student':
                ParentGuardian.objects.filter(id=g_id, student=user).delete()
            elif user.role == 'admin':
                ParentGuardian.objects.filter(id=g_id).delete()
            messages.success(request, 'Guardian removed.')
        return redirect('guardians')

    if user.role == 'student':
        guardians = ParentGuardian.objects.filter(student=user)
    else:
        guardians = ParentGuardian.objects.all().select_related('student')

    students = User.objects.filter(role='student') if user.role == 'admin' else None

    return render(request, 'dashboard/features/guardians.html', {
        'guardians': guardians,
        'students': students,
    })


# ============================
# 4. HEALTH RECORDS
# ============================

@login_required
def health_records_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save':
            student_id = user.id if user.role == 'student' else request.POST.get('student_id')
            if student_id:
                record, created = HealthRecord.objects.get_or_create(student_id=student_id)
                record.blood_group = request.POST.get('blood_group', record.blood_group)
                record.allergies = request.POST.get('allergies', record.allergies)
                record.medical_conditions = request.POST.get('medical_conditions', record.medical_conditions)
                record.medications = request.POST.get('medications', record.medications)
                record.emergency_contact_name = request.POST.get('emergency_contact_name', record.emergency_contact_name)
                record.emergency_contact_phone = request.POST.get('emergency_contact_phone', record.emergency_contact_phone)
                record.insurance_info = request.POST.get('insurance_info', record.insurance_info)
                record.save()
                messages.success(request, 'Health record saved successfully!')
        return redirect('health_records')

    if user.role == 'student':
        try:
            record = user.health_record
        except HealthRecord.DoesNotExist:
            record = None
        records = None
    else:
        record = None
        records = HealthRecord.objects.all().select_related('student')

    students = User.objects.filter(role='student') if user.role in ('admin', 'teacher') else None

    return render(request, 'dashboard/features/health.html', {
        'record': record,
        'records': records,
        'students': students,
    })


# ============================
# 5. TRANSPORT MANAGEMENT
# ============================

@login_required
def transport_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_route' and user.role == 'admin':
            route_name = request.POST.get('route_name')
            driver_name = request.POST.get('driver_name')
            driver_phone = request.POST.get('driver_phone')
            vehicle_number = request.POST.get('vehicle_number')
            capacity = request.POST.get('capacity', 40)
            if route_name and driver_name and vehicle_number:
                BusRoute.objects.create(
                    route_name=route_name, driver_name=driver_name,
                    driver_phone=driver_phone, vehicle_number=vehicle_number, capacity=capacity
                )
                messages.success(request, 'Route added!')
        elif action == 'assign' and user.role in ('admin', 'student'):
            student_id = user.id if user.role == 'student' else request.POST.get('student_id')
            route_id = request.POST.get('route_id')
            pickup_point = request.POST.get('pickup_point')
            pickup_time = request.POST.get('pickup_time')
            if route_id and pickup_point and pickup_time:
                StudentTransport.objects.update_or_create(
                    student_id=student_id,
                    defaults={'route_id': route_id, 'pickup_point': pickup_point, 'pickup_time': pickup_time}
                )
                messages.success(request, 'Transport assigned!')
        elif action == 'delete_route' and user.role == 'admin':
            BusRoute.objects.filter(id=request.POST.get('route_id')).delete()
            messages.success(request, 'Route deleted.')
        elif action == 'toggle_route' and user.role == 'admin':
            route = BusRoute.objects.filter(id=request.POST.get('route_id')).first()
            if route:
                route.is_active = not route.is_active
                route.save()
        return redirect('transport')

    routes = BusRoute.objects.all()
    try:
        my_transport = user.transport if user.role == 'student' else None
    except StudentTransport.DoesNotExist:
        my_transport = None

    students = User.objects.filter(role='student') if user.role == 'admin' else None

    return render(request, 'dashboard/features/transport.html', {
        'routes': routes,
        'my_transport': my_transport,
        'students': students,
        'active_routes': routes.filter(is_active=True).count(),
        'total_passengers': StudentTransport.objects.count(),
    })


# ============================
# 6. HOSTEL MANAGEMENT
# ============================

@login_required
def hostel_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST' and user.role == 'admin':
        action = request.POST.get('action')
        if action == 'add_room':
            building = request.POST.get('building')
            room_number = request.POST.get('room_number')
            floor = request.POST.get('floor', 0)
            capacity = request.POST.get('capacity', 2)
            room_type = request.POST.get('room_type', 'double')
            has_ac = request.POST.get('has_ac') == 'on'
            has_attached_bath = request.POST.get('has_attached_bath') == 'on'
            if building and room_number:
                HostelRoom.objects.create(
                    building=building, room_number=room_number, floor=floor,
                    capacity=capacity, room_type=room_type, has_ac=has_ac, has_attached_bath=has_attached_bath
                )
                messages.success(request, 'Room added!')
        elif action == 'allocate':
            student_id = request.POST.get('student_id')
            room_id = request.POST.get('room_id')
            check_in = request.POST.get('check_in')
            monthly_fee = request.POST.get('monthly_fee', 0)
            if student_id and room_id and check_in:
                HostelAllocation.objects.create(
                    student_id=student_id, room_id=room_id, check_in=check_in, monthly_fee=monthly_fee
                )
                messages.success(request, 'Student allocated to room!')
        elif action == 'checkout':
            alloc_id = request.POST.get('alloc_id')
            alloc = HostelAllocation.objects.filter(id=alloc_id).first()
            if alloc:
                alloc.check_out = date.today()
                alloc.save()
                messages.success(request, 'Student checked out.')
        elif action == 'delete_room':
            HostelRoom.objects.filter(id=request.POST.get('room_id')).delete()
            messages.success(request, 'Room deleted.')
        return redirect('hostel')

    rooms = HostelRoom.objects.all()
    if user.role == 'student':
        allocations = HostelAllocation.objects.filter(student=user).select_related('room')
    else:
        allocations = HostelAllocation.objects.filter(check_out__isnull=True).select_related('room', 'student')

    students = User.objects.filter(role='student') if user.role == 'admin' else None
    total_capacity = sum(r.capacity for r in rooms)
    total_occupied = sum(r.current_occupancy for r in rooms)

    return render(request, 'dashboard/features/hostel.html', {
        'rooms': rooms,
        'allocations': allocations,
        'students': students,
        'total_capacity': total_capacity,
        'total_occupied': total_occupied,
        'available': total_capacity - total_occupied,
    })


# ============================
# 7. INVENTORY
# ============================

@login_required
def inventory_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST' and user.role == 'admin':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name')
            category = request.POST.get('category', 'other')
            location = request.POST.get('location')
            quantity = request.POST.get('quantity', 1)
            condition = request.POST.get('condition', 'good')
            purchase_cost = request.POST.get('purchase_cost', 0)
            notes = request.POST.get('notes', '')
            if name and location:
                InventoryItem.objects.create(
                    name=name, category=category, location=location, quantity=quantity,
                    condition=condition, purchase_cost=purchase_cost, notes=notes,
                    purchase_date=date.today()
                )
                messages.success(request, 'Item added to inventory!')
        elif action == 'update':
            item_id = request.POST.get('item_id')
            item = InventoryItem.objects.filter(id=item_id).first()
            if item:
                item.quantity = request.POST.get('quantity', item.quantity)
                item.condition = request.POST.get('condition', item.condition)
                item.location = request.POST.get('location', item.location)
                item.notes = request.POST.get('notes', item.notes)
                item.save()
                messages.success(request, 'Item updated!')
        elif action == 'delete':
            InventoryItem.objects.filter(id=request.POST.get('item_id')).delete()
            messages.success(request, 'Item removed.')
        return redirect('inventory')

    items = InventoryItem.objects.all().only(
        'id', 'name', 'category', 'location', 'quantity', 'condition',
        'purchase_date', 'purchase_cost', 'last_maintained', 'notes',
    )
    category_filter = request.GET.get('category')
    if category_filter:
        items = items.filter(category=category_filter)

    value_expression = ExpressionWrapper(
        F('purchase_cost') * F('quantity'),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    total_value = items.aggregate(total=Sum(value_expression))['total'] or 0
    total_items = items.count()
    damaged_count = items.filter(condition__in=['poor', 'damaged']).count()
    categories = InventoryItem.objects.order_by('category').values_list('category', flat=True).distinct()

    return render(request, 'dashboard/features/inventory.html', {
        'items': items[:100],
        'total_items': total_items,
        'total_value': total_value,
        'categories': categories,
        'selected_category': category_filter,
        'damaged_count': damaged_count,
    })


# ============================
# 8. VISITOR LOG
# ============================

@login_required
def visitors_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST' and user.role in ('admin', 'teacher'):
        action = request.POST.get('action')
        if action == 'log_in':
            visitor_name = request.POST.get('visitor_name')
            purpose = request.POST.get('purpose')
            contact_number = request.POST.get('contact_number')
            visiting_whom = request.POST.get('visiting_whom')
            id_proof = request.POST.get('id_proof', '')
            if visitor_name and purpose and contact_number:
                VisitorLog.objects.create(
                    visitor_name=visitor_name, purpose=purpose, contact_number=contact_number,
                    visiting_whom=visiting_whom, id_proof=id_proof, approved_by=user
                )
                messages.success(request, 'Visitor logged in!')
        elif action == 'log_out':
            log_id = request.POST.get('log_id')
            log = VisitorLog.objects.filter(id=log_id, out_time__isnull=True).first()
            if log:
                log.out_time = timezone.now()
                log.save()
                messages.success(request, 'Visitor logged out.')
        elif action == 'delete':
            VisitorLog.objects.filter(id=request.POST.get('log_id')).delete()
        return redirect('visitors')

    logs = VisitorLog.objects.select_related('approved_by').only(
        'id', 'visitor_name', 'purpose', 'contact_number', 'visiting_whom',
        'id_proof', 'in_time', 'out_time', 'approved_by__id',
        'approved_by__username', 'approved_by__first_name', 'approved_by__last_name',
    )[:100]
    currently_in = VisitorLog.objects.filter(out_time__isnull=True).count()
    today_total = VisitorLog.objects.filter(in_time__date=date.today()).count()

    return render(request, 'dashboard/features/visitors.html', {
        'logs': logs,
        'currently_in': currently_in,
        'today_total': today_total,
    })


# ============================
# 9. CERTIFICATES
# ============================

@login_required
def certificates_view(request):
    return retired_feature_redirect(
        request,
        'Certificates',
        redirect_to='dashboard_home',
        extra_message='Academic work now lives inside Classrooms.',
    )

    user = request.user

    if request.method == 'POST' and user.role in ('admin', 'teacher'):
        action = request.POST.get('action')
        if action == 'create':
            student_id = request.POST.get('student_id')
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            certificate_type = request.POST.get('certificate_type', 'merit')
            if student_id and title:
                Certificate.objects.create(
                    student_id=student_id, title=title, description=description,
                    certificate_type=certificate_type, issued_by=user
                )
                messages.success(request, 'Certificate issued!')
        elif action == 'delete':
            Certificate.objects.filter(id=request.POST.get('cert_id')).delete()
            messages.success(request, 'Certificate deleted.')
        return redirect('certificates')

    if user.role == 'student':
        certs = Certificate.objects.filter(student=user).select_related('issued_by')
    else:
        certs = Certificate.objects.all().select_related('student', 'issued_by')

    students = User.objects.filter(role='student') if user.role in ('admin', 'teacher') else None

    return render(request, 'dashboard/features/certificates.html', {
        'certs': certs,
        'students': students,
        'total': certs.count(),
    })


# ============================
# 10. COMPLAINTS
# ============================

@login_required
def complaints_view(request):
    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            subject = request.POST.get('subject')
            description = request.POST.get('description')
            category = request.POST.get('category', 'other')
            priority = request.POST.get('priority', 'medium')
            if subject and description:
                Complaint.objects.create(
                    filed_by=user, subject=subject, description=description,
                    category=category, priority=priority
                )
                messages.success(request, 'Complaint filed successfully!')
        elif action == 'update_status' and user.role in ('admin', 'teacher'):
            complaint_id = request.POST.get('complaint_id')
            status = request.POST.get('status')
            resolution = request.POST.get('resolution', '')
            complaint = Complaint.objects.filter(id=complaint_id).first()
            if complaint:
                complaint.status = status
                complaint.resolution = resolution
                if status == 'resolved':
                    complaint.resolved_date = timezone.now()
                complaint.assigned_to = user
                complaint.save()
                messages.success(request, 'Complaint updated!')
        return redirect('complaints')

    if user.role in ('admin', 'teacher'):
        complaints = Complaint.objects.all().select_related('filed_by', 'assigned_to')
    else:
        complaints = Complaint.objects.filter(filed_by=user)

    return render(request, 'dashboard/features/complaints.html', {
        'complaints': complaints,
        'open_count': complaints.filter(status='open').count(),
        'in_progress_count': complaints.filter(status='in_progress').count(),
        'resolved_count': complaints.filter(status='resolved').count(),
        'total': complaints.count(),
    })


# ============================
# 11. SCHOLARSHIPS
# ============================

@login_required
def scholarships_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create' and user.role == 'admin':
            name = request.POST.get('name')
            description = request.POST.get('description')
            amount = request.POST.get('amount')
            criteria = request.POST.get('criteria')
            deadline = request.POST.get('deadline')
            department = request.POST.get('department', '')
            total_slots = request.POST.get('total_slots', 10)
            if name and description and amount and deadline:
                Scholarship.objects.create(
                    name=name, description=description, amount=amount,
                    criteria=criteria, deadline=deadline, department=department, total_slots=total_slots
                )
                messages.success(request, 'Scholarship created!')
        elif action == 'apply' and user.role == 'student':
            scholarship_id = request.POST.get('scholarship_id')
            statement = request.POST.get('statement')
            gpa = request.POST.get('gpa')
            if scholarship_id and statement:
                if not ScholarshipApplication.objects.filter(student=user, scholarship_id=scholarship_id).exists():
                    ScholarshipApplication.objects.create(
                        student=user, scholarship_id=scholarship_id, statement=statement, gpa=gpa or None
                    )
                    messages.success(request, 'Application submitted!')
                else:
                    messages.warning(request, 'You have already applied.')
        elif action == 'update_app' and user.role == 'admin':
            app_id = request.POST.get('app_id')
            status = request.POST.get('status')
            remarks = request.POST.get('remarks', '')
            app = ScholarshipApplication.objects.filter(id=app_id).first()
            if app:
                app.status = status
                app.remarks = remarks
                app.save()
                messages.success(request, 'Application updated!')
        return redirect('scholarships')

    scholarships = Scholarship.objects.all()
    my_applications = ScholarshipApplication.objects.filter(student=user).select_related('scholarship') if user.role == 'student' else None
    all_applications = ScholarshipApplication.objects.all().select_related('student', 'scholarship') if user.role == 'admin' else None

    return render(request, 'dashboard/features/scholarships.html', {
        'scholarships': scholarships,
        'my_applications': my_applications,
        'all_applications': all_applications,
        'active_count': scholarships.filter(is_active=True).count(),
    })


# ============================
# 12. EXAM SEATING
# ============================

@login_required
def exam_seating_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST' and user.role in ('admin', 'teacher'):
        action = request.POST.get('action')
        if action == 'create':
            exam_id = request.POST.get('exam_id')
            student_id = request.POST.get('student_id')
            room = request.POST.get('room')
            seat_number = request.POST.get('seat_number')
            if exam_id and student_id and room and seat_number:
                ExamSeat.objects.update_or_create(
                    exam_id=exam_id, student_id=student_id,
                    defaults={'room': room, 'seat_number': seat_number}
                )
                messages.success(request, 'Seat assigned!')
        elif action == 'delete':
            ExamSeat.objects.filter(id=request.POST.get('seat_id')).delete()
            messages.success(request, 'Seat assignment removed.')
        return redirect('exam_seating')

    if user.role == 'student':
        seats = ExamSeat.objects.filter(student=user).select_related('exam__course_class')
    else:
        seats = ExamSeat.objects.all().select_related('exam__course_class', 'student')

    exams = Exam.objects.all() if user.role in ('admin', 'teacher') else None
    students = User.objects.filter(role='student') if user.role in ('admin', 'teacher') else None

    return render(request, 'dashboard/features/exam_seating.html', {
        'seats': seats,
        'exams': exams,
        'students': students,
    })


# ============================
# 13. CLASS RECORDINGS
# ============================

@login_required
def recordings_view(request):
    user = request.user

    if user.role == 'admin':
        messages.info(request, 'Class recordings are uploaded by teachers and watched by students.')
        return redirect('dashboard_home')

    if request.method == 'POST' and user.role == 'teacher':
        action = request.POST.get('action')
        if action == 'create':
            class_id = request.POST.get('class_id')
            title = request.POST.get('title')
            video_url = request.POST.get('video_url')
            description = request.POST.get('description', '')
            recording_date = request.POST.get('recording_date')
            duration_minutes = request.POST.get('duration_minutes', 0)
            if class_id and title and video_url and recording_date and CourseClass.objects.filter(id=class_id, teacher=user).exists():
                ClassRecording.objects.create(
                    course_class_id=class_id, title=title, video_url=video_url,
                    description=description, recording_date=recording_date,
                    duration_minutes=duration_minutes, uploaded_by=user
                )
                messages.success(request, 'Recording uploaded!')
        elif action == 'delete':
            ClassRecording.objects.filter(id=request.POST.get('rec_id'), uploaded_by=user).delete()
            messages.success(request, 'Recording deleted.')
        return redirect('recordings')

    if user.role == 'student':
        recordings = ClassRecording.objects.filter(course_class__students=user).select_related('course_class', 'uploaded_by')
    else:
        recordings = ClassRecording.objects.filter(uploaded_by=user).select_related('course_class')

    teacher_classes = CourseClass.objects.filter(teacher=user) if user.role == 'teacher' else None
    total_duration = sum(r.duration_minutes for r in recordings)

    return render(request, 'dashboard/features/recordings.html', {
        'recordings': recordings,
        'teacher_classes': teacher_classes,
        'total_recordings': recordings.count(),
        'total_duration': total_duration,
    })


# ============================
# 14. STUDY GROUPS
# ============================

@login_required
def study_groups_view(request):
    user = request.user
    visible_classes = _feature_classes_for_user(user)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            name = request.POST.get('name')
            description = request.POST.get('description', '')
            class_id = request.POST.get('class_id')
            max_members = request.POST.get('max_members', 10)
            if name:
                if class_id and not visible_classes.filter(id=class_id).exists() and not is_platform_admin(user):
                    messages.error(request, 'Choose a classroom from your institution workspace.')
                    return redirect('study_groups')
                group = StudyGroup.objects.create(
                    name=name, description=description, created_by=user,
                    course_class_id=class_id if class_id else None, max_members=max_members
                )
                group.members.add(user)
                messages.success(request, 'Study group created!')
        elif action == 'join':
            group_id = request.POST.get('group_id')
            group = StudyGroup.objects.filter(id=group_id).first()
            if group and group.members.count() < group.max_members:
                group.members.add(user)
                messages.success(request, f'Joined group: {group.name}')
            else:
                messages.warning(request, 'Group is full.')
        elif action == 'leave':
            group_id = request.POST.get('group_id')
            group = StudyGroup.objects.filter(id=group_id).first()
            if group:
                group.members.remove(user)
                messages.success(request, 'Left the group.')
        elif action == 'send_message':
            group_id = request.POST.get('group_id')
            content = request.POST.get('content')
            if group_id and content:
                StudyGroupMessage.objects.create(group_id=group_id, sender=user, content=content)
        elif action == 'delete' and (is_platform_admin(user) or is_institution_admin(user)):
            group_qs = StudyGroup.objects.all()
            if is_institution_admin(user) and user.institution_id:
                group_qs = group_qs.filter(
                    Q(course_class__institution=user.institution) |
                    Q(created_by__institution=user.institution)
                ).distinct()
            group_qs.filter(id=request.POST.get('group_id')).delete()
            messages.success(request, 'Group deleted.')
        return redirect('study_groups')

    all_groups = StudyGroup.objects.all().prefetch_related('members')
    if not is_platform_admin(user) and user.institution_id:
        all_groups = all_groups.filter(
            Q(course_class__institution=user.institution) |
            Q(created_by__institution=user.institution)
        ).distinct()
    my_groups = list(all_groups.filter(members=user)[:30])
    available_groups = all_groups.exclude(members=user)[:30]

    group_messages = {}
    for group in my_groups:
        group_messages[group.id] = []
    for message in StudyGroupMessage.objects.filter(group__in=my_groups).select_related('sender').only(
        'id', 'group_id', 'sender__id', 'sender__username', 'sender__first_name',
        'sender__last_name', 'content', 'file', 'timestamp',
    ).order_by('group_id', '-timestamp'):
        messages_for_group = group_messages.setdefault(message.group_id, [])
        if len(messages_for_group) < 20:
            messages_for_group.append(message)

    return render(request, 'dashboard/features/study_groups.html', {
        'my_groups': my_groups,
        'available_groups': available_groups,
        'group_messages': group_messages,
        'user_classes': visible_classes,
    })


# ============================
# 15. SKILL TRACKER
# ============================

@login_required
def skills_view(request):
    return retired_feature_redirect(
        request,
        'Skills',
        redirect_to='dashboard_home',
        extra_message='Academic work now lives inside Classrooms.',
    )

    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_badge' and user.role == 'admin':
            name = request.POST.get('name')
            icon = request.POST.get('icon', '⭐')
            category = request.POST.get('category', 'General')
            description = request.POST.get('description', '')
            if name:
                SkillBadge.objects.create(name=name, icon=icon, category=category, description=description)
                messages.success(request, 'Skill badge created!')
        elif action == 'endorse' and user.role in ('teacher', 'admin'):
            student_id = request.POST.get('student_id')
            skill_id = request.POST.get('skill_id')
            level = request.POST.get('level', 1)
            if student_id and skill_id:
                StudentSkill.objects.update_or_create(
                    student_id=student_id, skill_id=skill_id,
                    defaults={'level': level, 'endorsed_by': user}
                )
                messages.success(request, 'Skill endorsed!')
        return redirect('skills')

    if user.role == 'student':
        skills = StudentSkill.objects.filter(student=user).select_related('skill', 'endorsed_by')
    else:
        skills = StudentSkill.objects.all().select_related('student', 'skill', 'endorsed_by')

    all_badges = SkillBadge.objects.all()
    students = User.objects.filter(role='student') if user.role in ('teacher', 'admin') else None

    return render(request, 'dashboard/features/skills.html', {
        'skills': skills,
        'all_badges': all_badges,
        'students': students,
    })


# ============================
# 16. COURSE FEEDBACK
# ============================

@login_required
def feedback_view(request):
    user = request.user
    visible_classes = _feature_classes_for_user(user)

    if request.method == 'POST' and user.role == 'student':
        action = request.POST.get('action')
        if action == 'submit':
            class_id = request.POST.get('class_id')
            rating = request.POST.get('rating', 5)
            review = request.POST.get('review', '')
            is_anonymous = request.POST.get('is_anonymous') == 'on'
            if class_id:
                if not visible_classes.filter(id=class_id).exists():
                    messages.error(request, 'Choose a classroom from your institution workspace.')
                    return redirect('feedback')
                if not CourseFeedback.objects.filter(course_class_id=class_id, student=user).exists():
                    CourseFeedback.objects.create(
                        course_class_id=class_id, student=user, rating=rating,
                        review=review, is_anonymous=is_anonymous
                    )
                    messages.success(request, 'Feedback submitted!')
                else:
                    messages.warning(request, 'You already submitted feedback for this course.')
        return redirect('feedback')

    if user.role == 'student':
        enrolled = visible_classes
        feedbacks = CourseFeedback.objects.filter(student=user).select_related('course_class')
        submitted_class_ids = set(feedbacks.values_list('course_class_id', flat=True))
        pending_classes = enrolled.exclude(id__in=submitted_class_ids)
    elif user.role == 'teacher':
        feedbacks = CourseFeedback.objects.filter(course_class__in=visible_classes).select_related('course_class', 'student')
        pending_classes = None
    elif is_institution_admin(user):
        feedbacks = CourseFeedback.objects.filter(course_class__institution=user.institution).select_related('course_class', 'student') if user.institution_id else CourseFeedback.objects.none()
        pending_classes = None
    else:
        feedbacks = CourseFeedback.objects.all().select_related('course_class', 'student')
        pending_classes = None

    feedback_count = feedbacks.count()
    avg_rating = feedbacks.aggregate(avg=Avg('rating'))['avg'] or 0

    return render(request, 'dashboard/features/feedback.html', {
        'feedbacks': feedbacks[:100],
        'pending_classes': pending_classes if user.role == 'student' else None,
        'avg_rating': round(avg_rating, 1),
        'total_feedbacks': feedback_count,
    })


# ============================
# 17. CIRCULARS / MEMOS
# ============================

@login_required
def circulars_view(request):
    return retired_feature_redirect(
        request,
        'Circulars',
        redirect_to='notices',
        extra_message='Use Notices and Messages for school communication.',
    )

    user = request.user

    if request.method == 'POST' and user.role in ('admin', 'teacher'):
        action = request.POST.get('action')
        if action == 'create':
            title = request.POST.get('title')
            content = request.POST.get('content')
            department = request.POST.get('department', '')
            is_urgent = request.POST.get('is_urgent') == 'on'
            if title and content:
                Circular.objects.create(
                    title=title, content=content, issued_by=user,
                    department=department, is_urgent=is_urgent
                )
                messages.success(request, 'Circular published!')
        elif action == 'delete':
            Circular.objects.filter(id=request.POST.get('circular_id')).delete()
            messages.success(request, 'Circular deleted.')
        return redirect('circulars')

    circulars = list(Circular.objects.select_related('issued_by').only(
        'id', 'title', 'content', 'issued_by__id', 'issued_by__username',
        'issued_by__first_name', 'issued_by__last_name', 'department',
        'issued_date', 'is_urgent', 'attachment',
    )[:100])

    circular_ids = [c.id for c in circulars]
    read_ids = set(CircularReceipt.objects.filter(
        circular_id__in=circular_ids,
        user=user,
    ).values_list('circular_id', flat=True))
    unread_ids = [circular_id for circular_id in circular_ids if circular_id not in read_ids]
    CircularReceipt.objects.bulk_create(
        [CircularReceipt(circular_id=circular_id, user=user) for circular_id in unread_ids],
        ignore_conflicts=True,
    )
    for c in circulars:
        c.is_read = c.id in read_ids

    return render(request, 'dashboard/features/circulars.html', {
        'circulars': circulars,
        'total': len(circulars),
        'urgent_count': sum(1 for c in circulars if c.is_urgent),
    })


# ============================
# 18. FLASHCARDS
# ============================

@login_required
def flashcards_view(request):
    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_deck':
            title = request.POST.get('title')
            subject = request.POST.get('subject', '')
            description = request.POST.get('description', '')
            is_public = request.POST.get('is_public') == 'on'
            if title:
                FlashcardDeck.objects.create(
                    title=title, subject=subject, description=description,
                    created_by=user, is_public=is_public
                )
                messages.success(request, 'Deck created!')
        elif action == 'add_card':
            deck_id = request.POST.get('deck_id')
            front = request.POST.get('front')
            back = request.POST.get('back')
            difficulty = request.POST.get('difficulty', 'medium')
            deck = FlashcardDeck.objects.filter(id=deck_id, created_by=user).first()
            if deck and front and back:
                Flashcard.objects.create(deck=deck, front=front, back=back, difficulty=difficulty)
                messages.success(request, 'Card added!')
        elif action == 'delete_deck':
            FlashcardDeck.objects.filter(id=request.POST.get('deck_id'), created_by=user).delete()
            messages.success(request, 'Deck deleted.')
        elif action == 'delete_card':
            card = Flashcard.objects.filter(id=request.POST.get('card_id')).first()
            if card and card.deck.created_by == user:
                card.delete()
                messages.success(request, 'Card deleted.')
        return redirect('flashcards')

    my_decks = FlashcardDeck.objects.filter(created_by=user).prefetch_related('cards')
    public_decks = FlashcardDeck.objects.filter(is_public=True).exclude(created_by=user)
    if not is_platform_admin(user):
        if user.institution_id:
            public_decks = public_decks.filter(created_by__institution=user.institution)
        else:
            public_decks = public_decks.none()
    public_decks = public_decks.prefetch_related('cards')

    # Study mode - get deck cards
    study_deck_id = request.GET.get('study')
    study_cards = []
    study_deck = None
    if study_deck_id:
        allowed_decks = FlashcardDeck.objects.filter(Q(created_by=user) | Q(id__in=public_decks.values('id')))
        study_deck = allowed_decks.filter(id=study_deck_id).first()
        if study_deck:
            study_cards = list(study_deck.cards.all().values('id', 'front', 'back', 'difficulty'))

    import json
    return render(request, 'dashboard/features/flashcards.html', {
        'my_decks': my_decks,
        'public_decks': public_decks,
        'study_deck': study_deck,
        'study_cards_json': json.dumps(study_cards),
        'total_cards': sum(d.card_count for d in my_decks),
    })


# ============================
# 19. STUDENT DIARY
# ============================

@login_required
def diary_view(request):
    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            title = request.POST.get('title')
            content = request.POST.get('content')
            mood = request.POST.get('mood', '😊')
            is_private = request.POST.get('is_private') != 'off'
            if title and content:
                DiaryEntry.objects.create(
                    student=user, title=title, content=content, mood=mood, is_private=is_private
                )
                messages.success(request, 'Entry saved!')
        elif action == 'delete':
            DiaryEntry.objects.filter(id=request.POST.get('entry_id'), student=user).delete()
            messages.success(request, 'Entry deleted.')
        return redirect('diary')

    entries = DiaryEntry.objects.filter(student=user)

    return render(request, 'dashboard/features/diary.html', {
        'entries': entries,
        'total': entries.count(),
    })


# ============================
# 20. KANBAN BOARD
# ============================

@login_required
def kanban_view(request):
    return retired_feature_redirect(
        request,
        'Kanban',
        redirect_to='todos',
        extra_message='Use Todo List and Classroom workflows instead.',
    )

    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_board':
            title = request.POST.get('title')
            if title:
                board = KanbanBoard.objects.create(title=title, user=user)
                # Create default columns
                KanbanColumn.objects.create(board=board, title='To Do', position=0, color='rose')
                KanbanColumn.objects.create(board=board, title='In Progress', position=1, color='amber')
                KanbanColumn.objects.create(board=board, title='Done', position=2, color='emerald')
                messages.success(request, 'Board created!')
        elif action == 'add_column':
            board_id = request.POST.get('board_id')
            title = request.POST.get('title')
            color = request.POST.get('color', 'indigo')
            board = KanbanBoard.objects.filter(id=board_id, user=user).first()
            if board and title:
                pos = board.columns.count()
                KanbanColumn.objects.create(board=board, title=title, position=pos, color=color)
        elif action == 'add_card':
            column_id = request.POST.get('column_id')
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            priority = request.POST.get('priority', 'medium')
            due_date = request.POST.get('due_date') or None
            column = KanbanColumn.objects.filter(id=column_id).first()
            if column and column.board.user == user and title:
                pos = column.cards.count()
                KanbanCard.objects.create(
                    column=column, title=title, description=description,
                    priority=priority, due_date=due_date, position=pos
                )
        elif action == 'move_card':
            card_id = request.POST.get('card_id')
            target_column_id = request.POST.get('target_column_id')
            card = KanbanCard.objects.filter(id=card_id).first()
            if card and card.column.board.user == user:
                card.column_id = target_column_id
                card.save()
        elif action == 'delete_card':
            card = KanbanCard.objects.filter(id=request.POST.get('card_id')).first()
            if card and card.column.board.user == user:
                card.delete()
        elif action == 'delete_board':
            KanbanBoard.objects.filter(id=request.POST.get('board_id'), user=user).delete()
            messages.success(request, 'Board deleted.')
        return redirect('kanban')

    boards = KanbanBoard.objects.filter(user=user).prefetch_related('columns__cards')

    # Current board
    board_id = request.GET.get('board')
    current_board = None
    if board_id:
        current_board = KanbanBoard.objects.filter(id=board_id, user=user).prefetch_related('columns__cards').first()
    elif boards.exists():
        current_board = boards.first()

    return render(request, 'dashboard/features/kanban.html', {
        'boards': boards,
        'current_board': current_board,
    })


# ============================
# 21. PHOTO GALLERY
# ============================

@login_required
def gallery_view(request):
    return retired_feature_redirect(
        request,
        'Gallery',
        redirect_to='dashboard_home',
        extra_message='This module is no longer part of the active platform.',
    )

    user = request.user

    if request.method == 'POST' and user.role in ('admin', 'teacher'):
        action = request.POST.get('action')
        if action == 'create_album':
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            if title:
                PhotoAlbum.objects.create(title=title, description=description, created_by=user)
                messages.success(request, 'Album created!')
        elif action == 'upload_photo':
            album_id = request.POST.get('album_id')
            caption = request.POST.get('caption', '')
            photo_file = request.FILES.get('photo')
            if album_id and photo_file:
                Photo.objects.create(
                    album_id=album_id, image=photo_file, caption=caption, uploaded_by=user
                )
                messages.success(request, 'Photo uploaded!')
        elif action == 'delete_album':
            PhotoAlbum.objects.filter(id=request.POST.get('album_id')).delete()
            messages.success(request, 'Album deleted.')
        elif action == 'delete_photo':
            Photo.objects.filter(id=request.POST.get('photo_id')).delete()
        return redirect('gallery')

    albums = PhotoAlbum.objects.all().prefetch_related('photos')
    album_id = request.GET.get('album')
    current_album = None
    if album_id:
        current_album = PhotoAlbum.objects.filter(id=album_id).prefetch_related('photos').first()

    return render(request, 'dashboard/features/gallery.html', {
        'albums': albums,
        'current_album': current_album,
        'total_photos': Photo.objects.count(),
    })


# ============================
# 22. MOOD TRACKER
# ============================

@login_required
def mood_view(request):
    user = request.user
    guard = _institution_admin_module_guard(request)
    if guard:
        return guard

    if request.method == 'POST' and user.role == 'student':
        action = request.POST.get('action')
        if action == 'log':
            mood = request.POST.get('mood')
            note = request.POST.get('note', '')
            if mood:
                MoodEntry.objects.update_or_create(
                    student=user, date=date.today(),
                    defaults={'mood': mood, 'note': note}
                )
                messages.success(request, 'Mood logged!')
        elif action == 'delete':
            MoodEntry.objects.filter(id=request.POST.get('entry_id'), student=user).delete()
        return redirect('mood')

    if user.role == 'student':
        moods = MoodEntry.objects.filter(student=user)
    else:
        moods = MoodEntry.objects.all().select_related('student')

    # Build 30-day mood data for chart
    mood_chart = []
    for i in range(30):
        d = date.today() - timedelta(days=29 - i)
        entry = moods.filter(date=d).first() if user.role == 'student' else None
        mood_chart.append({
            'date': d.strftime('%d'),
            'mood': entry.mood if entry else '',
        })

    today_logged = moods.filter(date=date.today()).exists() if user.role == 'student' else False
    import json
    return render(request, 'dashboard/features/mood.html', {
        'moods': moods[:30],
        'mood_chart_json': json.dumps(mood_chart),
        'today_logged': today_logged,
        'total_entries': moods.count(),
    })


# ============================
# 23. NOTIFICATION PREFERENCES
# ============================

@login_required
def notifications_prefs_view(request):
    user = request.user

    prefs, created = NotificationPreference.objects.get_or_create(user=user)

    if request.method == 'POST':
        prefs.notice_enabled = request.POST.get('notice_enabled') == 'on'
        prefs.message_enabled = request.POST.get('message_enabled') == 'on'
        prefs.assignment_enabled = request.POST.get('assignment_enabled') == 'on'
        prefs.grade_enabled = request.POST.get('grade_enabled') == 'on'
        prefs.attendance_enabled = request.POST.get('attendance_enabled') == 'on'
        prefs.event_enabled = request.POST.get('event_enabled') == 'on'
        prefs.forum_enabled = request.POST.get('forum_enabled') == 'on'
        prefs.save()
        messages.success(request, 'Notification preferences saved!')
        return redirect('notifications_prefs')

    return render(request, 'dashboard/features/notifications.html', {'prefs': prefs})


# ============================
# 24. BOOKMARKS
# ============================

@login_required
def bookmarks_view(request):
    user = request.user

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            content_type = request.POST.get('content_type')
            object_id = request.POST.get('object_id')
            title = request.POST.get('title')
            url = request.POST.get('url', '')
            if content_type and object_id and title:
                Bookmark.objects.get_or_create(
                    user=user, content_type=content_type, object_id=object_id,
                    defaults={'title': title, 'url': url}
                )
                messages.success(request, 'Bookmarked!')
        elif action == 'delete':
            Bookmark.objects.filter(id=request.POST.get('bookmark_id'), user=user).delete()
            messages.success(request, 'Bookmark removed.')
        return redirect('bookmarks')

    bookmarks = Bookmark.objects.filter(user=user)
    type_filter = request.GET.get('type')
    if type_filter:
        bookmarks = bookmarks.filter(content_type=type_filter)

    return render(request, 'dashboard/features/bookmarks.html', {
        'bookmarks': bookmarks,
        'type_filter': type_filter,
        'total': bookmarks.count(),
    })


# ============================
# 25. POMODORO TIMER
# ============================

@login_required
def pomodoro_view(request):
    return render(request, 'dashboard/features/pomodoro.html')


# ============================
# 26. WHITEBOARD
# ============================

@login_required
def whiteboard_view(request):
    return render(request, 'dashboard/features/whiteboard.html')
