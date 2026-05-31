from django.db import models
from django.conf import settings
from academics.models import CourseClass


class ForumThread(models.Model):
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_threads')
    course_class = models.ForeignKey(CourseClass, on_delete=models.CASCADE, related_name='forum_threads', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_pinned = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return self.title

    @property
    def reply_count(self):
        return self.replies.count()


class ForumReply(models.Model):
    thread = models.ForeignKey(ForumThread, on_delete=models.CASCADE, related_name='replies')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_replies')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"Reply by {self.author.username} on {self.thread.title}"


class ForumReaction(models.Model):
    REACTION_TYPES = (
        ('like', '👍 Like'),
        ('helpful', '💡 Helpful'),
        ('insightful', '🧠 Insightful'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='forum_reactions')
    thread = models.ForeignKey(ForumThread, on_delete=models.CASCADE, related_name='reactions', blank=True, null=True)
    reply = models.ForeignKey(ForumReply, on_delete=models.CASCADE, related_name='reactions', blank=True, null=True)
    reaction_type = models.CharField(max_length=15, choices=REACTION_TYPES, default='like')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'thread', 'reply', 'reaction_type')

    def __str__(self):
        target = self.thread.title if self.thread else f"reply #{self.reply_id}"
        return f"{self.user.username} {self.get_reaction_type_display()} on {target}"
