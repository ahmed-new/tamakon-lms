# tamakon/admin_order.py
from django.contrib import admin


admin.site.site_header="ادارة تمكن"
admin.site.site_title="واجهة ادارة منصة تمكن"
# ترتيب عرض الموديلات داخل كل App
MODEL_ORDER = {
    "learning": [
        "Course",
        "CoursePart",
        "Chapter",
        "Topic",
        "Lesson",
        "Question",
        "AnswerOption",
        "LessonView",  # اختياري؛ خليه آخر واحد
    ],
    "commerce": [
        "Enrollment",
        "EnrollmentInstallment",
        "EnrollmentPartAccess",
        "Visitor",
    ],
    # لو حابب ترتّب users برضه:
    # "users": ["User", "UserDevice"],
}

# (اختياري) ترتيب عرض التطبيقات نفسها في صفحة الأدمن
APP_ORDER = [
    "LEARNING",
    "COMMERCE",
    "AUTHENTICATION AND AUTHORIZATION",  # المجموعات/الصلاحيات
]

def _app_order_key(app):
    name = app["name"].upper()
    try:
        return APP_ORDER.index(name)
    except ValueError:
        return 999  # أي App غير مذكور ييجي في الآخر

def custom_get_app_list(self, request):
    """
    نعيد قائمة التطبيقات لكن مرتبة حسب APP_ORDER
    ونرتب الموديلات داخل كل تطبيق حسب MODEL_ORDER.
    """
    app_dict = self._build_app_dict(request)
    app_list = sorted(app_dict.values(), key=_app_order_key)

    for app in app_list:
        label = app["app_label"]  # مثال: "learning"
        desired = MODEL_ORDER.get(label, [])
        if desired:
            app["models"].sort(
                key=lambda m: desired.index(m["object_name"]) if m["object_name"] in desired else len(desired) + 1
            )
        else:
            # الافتراضي: أبجدي بالـ verbose_name
            app["models"].sort(key=lambda m: m["name"])
    return app_list

# تطبيق الباتش على الأدمن الافتراضي
admin.AdminSite.get_app_list = custom_get_app_list
