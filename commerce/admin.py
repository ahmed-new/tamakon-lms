# commerce/admin.py
from django.contrib import admin
from django.utils import timezone
from .models import Enrollment, EnrollmentInstallment, EnrollmentPartAccess
from .utils import ensure_part_access_plan  # ← جديد
from learning.models import Course




class EnrollmentInstallmentInline(admin.TabularInline):
    model = EnrollmentInstallment
    extra = 0
    readonly_fields = ("created_at",)

class EnrollmentPartAccessInline(admin.TabularInline):
    model = EnrollmentPartAccess
    extra = 0

@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "status", "started_at", "expires_at", "created_at")
    list_filter = ("status", "course")
    search_fields = ("user__username", "user__email", "course__title")
    inlines = [EnrollmentInstallmentInline, EnrollmentPartAccessInline]
    actions = ["generate_part_plan"]

    @admin.action(description="توليد خطة فتح الأجزاء حسب ترتيب الدورة")
    def generate_part_plan(self, request, queryset):
        total = 0
        for enr in queryset:
            total += ensure_part_access_plan(enr, overwrite=False)
        self.message_user(request, f"تم إنشاء {total} سماحية جزء.")

@admin.register(EnrollmentInstallment)
class EnrollmentInstallmentAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "step", "amount", "due_date", "status", "paid_at")
    list_filter = ("status",)
    actions = ["mark_paid"]

    @admin.action(description="تحديد كمدفوع الآن")
    def mark_paid(self, request, queryset):
        updated = 0
        for inst in queryset:
            inst.status = EnrollmentInstallment.Status.PAID
            inst.paid_at = timezone.now()
            inst.save(update_fields=["status", "paid_at"])
            updated += 1
        self.message_user(request, f"تم تحديث {updated} قسط/أقساط إلى مدفوع.")

@admin.register(EnrollmentPartAccess)
class EnrollmentPartAccessAdmin(admin.ModelAdmin):
    list_display = ("enrollment", "part", "unlock_step", "unlocked_at")
    list_filter = ("unlock_step", "part__course")
    search_fields = ("enrollment__user__username", "enrollment__user__email", "part__title")





from django.contrib import admin
from .models import Coupon, Payment

@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display  = ("code", "percent", "enabled", "owner", "active_from", "active_to", "usage_limit", "used_count")
    list_filter   = ("enabled", "active_from", "active_to")
    search_fields = ("code", "notes")
    ordering      = ("-id",)

    # المدرّب يشوف فقط كوبوناته
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("owner")
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(owner=request.user)
        return qs.none()

    # المدرب يقدر يضيف كوبون لنفسه فقط
    def has_add_permission(self, request):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return True
        if getattr(request.user, "is_trainer", False):
            return True  # يضيف كوبون مملوك له
        return False

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return True
        if getattr(request.user, "is_trainer", False):
            return bool(obj and obj.owner_id == request.user.id)
        return False

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return True
        if getattr(request.user, "is_trainer", False):
            return bool(obj and obj.owner_id == request.user.id)
        return False

    # حصر اختيارات الدورات على دورات المدرّب في الـ M2M
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "courses":
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                
                return super().formfield_for_manytomany(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                kwargs["queryset"] = Course.objects.filter(instructor=request.user)
        return super().formfield_for_manytomany(db_field, request, **kwargs)


    def get_fieldsets(self, request, obj =None):
        fieldsets = super().get_fieldsets(request, obj)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return fieldsets
        if getattr(request.user, "is_trainer", False):
            new_fs=[]
            for title , options in fieldsets:
                fields= list (options.get("fields",()))
                if "owner" in fields:
                    fields=[f for f in fields if f != "owner"]
                    newopts= dict(options)
                    newopts["fields"]= fields
                    new_fs.append((title , newopts))
            return tuple(new_fs)



    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name=="owner":
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                User = db_field.remote_field.model
                kwargs["queryset"] = User.objects.filter(role__in = ["admin","trainer"])
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
                
            if getattr(request.user, "is_trainer", False):
                User = db_field.remote_field.model
                kwargs['queryset'] = User.objects.filter(pk= request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)    






    # ضمان إن المالك هو المدرّب الحالي عند الإنشاء، وعدم تغييره بعد كده
    def save_model(self, request, obj, form, change):
        if getattr(request.user, "is_trainer", False) and not request.user.is_superuser:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return ()
        if getattr(request.user, "is_trainer", False):
            # لا يغير الـ owner يدويًا
            base = list(getattr(self, "readonly_fields", ()))
            if obj:
                base.append("owner")
            return tuple(base)
        return super().get_readonly_fields(request, obj)















@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("user", "course", "mode", "amount", "currency", "status", "created_at")
    list_filter = ("status", "mode", "currency", "course")
    search_fields = ("user__username", "user__email", "paypal_order_id", "paypal_capture_id")
    readonly_fields = ("raw_response",)
