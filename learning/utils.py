# learning/utils.py
from django.db.models import Count
from .models import Lesson, LessonView
from commerce.models import (
    Enrollment,
    EnrollmentInstallment,
    EnrollmentPartAccess,
)





# ====== اشتراك نشط للدورة ======
def get_active_enrollment(user, course):
    """يرجّع اشتراك نشط للمستخدم في الدورة أو None."""
    if not user or not user.is_authenticated:
        return None
    try:
        enr = Enrollment.objects.get(user=user, course=course)
    except Enrollment.DoesNotExist:
        return None
    return enr if enr.is_active_for_access() else None


# ====== أقساط مدفوعة ======
def paid_installments_count(enrollment: Enrollment) -> int:
    """عدد الأقساط المدفوعة فعليًا لهذا الاشتراك."""
    return enrollment.installments.filter(
        status=EnrollmentInstallment.Status.PAID
    ).count()






# ====== الأجزاء المفتوحة للاشتراك ======
def unlocked_parts_for_enrollment(enrollment: Enrollment):
    """
    - لو الاشتراك لا يملك أي تعريفات PartAccess => الدورة كلها مفتوحة (نرجّع None).
    - غير ذلك: نرجّع set من IDs للأجزاء المفتوحة حيث unlock_step <= عدد الأقساط المدفوعة.
    """
    qs = enrollment.part_access.all()
    if not qs.exists():
        return None  # Full access
    paid_count = paid_installments_count(enrollment)
    allowed_part_ids = set(
        qs.filter(unlock_step__lte=paid_count).values_list("part_id", flat=True)
    )
    return allowed_part_ids






# ====== صلاحيات الوصول ======
def user_has_part_access(user, part) -> bool:
    """
    يحتاج اشتراك نشط للدورة:
    - إن لم يوجد أي PartAccess => وصول كامل لكل الأجزاء.
    - إن وُجد PartAccess => الجزء مسموح لو ضمن unlocked_parts.
    """
    enr = get_active_enrollment(user, part.course)
    if not enr:
        return False
    allowed = unlocked_parts_for_enrollment(enrollment=enr)
    if allowed is None:  # Full-course access
        return True
    return part.id in allowed





def user_has_lesson_access(user, lesson) -> bool:
    """وصول الدرس غير المجاني مبني على الجزء التابع له."""
    return user_has_part_access(user, lesson.topic.chapter.part)






def user_has_course_access(user, course) -> bool:
    """
    إبقاء هذه الدالة للتوافق الخلفي: True لو الاشتراك نشط (بغضّ النظر عن الأجزاء).
    استخدم user_has_part_access للمنع/السماح الفعلي على المحتوى.
    """
    return get_active_enrollment(user, course) is not None







# ====== نسبة التقدّم ======
def course_progress_percent(user, course) -> float:
    """
    يحسب نسبة التقدّم على مستوى كل دروس الدورة (بغضّ النظر عن الأجزاء المفتوحة).
    = عدد الدروس التي أتمّها المستخدم / إجمالي دروس الدورة × 100
    """
    # إجمالي كل دروس الدورة
    total = Lesson.objects.filter(
        topic__chapter__part__course=course
    ).count()
    if total == 0:
        return 0.0

    # الدروس المكتملة بواسطة المستخدم (سواء كانت من جزء مفتوح أو لا)
    done = LessonView.objects.filter(
        user=user,
        lesson__topic__chapter__part__course=course
    ).count()

    return round((done / total) * 100.0, 2)
