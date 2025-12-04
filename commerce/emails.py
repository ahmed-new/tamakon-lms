# commerce/emails.py
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from learning.utils import course_progress_percent

DEFAULT_FROM = getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com")

def send_enrollment_email(user, enrollment, payment, site_url=None):
    """
    إيميل تأكيد الاشتراك + تفاصيل:
    - نوع الاشتراك (من payment.mode)
    - نسبة التقدّم
    - جدول الأقساط (لو موجود)
    - القسط القادم/انتهت الأقساط
    """
    course = enrollment.course

    # نسبة التقدم
    try:
        progress = course_progress_percent(user, course)
    except Exception:
        progress = 0.0
    progress_int = int(round(float(progress)))

    # نوع الاشتراك من الـ Payment
    pay_mode_str = str(payment.mode).lower() if payment and payment.mode else ""

    is_installment = (pay_mode_str != "full")
    mode_label = "تقسيط" if is_installment else "دفع كامل"

    # جدول الأقساط (سواء الدفع كامل أو تقسيط — لو عندك أقساط بتظهر في الإيميل)
    installments_data = []
    total_steps = paid_count = remaining_count = 0
    next_due = None

    qs = enrollment.installments.order_by("step")
    if qs.exists():
        for inst in qs:
            status_str = str(getattr(inst, "status", "")).lower()
            row = {
                "step": inst.step,
                "amount": getattr(inst, "amount", None),
                "currency": getattr(inst, "currency", None) or payment.currency or "USD",
                "status": status_str,  # "paid" / "due" ... (هنعرِضها في القالب)
                "due_date": getattr(inst, "due_date", None),
                "paid_at": getattr(inst, "paid_at", None),
            }
            installments_data.append(row)

        total_steps = len(installments_data)
        paid_count = sum(1 for r in installments_data if r["status"] == "paid")
        remaining_count = sum(1 for r in installments_data if r["status"] == "due")
        next_due = next((r for r in installments_data if r["status"] == "due"), None)

    ctx = {
        "user": user,
        "enrollment": enrollment,
        "payment": payment,
        "course": course,
        "site_url": site_url or "http://127.0.0.1:8000",

        "mode_label": mode_label,
        "progress": progress_int,

        "installments": installments_data,
        "total_steps": total_steps,
        "paid_count": paid_count,
        "remaining_count": remaining_count,
        "next_due": next_due,
        "all_installments_paid": (total_steps > 0 and remaining_count == 0),
        "is_installment": is_installment,
    }

    subject = f"تأكيد اشتراكك في دورة {course.title}"
    html = render_to_string("emails/enrollment_success.html", ctx)

    msg = EmailMultiAlternatives(subject, html, DEFAULT_FROM, [user.email])
    msg.attach_alternative(html, "text/html")
    msg.send()





def send_absence_email(user, last_seen):

    subject = "! رجوعك هيكمل رحلتك التعليمية 🚀افتقدناك"
    ctx = {
        "user": user,
        "last_seen": last_seen,
        "site_name": getattr(settings, "SITE_NAME", "منصتك التعليمية"),
        "dashboard_url": getattr(settings, "SITE_URL", "") + "/dashboard/",
    }
    html = render_to_string("emails/absence_14_days.html", ctx)
    txt = render_to_string("emails/absence_14_days.txt", ctx)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=txt,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "ahmeddev538@gmail.com"),
        to=[user.email],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()




# emails for suspending and frozen enrollment 
from django.urls import reverse


def _abs_url(path: str) -> str:
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    return f"{base}{path}"

def _send_email(subject, to, template_base, ctx):
    html = render_to_string(f"emails/{template_base}.html", ctx)
    txt  = render_to_string(f"emails/{template_base}.txt", ctx)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=txt,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "ahmeddev538@gmail.com"),
        to=[to],
    )
    msg.attach_alternative(html, "text/html")
    msg.send()

def send_enrollment_suspended_email(enrollment):
    course_path = reverse("learning:course_detail", kwargs={"slug": enrollment.course.slug})
    ctx = {
        "user": enrollment.user,
        "course": enrollment.course,
        "course_url": _abs_url(course_path),
        "site_name": getattr(settings, "SITE_NAME", "منصتك التعليمية"),
    }
    _send_email(
        subject="تم تعليق اشتراكك مؤقتًا بسبب تأخر السداد",
        to=enrollment.user.email,
        template_base="enrollment_suspended",
        ctx=ctx,
    )

def send_enrollment_frozen_email(enrollment):
    my_courses_path = reverse("learning:my_courses")

    # حضّر تواريخ ومدة التجميد إن وُجدت
    fs = getattr(enrollment, "frozen_started_at", None)
    fu = getattr(enrollment, "frozen_until", None)

    frozen_days = None
    if fs and fu:
        # عدد الأيام المحسوبة كفرق تواريخ (دون تضمين اليوم الأخير كساعات)
        frozen_days = (fu - fs).days
        if frozen_days < 0:
            frozen_days = 0  # احترازى لو التواريخ معكوسة بالخطأ

    ctx = {
        "user": enrollment.user,
        "course": enrollment.course,
        "my_courses_url": _abs_url(my_courses_path),
        "site_name": getattr(settings, "SITE_NAME", "تمكن"),

        # بيانات إضافية
        "frozen_started_at": fs,
        "frozen_until": fu,
        "frozen_days": frozen_days,
    }

    _send_email(
        subject="تم تجميد اشتراكك مؤقتًا",
        to=enrollment.user.email,
        template_base="enrollment_frozen",
        ctx=ctx,
    )