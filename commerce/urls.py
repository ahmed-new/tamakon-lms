from django.urls import path
from . import views_payments 
from .views import freeze_enrollment ,unfreeze_enrollment

app_name = "commerce"

urlpatterns = [
    path("checkout/<slug:slug>/", views_payments.checkout_view, name="checkout"),
    path("api/paypal/create/<slug:slug>/", views_payments.paypal_create_order_view, name="paypal_create"),
    path("paypal/capture/", views_payments.paypal_capture_view, name="paypal_capture"),
    path("api/paypal/quote/<slug:slug>/", views_payments.paypal_quote_view, name="paypal_quote"),
    path("enrollments/<int:pk>/freeze/", freeze_enrollment, name="freeze_enrollment"),
    path("enrollments/<int:pk>/unfreeze/", unfreeze_enrollment, name="unfreeze_enrollment"),
]
