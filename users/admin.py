# users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User , UserDevice


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff", "is_superuser")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-date_joined",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("المعلومات الشخصية", {"fields": ("first_name", "last_name", "email", "whatsapp_number")}),
        ("الأذونات", {"fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("تواريخ مهمة", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "email", "password1", "password2", "role", "is_active"),
        }),
    )






@admin.register(UserDevice)
class UserDeviceAdmin(admin.ModelAdmin):
    list_display = ("user", "device_id", "allowed", "ip_address", "short_ua", "first_seen_at", "last_seen_at")
    list_filter  = ("allowed", "user")
    search_fields = ("user__username", "user__email", "device_id", "ip_address", "user_agent")
    readonly_fields = ("device_id", "user_agent", "ip_address", "first_seen_at", "last_seen_at")

    def short_ua(self, obj):
        ua = (obj.user_agent or "")[:60]
        return ua + ("..." if len(obj.user_agent or "") > 60 else "")
    short_ua.short_description = "User-Agent"







from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User

# Proxy Model علشان صفحة مستقلة لبيانات الدفع
class TrainerBilling(User):
    class Meta:
        proxy = True
        verbose_name = "بيانات باي بال (للمدرب)"
        verbose_name_plural = "بيانات باي بال (للمدرّبين)"

class TrainerBillingForm(forms.ModelForm):
    paypal_secret_plain = forms.CharField(
        label="PayPal Secret",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="اتركه فارغًا للإبقاء على السر الحالي."
    )

    class Meta:
        model = User
        fields = ("paypal_client_id", "paypal_secret_plain")

    def save(self, commit=True):
        u = super().save(commit=False)
        secret_plain = self.cleaned_data.get("paypal_secret_plain")
        if secret_plain:
            u.set_paypal_secret(secret_plain)
        if commit:
            # حفظ client_id و السر المشفّر فقط
            u.save(update_fields=["paypal_client_id", "paypal_secret_encrypted"])
        return u

@admin.register(TrainerBilling)
class TrainerBillingAdmin(admin.ModelAdmin):
    form = TrainerBillingForm
    fields = ("username", "paypal_client_id", "paypal_secret_plain")
    readonly_fields = ("username",)
    list_display = ("username", "paypal_client_id")
    search_fields = ("username", "email")

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs.filter(role="trainer")
        if getattr(request.user, "is_trainer", False):
            return qs.filter(pk=request.user.pk)
        return qs.none()

    def has_view_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return True
        if getattr(request.user, "is_trainer", False):
            return obj is None or obj.pk == request.user.pk
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return False
        if getattr(request.user, "is_trainer", False):
            return obj is not None and obj.pk == request.user.pk
        return False

    def has_add_permission(self, request):
        # لا إنشاء سجلات جديدة — بس تعديل نفسه
        return False

    def has_delete_permission(self, request, obj=None):
        return False
