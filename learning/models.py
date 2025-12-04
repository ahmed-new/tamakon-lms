# learning/models.py
from django.db import models
from django.conf import settings
from decimal import Decimal




class Course(models.Model):
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,              # users.User
        on_delete=models.PROTECT,              # مايتحذفش لو المستخدم اتحذف بالغلط
        related_name="owned_courses",
        null=True, blank=True,                 # مبدئيًا نخلّيها Nullable لتمرير أول ميجريشن
        db_index=True,
        verbose_name="المدرّب (مالك)"
    )

    title = models.CharField(max_length=255, verbose_name="عنوان الدورة")
    slug = models.SlugField(max_length=255, unique=True, verbose_name="المعرف اللطيف")
    description = models.TextField(blank=True, verbose_name="وصف مختصر")
    has_certificate = models.BooleanField(default=True, verbose_name="شهادة إتمام")
    image = models.ImageField(upload_to="courses/", blank=True, null=True, verbose_name="صورة الدورة")

       # ====== تسعير وأقساط ======
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        default=Decimal("0.00"), verbose_name="سعر الدورة"
    )
    currency = models.CharField(
        max_length=8, default="USD", verbose_name="العملة"
    )
    allow_installments = models.BooleanField(
        default=False, verbose_name="تسمح بالدفع على أقساط؟"
    )
    installments_count = models.PositiveSmallIntegerField(
        default=1, verbose_name="عدد الأقساط (إن وُجد)",
        help_text="1 = دفع كامل مرة واحدة"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "دورة"
        verbose_name_plural = "الدورات"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def clean(self):
        # لو الأقساط غير مفعّلة خلي العدد = 1
        if not self.allow_installments:
            self.installments_count = 1
        # حماية بسيطة
        if self.installments_count < 1:
            raise ValidationError({"installments_count": "يجب أن يكون 1 على الأقل."})




class CoursePart(models.Model):
    """أجزاء الدورة (A/B/C) وقابلة لإعادة الترتيب من الأدمن."""
    class PartCode(models.TextChoices):
        A = "A", "أ"
        B = "B", "ب"
        C = "C", "ج"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="parts", verbose_name="الدورة")
    code = models.CharField(max_length=1, choices=PartCode.choices, verbose_name="الرمز")
    title = models.CharField(max_length=255, verbose_name="عنوان الجزء")
    description = models.TextField(blank=True, verbose_name="وصف الجزء")
    order_index = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    is_active = models.BooleanField(default=True, verbose_name="مُفعّل")

    class Meta:
        verbose_name = "جزء"
        verbose_name_plural = "الأجزاء"
        ordering = ["order_index"]
        unique_together = (("course", "code"),)

    def __str__(self):
        return f"{self.course.title} - جزء {self.get_code_display()}"





class Chapter(models.Model):
    """الفصل: يحتوي ملخص PDF وبنك أسئلة لاحقًا."""
    part = models.ForeignKey(CoursePart, on_delete=models.CASCADE, related_name="chapters", verbose_name="الجزء")
    title = models.CharField(max_length=255, verbose_name="عنوان الفصل")
    summary_pdf_url = models.TextField(blank=True, verbose_name="ملف الملخص PDF (رابط)")
    quiz_total_questions = models.PositiveIntegerField(default=0, verbose_name="إجمالي أسئلة البنك")
    quiz_random_take = models.PositiveIntegerField(default=20, verbose_name="عدد الأسئلة العشوائية في كل محاولة")
    order_index = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "فصل"
        verbose_name_plural = "الفصول"
        ordering = ["order_index"]

    def __str__(self):
        return f"{self.title} ({self.part})"








class Topic(models.Model):
    """موضوع داخل الفصل."""
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="topics", verbose_name="الفصل")
    title = models.CharField(max_length=255, verbose_name="عنوان الموضوع")
    order_index = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "موضوع"
        verbose_name_plural = "المواضيع"
        ordering = ["order_index"]

    def __str__(self):
        return f"{self.title} ({self.chapter})"






class Lesson(models.Model):
    """درس فيديو داخل الموضوع. الدرس الأول مجاني للمعاينة."""
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="lessons", verbose_name="الموضوع")
    title = models.CharField(max_length=255, verbose_name="عنوان الدرس")

    # مصدر واحد للفيديو (رابط أو ID كما تفضّل لاحقًا)
    video_url = models.TextField(verbose_name="رابط الفيديو")

    is_free_preview = models.BooleanField(default=False, verbose_name="متاح للمعاينة مجانًا")
    duration_seconds = models.PositiveIntegerField(null=True, blank=True, verbose_name="المدة بالثواني")
    order_index = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")

    class Meta:
        verbose_name = "درس"
        verbose_name_plural = "الدروس"
        ordering = ["order_index"]

    def __str__(self):
        return f"{self.title} ({self.topic})"






class LessonView(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lesson_views", verbose_name="المستخدم")
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="views", verbose_name="الدرس")
    completed_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإتمام")

    class Meta:
        verbose_name = "إتمام درس"
        verbose_name_plural = "إتمامات الدروس"
        unique_together = (("user", "lesson"),)  # كل درس مرة واحدة لكل مستخدم
        ordering = ["-completed_at"]

    def __str__(self):
        return f"{self.user} ⟶ {self.lesson} ({self.completed_at:%Y-%m-%d})"
    





