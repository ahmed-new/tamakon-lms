# commerce/signals.py
from decimal import Decimal
from datetime import date
from django.db.models.signals import  pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from calendar import monthrange
from django.db import transaction
from .emails import send_enrollment_email ,send_enrollment_suspended_email , send_enrollment_frozen_email
from .models import Enrollment, EnrollmentInstallment, EnrollmentPartAccess ,Payment,UserActivity
from .utils import ensure_part_access_plan  # ← جديد
import logging



logger = logging.getLogger(__name__)




def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = monthrange(y, m)[1]
    return date(y, m, min(d.day, last_day))

@receiver(post_save, sender=Enrollment)
def generate_installments_on_enrollment(sender, instance: Enrollment, created, **kwargs):
    if not created:
        return
    
    course = instance.course
    # ✅ فقط لو الدورة تسمح بالأقساط وعددها > 1
    if not (course.allow_installments and course.installments_count and course.installments_count > 1):
        # لا ننشئ أي قسط. (الدفع الكامل مرّة واحدة خارج جدول الأقساط)
        return
    
    
    if not instance.installments.exists():
        course = instance.course
        total = course.price or Decimal("0.00")
        count = course.installments_count if course.allow_installments else 1
        if count < 1:
            count = 1

        per = (total / count).quantize(Decimal("0.01"))
        amounts = [per] * count
        diff = total - sum(amounts)
        if diff != 0:
            amounts[-1] = (amounts[-1] + diff).quantize(Decimal("0.01"))

        base = instance.started_at or timezone.now().date()
        objs = []
        for i in range(count):
            due = _add_months(base, i)
            objs.append(EnrollmentInstallment(
                enrollment=instance, step=i+1, amount=amounts[i], due_date=due
            ))
        EnrollmentInstallment.objects.bulk_create(objs)

    # ← هنا المهم: توليد خطة فتح الأجزاء تلقائيًا لو الدورة أقساط
    ensure_part_access_plan(instance, overwrite=False)

@receiver(post_save, sender=EnrollmentInstallment)
def unlock_parts_when_paid(sender, instance: EnrollmentInstallment, created, **kwargs):
    if instance.status != EnrollmentInstallment.Status.PAID:
        return
    enr = instance.enrollment
    paid_count = enr.installments.filter(status=EnrollmentInstallment.Status.PAID).count()
    now = timezone.now()
    enr.part_access.filter(unlock_step__lte=paid_count, unlocked_at__isnull=True).update(unlocked_at=now)












# signals for sending emails when paying manual 
@receiver(pre_save, sender=Payment)
def _payment_track_old_status(sender, instance: Payment, **kwargs):
    """نحتفظ بالحالة القديمة قبل الحفظ علشان نعرف حصل انتقال لـ CAPTURED ولا لأ."""
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            instance._old_status = old.status
        except sender.DoesNotExist:
            instance._old_status = None
    else:
        instance._old_status = None


