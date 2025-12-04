# marketing/models.py
from django.db import models
from django.conf import settings

class VisitorEmailCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        SENDING = "sending", "جارٍ الإرسال"
        DONE = "done", "مكتمل"

    subject = models.CharField(max_length=200, verbose_name="العنوان (Subject)")
    body_html = models.TextField(verbose_name="HTML المحتوى")
    body_text = models.TextField(blank=True, null=True, verbose_name="النص العادي (اختياري)")
    filter_json = models.JSONField(default=dict, verbose_name="فلاتر الاستهداف")
    total_targets = models.PositiveIntegerField(default=0, verbose_name="عدد المستهدفين")
    sent_count = models.PositiveIntegerField(default=0, verbose_name="تم إرساله")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.get_status_display()}] {self.subject} ({self.sent_count}/{self.total_targets})"


class VisitorEmailLog(models.Model):
    campaign = models.ForeignKey(VisitorEmailCampaign, on_delete=models.CASCADE, related_name="logs")
    visitor = models.ForeignKey("commerce.Visitor", on_delete=models.CASCADE)
    to_email = models.EmailField()
    sent_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=10, default="sent")  # sent/failed
    error = models.TextField(blank=True, null=True)
    message_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.to_email} — {self.campaign.subject}"
