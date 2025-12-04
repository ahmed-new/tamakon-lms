# learning/views.py
from django.shortcuts import render, get_object_or_404, redirect, resolve_url
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from .forms import ContactForm
from .models import Lesson, LessonView, Chapter, Question, Course, CoursePart, Topic ,FAQ
from .utils import user_has_part_access ,get_active_enrollment, unlocked_parts_for_enrollment , course_progress_percent
from commerce.models import EnrollmentInstallment ,Enrollment , Visitor
import random
from django.core.mail import EmailMultiAlternatives
from collections import OrderedDict







def home(request):
    return render(request, "learning/home.html")






@login_required
def my_courses(request):
    enrollments = (Enrollment.objects
                   .filter(user=request.user)
                   .select_related("course")
                   .prefetch_related("installments")
                   .order_by("-created_at"))

    # احسب progress لكل كورس وألصقه مؤقتًا على الـ enrollment
    for enr in enrollments:
        try:
            prog = course_progress_percent(request.user, enr.course)  # 0..100 (float)
        except Exception:
            prog = 0.0

        # قيّم صحيحة ومحصورة 0..100 للاستخدام في القالب
        try:
            prog_int = int(round(float(prog)))
        except Exception:
            prog_int = 0
        enr.progress = max(0, min(100, prog_int))

        # معلومة القسط المستحق التالي (لو هتفيدك في العرض)
        due = enr.installments.filter(status=EnrollmentInstallment.Status.DUE).order_by("step").first()
        enr.next_due_step = due.step if due else None
        enr.next_due_date = due.due_date if due else None

    return render(request, "learning/my_courses.html", {
        "enrollments": enrollments,
    })







def course_list(request):
    courses = Course.objects.all().order_by("-created_at")
    return render(request, "learning/course_list.html", {"courses": courses})



from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings

