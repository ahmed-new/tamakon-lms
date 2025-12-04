# commerce/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Visitor(models.Model):
    email = models.EmailField(unique=True, verbose_name="البريد الإلكتروني")
    name = models.CharField(max_length=150, blank=True, null=True, verbose_name="الاسم (اختياري)")
    consent = models.BooleanField(default=True, verbose_name="موافقة على التواصل")
    source = models.CharField(max_length=150, blank=True, null=True, verbose_name="المصدر (مثلاً: صفحة درس)")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإضافة")
    last_seen_at = models.DateTimeField(blank=True, null=True, verbose_name="آخر ظهور")

    class Meta:
        verbose_name = "زائر"
        verbose_name_plural = "الزوّار"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email











class Enrollment(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        FROZEN = "frozen", "مجمّد"
        SUSPENDED = "suspended", "معلّق"
        CANCELLED = "cancelled", "ملغى"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="المستخدم",
    )
    course = models.ForeignKey(
        "learning.Course",
        on_delete=models.CASCADE,
        related_name="enrollments",
        verbose_name="الدورة",
    )

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="الحالة",
    )
    started_at = models.DateField(default=timezone.now, verbose_name="تاريخ بدء الاشتراك")
    expires_at = models.DateField( verbose_name="تاريخ الانتهاء",null=True, blank=True)
    frozen_started_at = models.DateField(null=True, blank=True)  # بداية فترة التجميد الحالية
    frozen_until = models.DateField(null=True, blank=True)
    freeze_days_used = models.PositiveIntegerField(default=0, verbose_name="أيام التجميد المستهلكة (حد 90)")

    notes = models.TextField(blank=True, null=True, verbose_name="ملاحظات")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "اشتراك"
        verbose_name_plural = "الاشتراكات"
        ordering = ["-created_at"]
        unique_together = (("user", "course"),)

    def __str__(self):
        return f"{self.user} → {self.course} ({self.get_status_display()})"

    def is_active_for_access(self) -> bool:
        if self.status != self.Status.ACTIVE:
            return False
        if self.expires_at and self.expires_at < timezone.now().date():
            return False
        return True

    def save(self, *args, **kwargs):
        if not self.expires_at:  # لو لسه مش متحدد
            self.expires_at = self.started_at + timedelta(days=365)
        super().save(*args, **kwargs)


from decimal import Decimal

class EnrollmentInstallment(models.Model):
    class Status(models.TextChoices):
        DUE     = "due", "مستحق"
        PAID    = "paid", "مدفوع"
        OVERDUE = "overdue", "متأخر"

    enrollment = models.ForeignKey("commerce.Enrollment", on_delete=models.CASCADE,
                                   related_name="installments", verbose_name="الاشتراك")
    step = models.PositiveSmallIntegerField(verbose_name="رقم القسط")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    due_date = models.DateField(blank=True, null=True, verbose_name="تاريخ الاستحقاق")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DUE, verbose_name="الحالة")
    paid_at = models.DateTimeField(blank=True, null=True, verbose_name="تاريخ السداد")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2,
                                          default=Decimal("0.00"), verbose_name="خصم مطبّق")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "قسط اشتراك"
        verbose_name_plural = "أقساط الاشتراك"
        ordering = ["step"]
        unique_together = (("enrollment", "step"),)

    def __str__(self):
        return f"{self.enrollment} — قسط {self.step} ({self.get_status_display()})"


class EnrollmentPartAccess(models.Model):
    """
    أي جزء يتفتح عند دفع قسط معيّن لهذا الاشتراك.
    - لو لا توجد سجلات لهذا الاشتراك => يعتبر الوصول كامل للدورة.
    """
    enrollment = models.ForeignKey("commerce.Enrollment", on_delete=models.CASCADE,
                                   related_name="part_access", verbose_name="الاشتراك")
    part = models.ForeignKey("learning.CoursePart", on_delete=models.CASCADE,
                             related_name="enrollment_access", verbose_name="الجزء")
    unlock_step = models.PositiveSmallIntegerField(verbose_name="يتاح عند القسط رقم")
    unlocked_at = models.DateTimeField(blank=True, null=True, verbose_name="تم الفتح في")

    class Meta:
        verbose_name = "سماحية جزء ضمن اشتراك"
        verbose_name_plural = "سماحيات الأجزاء ضمن اشتراك"
        unique_together = (("enrollment", "part"),)
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "unlock_step"], name="uniq_enrollment_unlock_step"),
        ]
        ordering = ["unlock_step"]

    def __str__(self):
        return f"{self.enrollment} → {self.part} (قسط {self.unlock_step})"







# --- COUPONS & PAYMENTS ---

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import JSONField

