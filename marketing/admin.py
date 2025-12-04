# marketing/admin.py
from django.contrib import admin
from .models import VisitorEmailCampaign, VisitorEmailLog

@admin.register(VisitorEmailCampaign)
class VisitorEmailCampaignAdmin(admin.ModelAdmin):
    list_display = ("id", "subject", "status", "total_targets", "sent_count", "created_at")
    readonly_fields = ("total_targets", "sent_count", "status", "created_by", "created_at")

@admin.register(VisitorEmailLog)
class VisitorEmailLogAdmin(admin.ModelAdmin):
    list_display = ("id", "campaign", "to_email", "status", "sent_at")
    readonly_fields = ("campaign", "visitor", "to_email", "status", "error", "sent_at", "message_id")