def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)

    parts = (
        CoursePart.objects
        .filter(course=course, is_active=True)
        .order_by("order_index")
        .prefetch_related(
            Prefetch("chapters",
                     queryset=Chapter.objects.order_by("order_index").prefetch_related(
                         Prefetch("topics",
                                  queryset=Topic.objects.order_by("order_index").prefetch_related("lessons"))
                     ))
        )
    )

    open_part_ids = set()
    next_due_step = None
    enrollment = None
    paid_installments = 0
    remaining_installments = 0

    if request.user.is_authenticated:
        enrollment = get_active_enrollment(request.user, course)
        if enrollment:
            allowed = unlocked_parts_for_enrollment(enrollment)
            if allowed is None:
                open_part_ids = {p.id for p in parts}  # وصول كامل
            else:
                open_part_ids = set(allowed)

            # القسط المستحق التالي
            due = enrollment.installments.filter(
                status=EnrollmentInstallment.Status.DUE
            ).order_by("step").first()
            if due:
                next_due_step = due.step

            # إحصائيات الأقساط (لو تقسيط)
            paid_installments = enrollment.installments.filter(
                status=EnrollmentInstallment.Status.PAID
            ).count()
            remaining_installments = enrollment.installments.filter(
                status=EnrollmentInstallment.Status.DUE
            ).count()

    # ====== حساب سعر القسط لو الأقساط مفعّلة ======
    installment_price = None
    installments_count = getattr(course, "installments_count", 1) or 1
    allow_installments = getattr(course, "allow_installments", False)
    if allow_installments and installments_count > 1:
        try:
            installment_price = (Decimal(course.price) / Decimal(installments_count)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except Exception:
            installment_price = None

    # العملة (لو عندك حقل على الـ Course هيتقري تلقائيًا؛ غير كده ندي default من الإعدادات)
    currency = getattr(course, "currency", "") or getattr(settings, "COMMERCE_CURRENCY", "USD")

    return render(request, "learning/course_detail.html", {
        "course": course,
        "parts": parts,
        "open_part_ids": open_part_ids,
        "next_due_step": next_due_step,
        "enrollment": enrollment,
        "paid_installments": paid_installments,
        "remaining_installments": remaining_installments,
        "installment_price": installment_price,   # ← جديد
        "installments_count": installments_count, # ← لتفادي الاعتماد على القالب في الحساب
        "currency": currency,                     # ← عملة موحّدة
        "allow_installments": allow_installments, # ← راية الاستخدام
    })






# ===== معاينة الدروس المجانية (بوابة الزائر) =====
SESSION_KEY = "visitor_ok"  # فلاج عام: الزائر مرّ من البوابة مرة

# مفاتيح بديلة (للتماشي مع أي كود قديم) + per-lesson flag
PREVIEW_KEYS_CANDIDATES = [
    "visitor_ok",
    "preview_passed",
    "preview_ok_lesson_{lesson_id}",
    "preview_passed_lesson_{lesson_id}",
]


def _preview_passed(request, lesson):
    """يتأكد هل الزائر مرّ من بوابة المعاينة (عامًا أو لهذا الدرس)."""
    for key in PREVIEW_KEYS_CANDIDATES:
        if request.session.get(key.format(lesson_id=lesson.pk)):
            return True
    return False


def _ordered_part_lessons_queryset(part):
    return (
        Lesson.objects
        .filter(topic__chapter__part=part)
        .select_related("topic", "topic__chapter")
        .order_by("topic__chapter__order_index", "topic__order_index", "order_index", "pk")
    )

def _make_nav_tree(lessons_qs, completed_ids: set[int]):
    """
    يبني شجرة تنقّل للقائمة الجانبية، ويعلّم الدروس المكتملة.
    """
    tree = []
    by_chapter = OrderedDict()
    for l in lessons_qs:
        ch = l.topic.chapter
        tp = l.topic
        if ch.id not in by_chapter:
            by_chapter[ch.id] = {"chapter": ch, "topics": OrderedDict()}
        topics = by_chapter[ch.id]["topics"]
        if tp.id not in topics:
            topics[tp.id] = {"topic": tp, "lessons": []}
        topics[tp.id]["lessons"].append({
            "id": l.id,
            "title": l.title,
            "is_free_preview": l.is_free_preview,
            "is_completed": (l.id in completed_ids),
        })
    for ch in by_chapter.values():
        tree.append({
            "chapter": ch["chapter"],
            "topics": [v for v in ch["topics"].values()]
        })
    return tree

def _prev_next_for(lessons_qs, current_lesson):
    ids = [l.id for l in lessons_qs]
    try:
        idx = ids.index(current_lesson.id)
    except ValueError:
        return (None, None)
    prev_obj = lessons_qs[idx-1] if idx > 0 else None
    next_obj = lessons_qs[idx+1] if idx + 1 < len(lessons_qs) else None
    return (prev_obj, next_obj)

def _completed_ids_for_user(user, part):
    if not user.is_authenticated:
        return set()
    qs = LessonView.objects.filter(
        user=user,
        lesson__topic__chapter__part=part
    ).values_list("lesson_id", flat=True)
    return set(qs)

def lesson_detail(request, pk: int):
    lesson = get_object_or_404(Lesson, pk=pk)
    part = lesson.topic.chapter.part
    course = part.course

    # دروس المعاينة (اسمح بالعرض بدون دخول لكن اعرض شجرة التنقّل أيضًا)
    if lesson.is_free_preview:
        if not request.user.is_authenticated and not _preview_passed(request, lesson):
            return redirect("learning:preview_gate", pk=lesson.pk)
        lessons_qs = list(_ordered_part_lessons_queryset(part))
        completed_ids = _completed_ids_for_user(request.user, part)
        nav_tree = _make_nav_tree(lessons_qs, completed_ids)
        prev_lesson, next_lesson = _prev_next_for(lessons_qs, lesson)
        return render(request, "learning/lesson_detail.html", {
            "lesson": lesson,
            "nav_tree": nav_tree,
            "prev_lesson": prev_lesson,
            "next_lesson": next_lesson,
            "part": part,
            "course": course,
            "completed_ids": completed_ids,
        })

    # غير مجاني → دخول
    if not request.user.is_authenticated:
        return redirect(f"{resolve_url('users:login')}?next={request.path}")

    # وصول للجزء
    if not user_has_part_access(request.user, part):
        messages.info(request, "هذه المادة متاحة للمشتركين في الجزء المفتوح لك من الدورة.")
        return redirect("learning:course_detail", slug=course.slug)

    # التنقّل + المُكتمل
    lessons_qs = list(_ordered_part_lessons_queryset(part))
    completed_ids = _completed_ids_for_user(request.user, part)
    nav_tree = _make_nav_tree(lessons_qs, completed_ids)
    prev_lesson, next_lesson = _prev_next_for(lessons_qs, lesson)

    return render(request, "learning/lesson_detail.html", {
        "lesson": lesson,
        "nav_tree": nav_tree,
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "part": part,
        "course": course,
        "completed_ids": completed_ids,
    })

def preview_gate(request, pk: int):
    """
    بوابة جمع الإيميل قبل مشاهدة الدرس المجاني.
    - تحفظ الإيميل في Visitor (لو جديد).
    - تضبط سيشن عام + خاص بالدرس.
    """
    lesson = get_object_or_404(Lesson, pk=pk)

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        name = (request.POST.get("name") or "").strip() or None

        if not email:
            messages.error(request, "من فضلك أدخل بريدك الإلكتروني.")
        else:
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "صيغة البريد الإلكتروني غير صحيحة.")
            else:
                visitor, created = Visitor.objects.get_or_create(
                    email=email,
                    defaults={"name": name, "source": f"lesson:{lesson.pk}"},
                )
                if not created:
                    visitor.last_seen_at = timezone.now()
                    if name and not visitor.name:
                        visitor.name = name
                    visitor.save(update_fields=["last_seen_at", "name"] if name else ["last_seen_at"])

                # فلاج عام + فلاج خاص بالدرس
                request.session[SESSION_KEY] = email or True
                request.session[f"preview_passed_lesson_{lesson.pk}"] = True

                messages.success(request, "تم تسجيل بريدك، استمتع بالمشاهدة!")
                return redirect("learning:lesson_detail", pk=lesson.pk)

    return render(request, "learning/preview_gate.html", {"lesson": lesson})





