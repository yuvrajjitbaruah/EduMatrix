from django.contrib import admin
from .models import ForumThread, ForumReply

admin.site.register(ForumThread)
admin.site.register(ForumReply)
