# commerce/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from .models import Enrollment
from .forms import FreezeEnrollmentForm

@login_required
def freeze_enrollment(request, pk):
    enr = get_object_or_404(Enrollment, pk=pk, user=request.user)

    # مسموح التجميد فقط لو الاشتراك نشط
    if enr.status != Enrollment.Status.ACTIVE:
        messages.error(request, "لا يمكن تجميد هذا الاشتراك حالياً.")
        return redirect("learning:my_courses")

    if request.method != "POST":
        messages.error(request, "طلب غير صحيح.")
        return redirect("learning:my_courses")

    form = FreezeEnrollmentForm(request.POST)
    if not form.is_valid():
        messages.error(request, "من فضلك أدخل بيانات صحيحة.")
        return redirect("learning:my_courses")

    days = form.cleaned_data["days"]
    password = form.cleaned_data["password"]

    # تحقق كلمة المرور
    if not request.user.check_password(password):
        messages.error(request, "كلمة المرور غير صحيحة.")
        return redirect("learning:my_courses")

    # تحقق الحد الأقصى 90 يوم إجمالي
    remaining = 90 - (enr.freeze_days_used or 0)
    if remaining <= 0:
        messages.error(request, "لقد استهلكت الحد الأقصى لأيام التجميد (90 يوم).")
        return redirect("learning:my_courses")

    if days > remaining:
        messages.error(request, f"الحد المتبقي لك هو {remaining} يوم فقط.")
        return redirect("learning:my_courses")

    # تنفيذ التجميد
    today = timezone.localdate()
    enr.status = Enrollment.Status.FROZEN
    enr.freeze_days_used = (enr.freeze_days_used or 0) + days
    enr.frozen_started_at = today
    enr.frozen_until = today + timedelta(days=days)  # هيتفك تلقائيًا بعد آخر يوم
    # اختياري: تدوين ملاحظة
    note = f"تجميد ذاتي لمدة {days} يوم بتاريخ {timezone.localdate()}."
    if enr.notes:
        enr.notes = f"{enr.notes}\n{note}"
    else:
        enr.notes = note
    enr.save(update_fields=["status", "freeze_days_used", "frozen_started_at", "frozen_until", "notes", "updated_at"])
    messages.success(request, f"تم تجميد الاشتراك لمدة {days} يوم. إجمالي التجميدات المستخدمة: {enr.freeze_days_used}/90")
    return redirect("learning:my_courses")


@login_required
def unfreeze_enrollment(request, pk):
    enr = get_object_or_404(Enrollment, pk=pk, user=request.user)

    if request.method != "POST":
        messages.error(request, "طلب غير صحيح.")
        return redirect("learning:my_courses")

    # مسموح فك التجميد فقط لو الحالة الحالية مجمّد
    if enr.status != Enrollment.Status.FROZEN:
        messages.error(request, "هذا الاشتراك غير مجمّد.")
        return redirect("learning:my_courses")

    # لو كان معلق بسبب أقساط متأخرة وعايز تمنع فكّه تلقائيًا، تقدر تضيف شرط هنا.
    enr.status = Enrollment.Status.ACTIVE
    enr.frozen_started_at = None
    enr.frozen_until = None
    note = f"إلغاء التجميد ذاتيًا بتاريخ {timezone.localdate()}."
    if enr.notes:
        enr.notes = f"{enr.notes}\n{note}"
    else:
        enr.notes = note
    enr.save(update_fields=["status", "frozen_started_at", "frozen_until", "notes", "updated_at"])

    messages.success(request, "تم إلغاء التجميد وإعادة تفعيل الاشتراك.")
    return redirect("learning:my_courses")
