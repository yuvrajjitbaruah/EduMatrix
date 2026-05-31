from django.contrib import admin
from .models import (
    Notice, Event, FeeRecord, LibraryResource, Achievement, StudentXP,
    Poll, PollOption, PollVote, TodoItem, ActivityLog, HelpFAQ,
    Note, ChatSession,
    HomeworkEntry, DisciplinaryRecord, ParentGuardian, HealthRecord, BusRoute, StudentTransport,
    HostelRoom, HostelAllocation, InventoryItem, VisitorLog, Certificate, Complaint, Scholarship,
    ScholarshipApplication, ExamSeat, ClassRecording, StudyGroup, StudyGroupMessage, SkillBadge,
    StudentSkill, CourseFeedback, Circular, CircularReceipt, ThoughtOfDay, FlashcardDeck, Flashcard,
    DiaryEntry, KanbanBoard, KanbanColumn, KanbanCard, PhotoAlbum, Photo, MoodEntry, NotificationPreference, Bookmark
)

# Core Dashboard Models
admin.site.register(Notice)
admin.site.register(Event)
admin.site.register(FeeRecord)
admin.site.register(LibraryResource)
admin.site.register(Achievement)
admin.site.register(StudentXP)
admin.site.register(Poll)
admin.site.register(PollOption)
admin.site.register(PollVote)
admin.site.register(TodoItem)
admin.site.register(ActivityLog)
admin.site.register(HelpFAQ)
admin.site.register(Note)
admin.site.register(ChatSession)

# Expansion Models
admin.site.register(HomeworkEntry)
admin.site.register(DisciplinaryRecord)
admin.site.register(ParentGuardian)
admin.site.register(HealthRecord)
admin.site.register(BusRoute)
admin.site.register(StudentTransport)
admin.site.register(HostelRoom)
admin.site.register(HostelAllocation)
admin.site.register(InventoryItem)
admin.site.register(VisitorLog)
admin.site.register(Certificate)
admin.site.register(Complaint)
admin.site.register(Scholarship)
admin.site.register(ScholarshipApplication)
admin.site.register(ExamSeat)
admin.site.register(ClassRecording)
admin.site.register(StudyGroup)
admin.site.register(StudyGroupMessage)
admin.site.register(SkillBadge)
admin.site.register(StudentSkill)
admin.site.register(CourseFeedback)
admin.site.register(Circular)
admin.site.register(CircularReceipt)
admin.site.register(ThoughtOfDay)
admin.site.register(FlashcardDeck)
admin.site.register(Flashcard)
admin.site.register(DiaryEntry)
admin.site.register(KanbanBoard)
admin.site.register(KanbanColumn)
admin.site.register(KanbanCard)
admin.site.register(PhotoAlbum)
admin.site.register(Photo)
admin.site.register(MoodEntry)
admin.site.register(NotificationPreference)
admin.site.register(Bookmark)