# ===== تسجيل إتمام الدرس (Progress) =====
@login_required
def complete_lesson(request, pk: int):
    """يسجّل إتمام الدرس للمستخدم الحالي لو مش مسجّل قبل كده."""
    lesson = get_object_or_404(Lesson, pk=pk)

    if request.method != "POST":
        messages.info(request, "اضغط زر إتمام الدرس بعد مشاهدة المحتوى.")
        return redirect("learning:lesson_detail", pk=lesson.pk)

    obj, created = LessonView.objects.get_or_create(user=request.user, lesson=lesson)
    if created:
        messages.success(request, "تم تسجيل إتمام الدرس بنجاح.")
    else:
        messages.info(request, "هذا الدرس مُسجّل كمكتمل بالفعل.")

    return redirect("learning:lesson_detail", pk=lesson.pk)





# ===== اختبار الفصل (بدون attempts) =====
@require_http_methods(["GET"])
def chapter_quiz(request, pk: int):
    """يعرض عينة عشوائية من أسئلة الفصل (quiz_random_take)."""
    chapter = get_object_or_404(Chapter, pk=pk)
    part = chapter.part

    # قفل الاختبار على المشتركين في الجزء
    if not request.user.is_authenticated:
        return redirect(f"{reverse('users:login')}?next={request.path}")
    if not user_has_part_access(request.user, part):
        messages.info(request, "هذا الاختبار متاح للمشتركين في الجزء المفتوح لك من الدورة.")
        return redirect("learning:course_detail", slug=part.course.slug)

    all_qs = list(
        Question.objects.filter(chapter=chapter, is_active=True).prefetch_related("options")
    )
    if not all_qs:
        messages.info(request, "لا توجد أسئلة متاحة لهذا الفصل حاليًا.")
        return redirect("learning:course_detail", slug=part.course.slug)

    take = min(chapter.quiz_random_take or 15, len(all_qs))
    random.shuffle(all_qs)
    sample_qs = all_qs[:take]

    return render(request, "learning/chapter_quiz.html", {
        "chapter": chapter,
        "questions": sample_qs,
        "error_qids": set(),
        "answers": {},
    })