@receiver(post_save, sender=Payment)
def _payment_bank_captured_apply_and_email(sender, instance: Payment, created, **kwargs):
    """
    يعمل فقط مع الدفعات اليدوية (BANK_TRANSFER) عند الانتقال فعليًا إلى CAPTURED:
      - لو محدد installment: نعلّمه PAID.
      - لو مش محدد installment لكن فيه step: نجيب القسط بالـ step ونعلّمه PAID.
      - لو لا ده ولا ده: نعتبرها دفع كامل ⇒ نعلّم كل الأقساط PAID (إن وجدت).
      - نضمن وجود/تهيئة خطة فتح الأجزاء.
      - نرسل إيميل تأكيد الاشتراك/السداد باستخدام send_enrollment_email.
    """
    # اشتغل فقط مع التحويل البنكي
    if instance.method != Payment.Method.BANK_TRANSFER:
        return

    # لازم يكون CAPTURED الآن ولم يكن CAPTURED قبل كده
    if instance.status != Payment.Status.CAPTURED:
        return
    if getattr(instance, "_old_status", None) == Payment.Status.CAPTURED:
        return  # تجنب التكرار

    def _apply():
        # أعد جلب الـ payment بعلاقاته
        payment = Payment.objects.select_related("user", "course", "enrollment", "installment").get(pk=instance.pk)
        user = payment.user
        course = payment.course

        # 1) حدّد/استنتج الاشتراك
        enr = payment.enrollment
        if not enr:
            # لو الإدمن ما ربطش Enrollment، نحاول نلاقي اشتراك قائم لنفس المستخدم/الدورة
            enr = (Enrollment.objects
                   .filter(user=user, course=course)
                   .order_by("-created_at").first())
            if enr and payment.enrollment is None:
                Payment.objects.filter(pk=payment.pk).update(enrollment=enr)

        if not enr:
            # مفيش اشتراك—السيناريو المتوقع إن الإدمن يكون أنشأ اشتراك قبل الدفع
            logger.warning("Bank payment #%s captured without an enrollment. Link a valid enrollment.", payment.pk)
            return

        # نضمن وجود خطة فتح الأجزاء
        ensure_part_access_plan(enr, overwrite=False)

        # 2) طبّق السداد على قسط محدد (إن وُجد)
        inst = payment.installment
        if not inst and payment.step:
            inst = enr.installments.filter(step=payment.step).first()

        if inst:
            if inst.status != EnrollmentInstallment.Status.PAID:
                inst.status = EnrollmentInstallment.Status.PAID
                inst.paid_at = timezone.now()
                inst.save(update_fields=["status", "paid_at"])
        else:
            # 3) دفع كامل (لا قسط محدد): علّم جميع الأقساط PAID (إن وُجدت أقساط)
            for i in enr.installments.all():
                if i.status != EnrollmentInstallment.Status.PAID:
                    i.status = EnrollmentInstallment.Status.PAID
                    i.paid_at = timezone.now()
                    i.save(update_fields=["status", "paid_at"])

        # 4) إرسال إيميل التأكيد (نفس الدالة المستخدمة مع PayPal)
        try:
            # لو دالتك تعتمد على SITE_URL، خليها تقراه من settings جوّا الدالة.
            send_enrollment_email(user, enr, payment, site_url=None)
        except Exception as e:
            logger.exception("Failed to send bank-transfer enrollment email for payment #%s: %s", payment.pk, e)

    # نطبّق بعد الـ commit لتجنّب مشاكل السباق
    transaction.on_commit(_apply)





from django.conf import settings

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_activity(sender, instance, created, **kwargs):
    if created:
        UserActivity.objects.get_or_create(user=instance)


from datetime import timedelta
# after paying an installment , check if its enrollment is suspended even thou no longer overdue installemnt over 60 days
@receiver(post_save, sender=EnrollmentInstallment)
def maybe_unsuspend_on_payment(sender, instance: EnrollmentInstallment, created, **kwargs):
    # نتحرك فقط لو القسط بقى مدفوع فعلاً
    if not instance.paid_at:
        return

    en = instance.enrollment
    if en.status != Enrollment.Status.SUSPENDED:
        return

    cutoff = timezone.localdate() - timedelta(days=60)
    still_overdue = en.installments.filter(
        status=EnrollmentInstallment.Status.OVERDUE,
        paid_at__isnull=True,
        due_date__lt=cutoff,
    ).exists()

    if not still_overdue:
        en.status = Enrollment.Status.ACTIVE
        en.save(update_fields=["status"])







# signlas dor sending emails once it is frozen or susbended


@receiver(pre_save, sender=Enrollment)
def _enrollment_capture_old_status(sender, instance: Enrollment, **kwargs):
    if instance.pk:
        try:
            old = Enrollment.objects.get(pk=instance.pk)
            instance.__old_status = old.status
        except Enrollment.DoesNotExist:
            instance.__old_status = None
    else:
        instance.__old_status = None





@receiver(post_save, sender=Enrollment)
def _enrollment_notify_on_status_change(sender, instance: Enrollment, created, **kwargs):
    if created:
        return

    old = getattr(instance, "__old_status", None)
    new = instance.status

    # اطبع اللوج علشان تتأكد إن السيجنال اشتغل
    print("ENROLLMENT STATUS CHANGED:", old, "→", new, instance.pk)

    if not old or old == new:
        return

    if new == Enrollment.Status.SUSPENDED:
        try:
            send_enrollment_suspended_email(instance)
        except Exception as e:
            print("Error sending suspended email:", e)

    elif new == Enrollment.Status.FROZEN:
        try:
            send_enrollment_frozen_email(instance)
        except Exception as e:
            print("Error sending frozen email:", e)
