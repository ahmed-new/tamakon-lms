# learning/admin.py
from django.contrib import admin
from .models import Course, CoursePart, Chapter, Topic, Lesson ,LessonView, Question, AnswerOption,FAQ
from .forms import QuestionForm
from django.utils.html import format_html


class CourseByOwnerFilter(admin.SimpleListFilter):
    title = "الدورة"
    parameter_name = "course"

    def lookups(self, request, model_admin):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            qs = Course.objects.all().order_by("title")
        elif getattr(request.user, "is_trainer", False):
            qs = Course.objects.filter(instructor=request.user).order_by("title")
        else:
            qs = Course.objects.none()
        return [(c.id, c.title) for c in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(course_id=self.value())
        return queryset


class ChapterByOwnerFilter(admin.SimpleListFilter):
    title = "الفصل"
    parameter_name = "chapter"

    def lookups(self, request, model_admin):
        
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            qs = Chapter.objects.select_related("part__course") \
                                .order_by("part__course__title", "part__order_index", "order_index")
        elif getattr(request.user, "is_trainer", False):
            qs = Chapter.objects.filter(part__course__instructor=request.user) \
                                .select_related("part__course") \
                                .order_by("part__course__title", "part__order_index", "order_index")
        else:
            qs = Chapter.objects.none()
        return [(c.id, f"{c.part.course.title} — {c.part.title} — {c.title}") for c in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(chapter_id=self.value())
        return queryset



class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = ("title", "is_free_preview", "order_index")
    ordering = ("order_index",)



@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display  = ("title", "chapter", "order_index")
    list_filter   = (ChapterByOwnerFilter,)  # أو أضف CourseByOwnerFilter لو معرفه
    search_fields = ("title",)
    ordering      = ("chapter", "order_index")

    # 1) المدرّب يشوف مواضيع فصول كورساته فقط
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(chapter__part__course__instructor=request.user)
        return qs.none()

    # 2) صلاحيات الكائن: رؤية/تعديل/حذف للمملوك فقط
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_delete_permission(self, request, obj=None):
        ok = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.chapter.part.course.instructor_id == request.user.id)
        return ok

    # 3) تقييد FK "chapter" عند الإنشاء/التعديل ليرى فصوله فقط
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "chapter":
            from .models import Chapter
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                kwargs["queryset"] = Chapter.objects.filter(part__course__instructor=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TopicInline(admin.TabularInline):
    model = Topic
    extra = 0
    fields = ("title", "order_index")
    ordering = ("order_index",)





class PartByOwnerFilter(admin.SimpleListFilter):
    title = "الجزء"
    parameter_name = "part"

    def lookups(self, request, model_admin):
        from .models import CoursePart
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            qs = CoursePart.objects.all().select_related("course").order_by("course__title", "order_index")
        elif getattr(request.user, "is_trainer", False):
            qs = CoursePart.objects.filter(course__instructor=request.user)\
                                   .select_related("course").order_by("course__title", "order_index")
        else:
            qs = CoursePart.objects.none()
        return [(p.id, f"{p.course.title} — {p.title}") for p in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(part_id=self.value())
        return queryset

class ChapterAdmin(admin.ModelAdmin):
    list_display = ("title", "part", "quiz_total_questions", "quiz_random_take", "order_index")
    # استخدم CourseByOwnerFilter لو عندك، وفلتر الأجزاء المقيَّد
    list_filter = (CourseByOwnerFilter, PartByOwnerFilter)  # أو (CourseByOwnerFilter, PartByOwnerFilter) لو معرفه
    search_fields = ("title",)
    ordering = ("part", "order_index")
    inlines = [TopicInline]

    # 1) المدرّب يشوف الفصول الخاصة بكورساتِه فقط
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(part__course__instructor=request.user)
        return qs.none()

    # 2) صلاحيات الكائن: رؤية/تعديل/حذف على المملوك فقط
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.part.course.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.part.course.instructor_id == request.user.id)
        return ok

    def has_delete_permission(self, request, obj=None):
        ok = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.part.course.instructor_id == request.user.id)
        return ok

    # 3) عند الإضافة/التعديل، قيّد FK "part" على أجزاء كورسات المدرّب فقط
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "part":
            from .models import CoursePart
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                kwargs["queryset"] = CoursePart.objects.filter(course__instructor=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)







class CoursePartAdmin(admin.ModelAdmin):
    list_display = ("course", "code", "title", "order_index", "is_active")
    # استبدل "course" في الفلاتر بـ CourseByOwnerFilter
    list_filter = (CourseByOwnerFilter, "is_active")
    search_fields = ("title", "course__title")
    ordering = ("course", "order_index")

    # 1) المدرّب يشوف الأجزاء الخاصة بكورساتِه فقط
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(course__instructor=request.user)
        return qs.none()

    # 2) صلاحيات الكائن: رؤية/تعديل/حذف على المملوك فقط (السوپر يوزر مستثنى)
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.course.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.course.instructor_id == request.user.id)
        return ok

    def has_delete_permission(self, request, obj=None):
        ok = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.course.instructor_id == request.user.id)
        return ok

    # 3) عند الإنشاء/التعديل، القيّد FK "course" ليختار من كورسات المدرّب فقط
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "course":
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                kwargs["queryset"] = Course.objects.filter(instructor=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)












