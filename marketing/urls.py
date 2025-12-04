# marketing/urls.py
from django.urls import path
from . import views

app_name = "marketing"

urlpatterns = [
    path("visitors/bulk-email/", views.bulk_email_compose, name="bulk_email_compose"),
    path("visitors/bulk-email/send/<int:campaign_id>/", views.bulk_email_send, name="bulk_email_send"),
    path("visitors/unsubscribe/", views.visitor_unsubscribe, name="visitor_unsubscribe"),
]
