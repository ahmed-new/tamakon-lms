from datetime import date
from calendar import monthrange
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.db.models import F
from commerce.models import EnrollmentInstallment ,Enrollment,UserActivity

from datetime import timedelta
from django.db.models import Q, Exists, OuterRef ,Prefetch

from .emails import send_absence_email  # هنكتبه تحت

DEFAULT_FROM = getattr(settings, "DEFAULT_FROM_EMAIL", "ahmeddev538@gmail.com")
SALARY_DAY   = 28   # يوم القبض
REMINDER_DAY = 26   # يوم الإرسال

def _month_first_last(d: date):
    first = date(d.year, d.month, 1)
    last  = date(d.year, d.month, monthrange(d.year, d.month)[1])
    return first, last

def _send_salary_day_reminder(user, enrollment, inst):
    ctx = {
        "user": user,
        "enrollment": enrollment,
        "inst": inst,
        "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000"),
    }
    subject = f"تذكير القسط لدورة {enrollment.course.title}"
    html = render_to_string("emails/installment_payroll_reminder.html", ctx)
    msg = EmailMultiAlternatives(subject, html, DEFAULT_FROM, [user.email])
    msg.attach_alternative(html, "text/html")
    msg.send()



@shared_task
def send_salary_day_reminders(force: bool = False):
    """
    يرسل يوم 26 من كل شهر:
      - لكل اشتراك لديه قسط حالته DUE أو OVERDUE
      - وتاريخ استحقاقه في الشهر الحالي وحتى يوم 28 (شاملًا).
    يرسل رسالة واحدة فقط لكل اشتراك (أقرب قسط).
    """
    today = timezone.localdate()

    if not force and today.day != REMINDER_DAY:
        return "Not the 26th — skipped."

    month_start, _ = _month_first_last(today)
    salary_cutoff = date(today.year, today.month, SALARY_DAY)

    Status = EnrollmentInstallment.Status
    statuses = [Status.DUE, Status.OVERDUE]

    qs = (EnrollmentInstallment.objects
          .select_related("enrollment", "enrollment__user", "enrollment__course")
          .filter(status__in=statuses,
                  due_date__isnull=False,
                  due_date__gte=month_start,
                  due_date__lte=salary_cutoff)
          .order_by("enrollment_id", "due_date"))

    sent = 0
    seen_enrollments = set()

    for inst in qs.iterator():
        enr = inst.enrollment
        if not enr or enr.id in seen_enrollments:
            continue
        user = getattr(enr, "user", None)
        if not user or not user.email:
            continue

        try:
            _send_salary_day_reminder(user, enr, inst)
            sent += 1
            seen_enrollments.add(enr.id)  # أبعت عن أقرب قسط فقط لكل اشتراك
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Failed salary reminder for enrollment %s", enr.id
            )

    return f"Sent {sent} salary-day reminders for {month_start} → {salary_cutoff}."




@shared_task
def send_two_weeks_absence_alerts():
    now = timezone.now()
    cutoff = now - timedelta(days=14)

    # الطلاب اللي عندهم Enrollment نشط
    active_enrollment = Enrollment.objects.filter(
        user=OuterRef("user"),
        is_active=True,  # عدّل الشرط حسب مشروعك
    )

    qs = (UserActivity.objects
          .filter(last_seen__lte=cutoff)              # غياب ≥ 14 يوم
          .filter(Q(last_absence_email_at__isnull=True) | Q(last_absence_email_at__lt=F("last_seen")))
          .annotate(has_active=Exists(active_enrollment))
          .filter(has_active=True)
          .select_related("user"))

    count = 0
    for act in qs.iterator():
        # ابعت الإيميل
        send_absence_email(act.user, last_seen=act.last_seen)
        # سجّل منع التكرار
        act.last_absence_email_at = now
        act.save(update_fields=["last_absence_email_at"])
        count += 1
    return count



#mark the due installments as overdue once we passed due date 

@shared_task
def mark_overdue_installments():
    today = timezone.localdate()

    qs = EnrollmentInstallment.objects.filter(
        Q(status__in=[EnrollmentInstallment.Status.DUE, EnrollmentInstallment.Status.OVERDUE]),
        Q(paid_at__isnull=True),
        Q(due_date__isnull=False),
        Q(due_date__lt=today),
        # الأهم: استبعاد الاشتراكات المجمّدة حاليًا
        ~Q(enrollment__status=Enrollment.Status.FROZEN),
    )

    return qs.update(status=EnrollmentInstallment.Status.OVERDUE)



