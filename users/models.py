# users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models
import uuid


class User(AbstractUser):
    """
    موديل المستخدم المخصص:
    - يرث من AbstractUser (فيه: username, password, first_name, last_name, email, is_staff, is_superuser, is_active, last_login, date_joined)
    - role: لتحديد الدور (طالب/أدمن/مدرّب)
    - whatsapp_number: رقم واتساب اختياري
    """

    class Roles(models.TextChoices):
        STUDENT = "student", "طالب"
        ADMIN   = "admin",   "أدمن"
        TRAINER = "trainer", "مدرّب"

    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.STUDENT,
        verbose_name="الدور",
        help_text="حدد دور المستخدم داخل المنصة."
    )

    whatsapp_number = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        verbose_name="رقم واتساب",
        help_text="اختياري — لاستخدامه في إشعارات واتساب."
    )


    paypal_client_id = models.CharField(
        max_length=120, blank=True, null=True,
        verbose_name="PayPal Client ID"
    )
    paypal_secret_encrypted = models.TextField(
        blank=True, null=True,
        verbose_name="PayPal Secret (encrypted)"
    )
    

       # setters/getters مريحة
    def set_paypal_secret(self, raw: str | None):
        from .crypto import encrypt
        self.paypal_secret_encrypted = encrypt((raw or "").strip()) if raw else None

    def get_paypal_secret(self) -> str:
        from .crypto import decrypt
        return decrypt(self.paypal_secret_encrypted or "")
    
    # خصائص مساعدة للقراءة
    @property
    def is_admin(self) -> bool:
        return self.role == self.Roles.ADMIN

    @property
    def is_trainer(self) -> bool:
        return self.role == self.Roles.TRAINER

    @property
    def is_student(self) -> bool:
        return self.role == self.Roles.STUDENT

    def __str__(self) -> str:
        display = self.get_full_name().strip() or self.username
        return f"{display} ({self.get_role_display()})"

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"
        ordering = ["-date_joined"]






class UserDevice(models.Model):
    """
    جهاز مسجَّل للمستخدم.
    - device_id: معرّف ثابت نخزّنه في كوكي بالمتصفح
    - user_agent/ip: معلومات مرجعية
    - allowed: لو حبّينا نعطّل جهاز لاحقًا
    """
    user = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="devices", verbose_name="المستخدم")
    device_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name="معرّف الجهاز")
    user_agent = models.TextField(blank=True, null=True, verbose_name="User-Agent")
    ip_address = models.GenericIPAddressField(blank=True, null=True, verbose_name="IP")
    allowed = models.BooleanField(default=True, verbose_name="مسموح")
    first_seen_at = models.DateTimeField(auto_now_add=True, verbose_name="أول ظهور")
    last_seen_at = models.DateTimeField(auto_now=True, verbose_name="آخر ظهور")

    class Meta:
        verbose_name = "جهاز مستخدم"
        verbose_name_plural = "أجهزة المستخدمين"
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.user} — {self.device_id}"
