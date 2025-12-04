# users/signals.py
import uuid
from django.contrib.auth.signals import user_logged_in
from django.contrib.auth import logout
from django.dispatch import receiver
from django.contrib import messages

from .models import UserDevice, User
from users.middleware import DEVICE_COOKIE_NAME  # لازم يكون نفس الاسم في الميدلوير


def _read_device_id_from_cookie(request):
    raw = request.COOKIES.get(DEVICE_COOKIE_NAME)
    if not raw:
        return None
    try:
        return str(uuid.UUID(raw))
    except Exception:
        return None


@receiver(user_logged_in)
def enforce_two_devices_limit(sender, request, user: User, **kwargs):
    # نطبق الحد على الطلاب فقط
    if getattr(user, "role", None) != getattr(User.Roles, "STUDENT", "student"):
        return

    device_id = _read_device_id_from_cookie(request)
    if not device_id:
        messages.error(request, "تعذّر التحقق من الجهاز. برجاء المحاولة من نفس المتصفح.")
        logout(request)
        return

    # لو الجهاز مسجّل قبل كده لنفس المستخدم: عدّي وحدّث آخر ظهور
    existing = UserDevice.objects.filter(user=user, device_id=device_id).first()
    if existing:
        existing.save(update_fields=["last_seen_at"])
        return

    # عدد الأجهزة المسجّلة بالفعل
    count = UserDevice.objects.filter(user=user, allowed=True).count()
    if count >= 2:
        logout(request)
        messages.error(
            request,
            "لقد وصلت للحد الأقصى للأجهزة المسموح بها (2). "
            "تواصل مع الدعم لإزالة جهاز مسجّل إذا كنت قد غيّرت جهازك."
        )
        return

    # سجّل الجهاز الحالي
    ua = request.META.get("HTTP_USER_AGENT", "") or None
    ip = request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR")
    if ip and "," in str(ip):
        ip = ip.split(",")[0].strip()

    UserDevice.objects.create(
        user=user,
        device_id=device_id,
        user_agent=ua,
        ip_address=ip or None,
        allowed=True,
    )
