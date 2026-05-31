from django.urls import path
from . import views

urlpatterns = [
    path('', views.quiz_list, name='quiz_list'),
    path('take/<int:quiz_id>/', views.take_quiz, name='take_quiz'),
    path('submit/<int:quiz_id>/', views.submit_quiz, name='submit_quiz'),
    path('create/', views.create_quiz, name='create_quiz'),
]