# فلتر مواضيع المدرّب فقط
class TopicByOwnerFilter(admin.SimpleListFilter):
    title = "الموضوع"
    parameter_name = "topic"

    def lookups(self, request, model_admin):
        from .models import Topic
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            qs = Topic.objects.select_related("chapter__part__course") \
                              .order_by("chapter__part__course__title", "chapter__order_index", "order_index")
        elif getattr(request.user, "is_trainer", False):
            qs = Topic.objects.filter(chapter__part__course__instructor=request.user) \
                              .select_related("chapter__part__course") \
                              .order_by("chapter__part__course__title", "chapter__order_index", "order_index")
        else:
            qs = Topic.objects.none()
        return [(t.id, f"{t.chapter.part.course.title} — {t.chapter.title} — {t.title}") for t in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(topic_id=self.value())
        return queryset


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display  = ("title", "topic", "is_free_preview", "order_index")
    list_filter   = (TopicByOwnerFilter, "is_free_preview")  # فلتر يظهر مواضيع المدرّب فقط
    search_fields = ("title",)
    ordering      = ("topic", "order_index")

    # 1) المدرّب يشوف دروس مواضيع كورساته فقط
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(topic__chapter__part__course__instructor=request.user)
        return qs.none()

    # 2) صلاحيات الكائن: رؤية/تعديل/حذف للمملوك فقط
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.topic.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.topic.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_delete_permission(self, request, obj=None):
        ok = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.topic.chapter.part.course.instructor_id == request.user.id)
        return ok

    # 3) عند الإضافة/التعديل، قَيِّد FK "topic" بمواضيع المدرّب فقط
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "topic":
            from .models import Topic
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                kwargs["queryset"] = Topic.objects.filter(
                    chapter__part__course__instructor=request.user
                )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)