# ===== Quiz (per Chapter, no attempts) =====
# learning/models.py (داخل Question)
from django.core.exceptions import ValidationError

class Question(models.Model):
    class QType(models.TextChoices):
        TEXT = "text", "نصي"
        TABLE = "table", "جدول"

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="questions", verbose_name="الفصل")
    text = models.TextField(verbose_name="نص السؤال")
    type = models.CharField(max_length=12, choices=QType.choices, default=QType.TEXT, verbose_name="النوع")

    # جدول منظم يُعرض داخل السؤال
    table_json = models.JSONField(blank=True, null=True, verbose_name="جدول السؤال (JSON)")

    explanation = models.TextField(blank=True, null=True, verbose_name="شرح عند الخطأ")
    is_active = models.BooleanField(default=True, verbose_name="مُفعّل")

    class Meta:
        verbose_name = "سؤال"
        verbose_name_plural = "أسئلة الفصل"
        ordering = ["id"]

    def __str__(self):
        return f"سؤال #{self.id} — {self.chapter.title}"

    def clean(self):
        super().clean()
        if self.type == self.QType.TABLE and not self.table_json:
            raise ValidationError("لأسئلة النوع جدول، يجب إدخال JSON للجدول أو تعبئة الحقول المساعدة.")



class AnswerOption(models.Model):
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="options", verbose_name="السؤال")
    text = models.TextField(verbose_name="نص الاختيار")
    is_correct = models.BooleanField(default=False, verbose_name="إجابة صحيحة؟")

    class Meta:
        verbose_name = "اختيار"
        verbose_name_plural = "اختيارات السؤال"
        ordering = ["id"]

    def __str__(self):
        return f"اختيار لسؤال #{self.question_id}"














class ContactMessage(models.Model):
    name = models.CharField(max_length=150, verbose_name="الاسم")
    email = models.EmailField(verbose_name="البريد الإلكتروني")
    whatsapp = models.CharField(max_length=30, blank=True, null=True, verbose_name="رقم واتساب (اختياري)")
    subject = models.CharField(max_length=200, verbose_name="العنوان / موضوع الرسالة")
    message = models.TextField(verbose_name="نص الرسالة")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإرسال")
    is_handled = models.BooleanField(default=False, verbose_name="تمت المعالجة؟")

    class Meta:
        verbose_name = "رسالة تواصل"
        verbose_name_plural = "رسائل تواصل"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> — {self.subject}"
    



# learning/models.py

class VideoAsset(models.Model):
    class Provider(models.TextChoices):
        VIMEO = "vimeo", "Vimeo"   # ← الوحيد المعروض

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="video_assets", verbose_name="المالك")

    provider = models.CharField("مزود الفيديو", max_length=30,
                                choices=Provider.choices, default=Provider.VIMEO)

    title = models.CharField("عنوان الفيديو", max_length=200)
    video_id = models.CharField("Video ID / URL", max_length=200, db_index=True)

    duration_seconds = models.PositiveIntegerField("المدة بالثواني", blank=True, null=True)
    encode_progress = models.PositiveIntegerField("نسبة المعالجة %", blank=True, null=True)
    transcoding_status = models.PositiveSmallIntegerField("حالة الترانسكود", blank=True, null=True)
    thumbnail_url = models.URLField("صورة مصغّرة", blank=True, null=True)
    meta = models.JSONField("بيانات إضافية (JSON)", blank=True, null=True)

    created_at = models.DateTimeField("أُنشت في", auto_now_add=True)
    updated_at = models.DateTimeField("عُدّلت في", auto_now=True)

    class Meta:
        verbose_name = "فيديو مرفوع"
        verbose_name_plural = "فيديوهات مرفوعة"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} — {self.video_id[:10]}"

    @property
    def is_ready(self) -> bool:
        if isinstance(self.encode_progress, int) and self.encode_progress >= 100:
            return True
        if isinstance(self.transcoding_status, int) and self.transcoding_status == 2:
            return True
        return False

    @property
    def embed_url(self) -> str | None:
        """
        بالرغم إن الـ provider ظاهر Vimeo، هنفضل نولّد IFRAME بتاع Bunny.
        """
        v = (self.video_id or "").strip()
        if not v:
            return None
        if v.startswith(("http://", "https://")):
            return v
        lib = getattr(settings, "BUNNY_LIBRARY_ID", None)
        if not lib:
            return None
        return f"https://iframe.mediadelivery.net/embed/{lib}/{v}"







# الاسئلة الشائعة
class FAQ(models.Model):
    category     = models.CharField("التصنيف (اختياري)", max_length=100, blank=True, null=True)
    question     = models.CharField("السؤال", max_length=255)
    answer       = models.TextField("الإجابة")
    order_index  = models.PositiveIntegerField("ترتيب العرض", default=0, db_index=True)
    is_active    = models.BooleanField("مُفعّل", default=True)
    created_at   = models.DateTimeField("أُنشئ في", auto_now_add=True,null=True, blank=True)
    updated_at   = models.DateTimeField("عُدّل في", auto_now=True,null=True, blank=True)

    class Meta:
        verbose_name = "سؤال شائع"
        verbose_name_plural = "الأسئلة الشائعة"
        ordering = ["category", "order_index", "id"]

    def __str__(self):
        return self.question