#   تعليق الاشتراكات التى تحتوى على اقساط متاخرة اكتر من 60 يوم بعد خصم فترة التجميد
@shared_task
def suspend_enrollments_with_overdue_60d():
    """
    يعلّق الاشتراكات التي لديها أي قسط غير مدفوع فات ميعاده، وكان
    'التأخير الفعلي' ≥ 60 يوم بعد خصم الأيام المتداخلة مع فترة التجميد الحالية.

    التأخير الفعلي = (today - due_date) - overlap_with_current_freeze
    """
    today = timezone.localdate()

    # Subquery: وجود أي قسط غير مدفوع وميعاده فات (لتحديد المرشّحين فقط)
    base_installments = EnrollmentInstallment.objects.filter(
        enrollment=OuterRef("pk"),
        paid_at__isnull=True,
        due_date__isnull=False,
        due_date__lt=today,
    )

    # Prefetch للأقساط المطلوبة للحساب (تفادي N+1)
    due_qs = (EnrollmentInstallment.objects
              .filter(paid_at__isnull=True, due_date__lt=today)
              .only("id", "due_date"))

    candidates = (Enrollment.objects
                  .exclude(status=Enrollment.Status.CANCELLED)
                  .annotate(has_due=Exists(base_installments))
                  .filter(has_due=True)
                  .select_related("user", "course")
                  .prefetch_related(Prefetch("installments", queryset=due_qs, to_attr="due_installments")))

    changed = 0
    for en in candidates.iterator():
        insts = getattr(en, "due_installments", [])
        if not insts:
            continue

        should_suspend = False

        # بيانات التجميد الحالي (لو موجودة)
        fs = getattr(en, "frozen_started_at", None)
        fu = getattr(en, "frozen_until", None)
        # لا نحسب ما بعد اليوم
        if fu:
            fu = min(fu, today)

        for inst in insts:
            days_overdue = (today - inst.due_date).days  # فرق الأيام من الاستحقاق حتى اليوم

            # خصم التداخل مع فترة التجميد الحالية فقط
            overlap_days = 0
            if en.status == Enrollment.Status.FROZEN and fs and fu and fs <= fu:
                # التداخل بين [due_date .. today] و [fs .. fu]
                start = max(inst.due_date, fs)
                end = fu
                if end > start:
                    overlap_days = (end - start).days

            effective = max(0, days_overdue - overlap_days)

            if effective >= 60:
                should_suspend = True
                break

        if should_suspend and en.status != Enrollment.Status.SUSPENDED:
            en.status = Enrollment.Status.SUSPENDED
            en.save(update_fields=["status"])
            changed += 1

    return changed



# اعادة تفعيل الاشتراكات المعلقة التى لم تعد تحتوى على اقساط متاخر اكتر من 60 يوم

@shared_task
def reactivate_when_no_overdue_60d():
    today = timezone.localdate()
    cutoff = today - timedelta(days=60)

    still_overdue_qs = EnrollmentInstallment.objects.filter(
        enrollment=OuterRef("pk"),
        status=EnrollmentInstallment.Status.OVERDUE,
        paid_at__isnull=True,
        due_date__lt=cutoff,
    )

    candidates = (Enrollment.objects
                  .filter(status=Enrollment.Status.SUSPENDED)
                  .annotate(still_overdue=Exists(still_overdue_qs))
                  .filter(still_overdue=False))

    changed = 0
    for en in candidates.iterator():
        en.status = Enrollment.Status.ACTIVE
        en.save(update_fields=["status"])
        changed += 1
    return changed






@shared_task
def auto_unfreeze_enrollments():
    today = timezone.localdate()
    cutoff = today - timedelta(days=60)

    # اشتراكات مجمّدة وجاهزة لفكّها (انتهت مدة التجميد)
    candidates = Enrollment.objects.filter(
        status=Enrollment.Status.FROZEN,
        frozen_until__isnull=False,
        frozen_until__lte=today,
    )

    # هل عليه أقساط متأخرة 60+ يوم؟
    overdue60 = EnrollmentInstallment.objects.filter(
        enrollment=OuterRef("pk"),
        status=EnrollmentInstallment.Status.OVERDUE,
        paid_at__isnull=True,
        due_date__lt=cutoff,
    )

    changed = 0
    for en in candidates.annotate(has_overdue60=Exists(overdue60)).iterator():
        # فضّي حقول فترة التجميد الحالية
        en.frozen_started_at = None
        en.frozen_until = None

        if en.has_overdue60:
            # يتحوّل لتعليق بدل التفعيل
            if en.status != Enrollment.Status.SUSPENDED:
                en.status = Enrollment.Status.SUSPENDED
                en.save(update_fields=["status", "frozen_started_at", "frozen_until", "updated_at"])
                # اختياري: وسم الأقساط المتأخرة فورًا
                en.installments.filter(paid_at__isnull=True, due_date__lt=today) \
                    .exclude(status=EnrollmentInstallment.Status.OVERDUE) \
                    .update(status=EnrollmentInstallment.Status.OVERDUE)
                changed += 1
        else:
            # يرجع نشط
            if en.status != Enrollment.Status.ACTIVE:
                en.status = Enrollment.Status.ACTIVE
                en.save(update_fields=["status", "frozen_started_at", "frozen_until", "updated_at"])
                changed += 1
            else:
                # حتى لو الحالة بالفعل ACTIVE، نظّف حقول التجميد
                en.save(update_fields=["frozen_started_at", "frozen_until", "updated_at"])
    return changed