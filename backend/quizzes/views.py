from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from dashboard.retired import retired_feature_json, retired_feature_redirect
from .models import Quiz, Question, Choice, QuizAttempt, StudentAnswer
from academics.models import CourseClass
import json

@login_required
def quiz_list(request):
    return retired_feature_redirect(
        request,
        'Legacy quiz module',
        redirect_to='classes',
        extra_message='Use AI Quiz Gen inside Classroom instead.',
    )

@login_required
def take_quiz(request, quiz_id):
    return retired_feature_redirect(
        request,
        'Legacy quiz module',
        redirect_to='classes',
        extra_message='Use AI Quiz Gen inside Classroom instead.',
    )

@login_required
def submit_quiz(request, quiz_id):
    return retired_feature_json('Legacy quiz module', 'Use AI Quiz Gen inside Classroom instead.')

@login_required
def create_quiz(request):
    return retired_feature_redirect(
        request,
        'Legacy quiz module',
        redirect_to='classes',
        extra_message='Use AI Quiz Gen inside Classroom instead.',
    )