@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "instructor", "has_certificate","thumb", "created_at")
    search_fields = ("title", "slug", "instructor__username", "instructor__email")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("-created_at",)

    fieldsets = (
        ("البيانات الأساسية", {
            # ضفنا instructor هنا عشان تقدّر تعيّنه من الأدمِن
            "fields": ("title", "slug", "description", "has_certificate","image", "instructor"),
        }),
        ("التسعير والأقساط", {
            "fields": ("price", "currency", "allow_installments", "installments_count"),
        }),
        ("المعلومات الزمنية", {
            "classes": ("collapse",),
            "fields": ("created_at", "updated_at"),
        }),
    )
    readonly_fields = ("created_at", "updated_at")

    # ===== فلترة قائمة الدورات على مالكها للمدرب =====
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        # لو هو مدرب، يشوف دوراته بس
        if getattr(request.user, "is_trainer", False):
            return qs.filter(instructor=request.user)
        return qs

    # ===== صلاحيات على مستوى الكائن =====
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.instructor_id == request.user.id)
        return ok

    def has_delete_permission(self, request, obj=None):
        ok = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.instructor_id == request.user.id)
        return ok

    def has_add_permission(self, request):
        # المدرب مسموح له يضيف كورس جديد (هيتسجّل باسمه تلقائيًا تحت)
        return super().has_add_permission(request)

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        # لو superuser (أو أدمن داخلي) يشوف الحقل عادي
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return fieldsets

        # لو مدرّب: نشيل الحقل من الفورم
        if getattr(request.user, "is_trainer", False):
            new_fs = []
            for title, opts in fieldsets:
                fields = list(opts.get("fields", ()))
                if "instructor" in fields:
                    fields = [f for f in fields if f != "instructor"]
                new_opts = dict(opts)
                new_opts["fields"] = tuple(fields)
                new_fs.append((title, new_opts))
            return tuple(new_fs)

        return fieldsets

    # 2) لو لأي سبب الحقل ظهر، قيّد الاختيارات للمدرّب نفسه فقط (دفاع إضافي)
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "instructor":
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                User = db_field.remote_field.model
                kwargs["queryset"] = User.objects.filter(pk=request.user.pk)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    # 3) اجعل حقل المالك Readonly للمدرّب بعد الإنشاء
    def get_readonly_fields(self, request, obj=None):
        ro = list(getattr(self, "readonly_fields", ()))
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return tuple(ro)
        if getattr(request.user, "is_trainer", False) and obj is not None:
            ro.append("instructor")
        return tuple(ro)

    # 4) وأخيرًا: enforce — حتى لو حد لعب في الريكوست، نزبط المالك للمدرّب الحالي
    def save_model(self, request, obj, form, change):
        if getattr(request.user, "is_trainer", False) and not request.user.is_superuser:
            # في الإنشاء أو التعديل: دايمًا خلي المالك هو المستخدم الحالي
            obj.instructor = request.user
        super().save_model(request, obj, form, change)


    def thumb(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;border-radius:6px;" />', obj.image.url)
        return "-"
    thumb.short_description = "صورة"









# فلتر بالدورة — يعرض للمدرّب كورساته فقط
class CourseOwnedFilterForViews(admin.SimpleListFilter):
    title = "الدورة"
    parameter_name = "by_course"

    def lookups(self, request, model_admin):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            qs = Course.objects.all().order_by("title")
        elif getattr(request.user, "is_trainer", False):
            qs = Course.objects.filter(instructor=request.user).order_by("title")
        else:
            qs = Course.objects.none()
        return [(c.id, c.title) for c in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(lesson__topic__chapter__part__course_id=self.value())
        return queryset

# فلتر بالدرس — يعرض للمدرّب دروس كورساته فقط
class LessonOwnedFilter(admin.SimpleListFilter):
    title = "الدرس"
    parameter_name = "by_lesson"

    def lookups(self, request, model_admin):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            qs = Lesson.objects.select_related("topic__chapter__part__course") \
                               .order_by("topic__chapter__part__course__title", "topic__order_index", "order_index")
        elif getattr(request.user, "is_trainer", False):
            qs = Lesson.objects.filter(
                topic__chapter__part__course__instructor=request.user
            ).select_related("topic__chapter__part__course") \
             .order_by("topic__chapter__part__course__title", "topic__order_index", "order_index")
        else:
            qs = Lesson.objects.none()

        def label(l):
            c = l.topic.chapter
            return f"{c.part.course.title} — {c.title} — {l.topic.title} — {l.title}"

        return [(l.id, label(l)) for l in qs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(lesson_id=self.value())
        return queryset


@admin.register(LessonView)
class LessonViewAdmin(admin.ModelAdmin):
    list_display  = ("user", "lesson", "completed_at")
    list_filter   = ("user", CourseOwnedFilterForViews, LessonOwnedFilter)
    search_fields = ("user__username", "lesson__title")
    ordering      = ("-completed_at",)

    # 1) المدرّب يشوف فقط الإتمامات التابعة لدروسه
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related(
            "lesson__topic__chapter__part__course", "user"
        )
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(lesson__topic__chapter__part__course__instructor=request.user)
        return qs.none()

    # 2) صلاحيات على مستوى السجل
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.lesson.topic.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        # عادةً LessonView ما بيتعدلش؛ خلّيها للسوپر يوزر فقط
        if request.user.is_superuser:
            return True
        if getattr(request.user, "is_trainer", False):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # ممكن تمنع حذف الإتمامات عن المدرّب
        if request.user.is_superuser:
            return True
        if getattr(request.user, "is_trainer", False):
            return False
        return super().has_delete_permission(request, obj)

    def has_add_permission(self, request):
        # ما نسمحش بإضافة إتمام درس يدويًا (بيتسجّل تلقائي)
        return request.user.is_superuser







class AnswerOptionInline(admin.TabularInline):
    model = AnswerOption
    extra = 2





@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    form = QuestionForm
    list_display  = ("id", "chapter", "type", "is_active")
    # خليك باستخدام فلتر الفصول المملوكة + بقية الفلاتر العادية
    list_filter   = (ChapterByOwnerFilter, "type", "is_active")
    search_fields = ("text",)
    inlines       = [AnswerOptionInline]
    fields = (
        "chapter", "type", "text",
        "table_title", "columns_csv", "rows_csv", "table_note", "table_json",
        "explanation", "is_active",
    )
    help_texts = {
        "table_json": "يمكنك تركه فارغًا إذا استخدمت الحقول أعلاه؛ سيتم توليده تلقائيًا.",
    }

    # 1) فلترة قائمة الأسئلة للمدرّب
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(chapter__part__course__instructor=request.user)
        return qs.none()

    # 2) صلاحيات الكائن (رؤية/تعديل/حذف) للمملوك فقط
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        ok = super().has_change_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.chapter.part.course.instructor_id == request.user.id)
        return ok

    def has_delete_permission(self, request, obj=None):
        ok = super().has_delete_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.chapter.part.course.instructor_id == request.user.id)
        return ok

    # 3) عند الإضافة/التعديل: قَيِّد FK "chapter" بفصول المدرّب فقط
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "chapter":
            from .models import Chapter
            if request.user.is_superuser or getattr(request.user, "is_admin", False):
                return super().formfield_for_foreignkey(db_field, request, **kwargs)
            if getattr(request.user, "is_trainer", False):
                kwargs["queryset"] = Chapter.objects.filter(part__course__instructor=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


admin.site.register(CoursePart, CoursePartAdmin)
admin.site.register(Chapter, ChapterAdmin)
# admin.site.register(Lesson, LessonAdmin)









from django.contrib import admin
from .models import ContactMessage

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "email", "whatsapp", "subject", "created_at", "is_handled")
    list_filter  = ("is_handled", "created_at")
    search_fields = ("name", "email", "subject", "message", "whatsapp")
    readonly_fields = ("created_at",)








from .models import VideoAsset

@admin.register(VideoAsset)
class VideoAssetAdmin(admin.ModelAdmin):
    list_display  = ("title", "provider", "owner", "video_id",
                     "encode_progress", "transcoding_status", "created_at")
    list_filter   = ("provider", "transcoding_status", "encode_progress", "created_at", "owner")
    search_fields = ("title", "video_id", "owner__username", "owner__email")
    readonly_fields = ("created_at", "updated_at")
    # لا نخفي provider — يظهر عادي للمدرّب

    # المدرّب يرى أصوله فقط
    def get_queryset(self, request):
        qs = super().get_queryset(request).select_related("owner")
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return qs
        if getattr(request.user, "is_trainer", False):
            return qs.filter(owner=request.user)
        return qs.none()

    # صلاحيات على مستوى السجل
    def has_view_permission(self, request, obj=None):
        ok = super().has_view_permission(request, obj)
        if request.user.is_superuser or obj is None:
            return ok
        if getattr(request.user, "is_trainer", False):
            return ok and (obj.owner_id == request.user.id)
        return ok

    def has_change_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return True
        if getattr(request.user, "is_trainer", False):
            return bool(obj and obj.owner_id == request.user.id)
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_superuser or getattr(request.user, "is_admin", False):
            return True
        if getattr(request.user, "is_trainer", False):
            return bool(obj and obj.owner_id == request.user.id)
        return super().has_delete_permission(request, obj)

    def has_add_permission(self, request):
        # الإضافة الأساسية بتحصل من صفحة الرفع؛ بس لو حابب تسيبها مفتوحة:
        return request.user.is_superuser or getattr(request.user, "is_admin", False)
    
    
    
    
    
    
@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display  = ("question_short", "category", "is_active", "order_index", "updated_at")
    list_filter   = ("is_active", "category")
    list_editable = ("is_active", "order_index")
    search_fields = ("question", "answer")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("category", "order_index", "id")

    def question_short(self, obj):
        return (obj.question[:60] + "…") if len(obj.question) > 60 else obj.question
    question_short.short_description = "السؤال"