class Coupon(models.Model):
    code = models.CharField("الكود", max_length=40, unique=True)
    # --- جديد: مالك الكوبون (مدرّب/أدمن) + دورات مسموح بها ---
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="coupons",
        verbose_name="المالك (اختياري)"
    )
    courses = models.ManyToManyField(
        "learning.Course",
        blank=True,
        related_name="coupons",
        verbose_name="الدورات المسموح بها"
    )
    percent = models.DecimalField(
        "نسبة الخصم (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="مثلاً 15 يعني 15% خصم"
    )
    active_from = models.DateTimeField("يبدأ من", null=True, blank=True)
    active_to   = models.DateTimeField("ينتهي في", null=True, blank=True)
    enabled     = models.BooleanField("مُفعّل", default=True)
    usage_limit = models.PositiveIntegerField("حد الاستخدام", null=True, blank=True,
                                              help_text="اتركه فارغًا لو غير محدود")
    used_count  = models.PositiveIntegerField("عدد مرات الاستخدام", default=0)
    notes       = models.TextField("ملاحظات", blank=True, null=True)

    class Meta:
        verbose_name = "كوبون"
        verbose_name_plural = "الكوبونات"
        ordering = ["-id"]

    def __str__(self):
        return f"{self.code} ({self.percent}%)"

    def is_active_now(self, now=None) -> bool:
        from django.utils import timezone
        now = now or timezone.now()
        if not self.enabled:
            return False
        if self.active_from and now < self.active_from:
            return False
        if self.active_to and now > self.active_to:
            return False
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return False
        return True

    def apply(self, amount):
        """يرجع (amount_after, discount_amount)"""
        from decimal import Decimal, ROUND_HALF_UP
        if self.percent <= 0:
            return (amount, Decimal("0.00"))
        disc = (amount * (self.percent / 100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return (amount - disc, disc)

    def is_valid_for(self, *, course=None, now=None) -> bool:
        """يتأكد إن الكوبون صالح زمنيًا ومسموح للكورس (لو محدد)."""
        if not self.is_active_now(now=now):
            return False

        # 1) لو الكوبون منسوب لمدرّس
        if self.owner_id:
            if course is None:
                return False  # كوبون مدرّس لازم نمرر الكورس
            # مسموح فقط لكورسات هذا المدرّس
            if getattr(course, "instructor_id", None) != self.owner_id:
                return False
            # لو محدد دورات بالاسم، لازم الكورس يكون من ضمنها
            if self.courses.exists() and not self.courses.filter(pk=course.pk).exists():
                return False
            return True

        # 2) كوبون “منصة عامة” (بدون مالك)
        if self.courses.exists():
            # لو المالك غير محدد لكن فيه دورات مقيّدة، يبقى لازم الكورس يطابق
            if course is None:
                return False
            return self.courses.filter(pk=course.pk).exists()

        # 3) عام بالكامل
        return True

    def apply_for_course(self, amount, *, course=None):
        """نفس apply القديمة لكن تراعي الكورس."""
        if not self.is_valid_for(course=course):
            from decimal import Decimal
            return (amount, Decimal("0.00"))
        return self.apply(amount)  # تستخدم نفس منطق الخصم الحالي














class Payment(models.Model):
    class Mode(models.TextChoices):
        FULL = "full", "دفع كامل"
        INST = "installment", "قسط"

    class Status(models.TextChoices):
        CREATED  = "created", "تم الإنشاء"
        APPROVED = "approved", "موافق عليه"
        CAPTURED = "captured", "تم التحصيل"
        FAILED   = "failed", "فشل"

    class Method(models.TextChoices):
        PAYPAL        = "paypal", "PayPal"
        BANK_TRANSFER = "bank",   "تحويل بنكي"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="payments", verbose_name="المستخدم")
    course = models.ForeignKey("learning.Course", on_delete=models.CASCADE,
                               related_name="payments", verbose_name="الدورة")

    enrollment = models.ForeignKey("commerce.Enrollment", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="payments",
                                   verbose_name="الاشتراك")
    installment = models.ForeignKey("commerce.EnrollmentInstallment", on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name="payments",
                                    verbose_name="القسط")

    mode = models.CharField(max_length=12, choices=Mode.choices, verbose_name="طريقة الدفع")
    step = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="رقم القسط")

    currency = models.CharField(max_length=8, default="USD", verbose_name="العملة")
    amount   = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ النهائي")
    coupon   = models.ForeignKey(Coupon, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="كوبون")
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="قيمة الخصم")

    paypal_order_id   = models.CharField(max_length=64, blank=True, null=True)
    paypal_capture_id = models.CharField(max_length=64, blank=True, null=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CREATED, verbose_name="الحالة")
    raw_response = JSONField(blank=True, null=True, verbose_name="استجابة باي بال (JSON)")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    method   = models.CharField(max_length=12, choices=Method.choices, default=Method.PAYPAL)
    class Meta:
        verbose_name = "دفعة"
        verbose_name_plural = "الدفعات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} → {self.course} [{self.mode}] {self.amount} {self.currency} ({self.status})"







# accounts/models.py (أو app مناسب عندك)
from django.conf import settings
from django.db import models
from django.utils import timezone

class UserActivity(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="activity")
    last_seen = models.DateTimeField(default=timezone.now)
    last_absence_email_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user} last_seen={self.last_seen}"
