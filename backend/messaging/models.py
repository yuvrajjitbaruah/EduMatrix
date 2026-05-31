from django.db import models
from django.conf import settings


class Message(models.Model):
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    subject = models.CharField(max_length=200)
    body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    attachment = models.FileField(upload_to='message_attachments/', blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, related_name='thread_replies', blank=True, null=True)

    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['receiver', 'is_read', 'sent_at'], name='msg_receiver_read_sent_idx'),
            models.Index(fields=['sender', 'sent_at'], name='msg_sender_sent_idx'),
            models.Index(fields=['parent', 'sent_at'], name='msg_parent_sent_idx'),
        ]

    def __str__(self):
        return f"{self.sender.username} → {self.receiver.username}: {self.subject}"