@require_http_methods(["POST"])
def chapter_quiz_submit(request, pk: int):
    """يتحقق من الإجابات ويعرض النتيجة + الشرح للأخطاء."""
    chapter = get_object_or_404(Chapter, pk=pk)
    part = chapter.part

    # قفل الاختبار على المشتركين في الجزء
    if not request.user.is_authenticated:
        return redirect(f"{reverse('users:login')}?next={request.path}")
    if not user_has_part_access(request.user, part):
        messages.info(request, "هذا الاختبار متاح للمشتركين في الجزء المفتوح لك من الدورة.")
        return redirect("learning:course_detail", slug=part.course.slug)

    q_ids = request.POST.getlist("q_id")
    if not q_ids:
        messages.error(request, "لم يتم العثور على أسئلة مرسلة. يرجى إعادة المحاولة.")
        return redirect("learning:chapter_quiz", pk=chapter.pk)

    questions = list(
        Question.objects.filter(id__in=q_ids, chapter=chapter, is_active=True).prefetch_related("options")
    )
    q_map = {str(q.id): q for q in questions}
    ordered_questions = [q_map[qid] for qid in q_ids if qid in q_map]

    if len(ordered_questions) != len(q_ids):
        messages.error(request, "حدث خطأ في التحقق من الأسئلة. أعد المحاولة من جديد.")
        return redirect("learning:chapter_quiz", pk=chapter.pk)

    answers = {}
    error_qids = set()
    for qid in q_ids:
        sel = (request.POST.get(f"q_{qid}") or "").strip()
        if not sel:
            error_qids.add(qid)
        else:
            answers[qid] = sel

    if error_qids:
        messages.error(request, "من فضلك أجب على جميع الأسئلة.")
        return render(request, "learning/chapter_quiz.html", {
            "chapter": chapter,
            "questions": ordered_questions,
            "error_qids": error_qids,
            "answers": answers,
        })

    results = []
    score = 0
    for q in ordered_questions:
        sel_opt_id = answers[str(q.id)]
        selected = None
        correct_opt = None
        for opt in q.options.all():
            if str(opt.id) == str(sel_opt_id):
                selected = opt
            if opt.is_correct:
                correct_opt = opt
        is_correct = bool(selected and selected.is_correct)
        if is_correct:
            score += 1
        results.append({
            "question": q,
            "selected": selected,
            "correct": correct_opt,
            "is_correct": is_correct,
        })

    total = len(ordered_questions)
    return render(request, "learning/chapter_quiz_result.html", {
        "chapter": chapter,
        "results": results,
        "score": score,
        "total": total,
    })





def _send_contact_email(obj):
    to_admin = getattr(settings, "CONTACT_EMAIL", None) or getattr(settings, "DEFAULT_FROM_EMAIL", None)
    if not to_admin:
        return
    subj = f"[تواصل] {obj.subject} — {obj.name}"
    txt = (
        f"اسم: {obj.name}\n"
        f"بريد: {obj.email}\n"
        f"واتساب: {obj.whatsapp or '-'}\n"
        f"الموضوع: {obj.subject}\n\n"
        f"الرسالة:\n{obj.message}\n"
    )
    html = (
        f"<p><strong>اسم:</strong> {obj.name}</p>"
        f"<p><strong>بريد:</strong> {obj.email}</p>"
        f"<p><strong>واتساب:</strong> {obj.whatsapp or '-'}</p>"
        f"<p><strong>الموضوع:</strong> {obj.subject}</p>"
        f"<hr><p style='white-space:pre-wrap'>{obj.message}</p>"
    )
    msg = EmailMultiAlternatives(
        subject=subj,
        body=txt,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
        to=[to_admin],
    )
    msg.attach_alternative(html, "text/html")
    try:
        msg.send()
    except Exception:
        pass  # ما نوقفش المستخدم

def contact(request):
    is_htmx = request.headers.get("HX-Request") == "true"

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            obj = form.save()
            _send_contact_email(obj)
            if is_htmx:
                return render(request, "learning/_contact_success.html", {"name": obj.name})
            messages.success(request, "تم استلام رسالتك وسنعود إليك قريبًا 🙏")
            return redirect(reverse("learning:contact"))
        else:
            if is_htmx:
                return render(request, "learning/_contact_form.html", {"form": form})

    # GET
    if is_htmx:
        return render(request, "learning/_contact_form.html", {"form": ContactForm()})
    return render(request, "learning/contact.html", {"form": ContactForm()})




import json

def faq_page(request):
    faqs = FAQ.objects.filter(is_active=True).order_by("category", "order_index", "id")

    # JSON-LD (FAQPage) لتحسين الظهور في جوجل
    items = []
    for f in faqs:
        items.append({
            "@type": "Question",
            "name": f.question,
            "acceptedAnswer": {"@type": "Answer", "text": f.answer},
        })
    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": items,
    }

    # تجميع بالتصنيف (اختياري)
    grouped = {}
    for f in faqs:
        grouped.setdefault(f.category or "عام", []).append(f)

    return render(request, "learning/faq.html", {
        "grouped": grouped,
        "schema_json": json.dumps(schema, ensure_ascii=False),
    })
    
    
    
    
def about_us( request):
    return render ( request , "learning/about_us.html")