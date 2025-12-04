# commerce/utils.py
from typing import Optional
from .models import Enrollment, EnrollmentPartAccess

def ensure_part_access_plan(enrollment: Enrollment, overwrite: bool = False) -> int:
    """
    يضمن وجود خطة فتح أجزاء لهذا الاشتراك.
    - لو overwrite=True يمسح الخطة القديمة ويعيد توليدها.
    - يعتمد على ترتيب الأجزاء في الدورة (order_index).
    - يعمل فقط عندما الدورة تسمح بالأقساط وكان installments_count > 1.
    يرجّع عدد السجلات المُنشأة.
    """
    course = enrollment.course

    if overwrite:
        enrollment.part_access.all().delete()

    # لو عنده خطة بالفعل، لا نعيد توليدها
    if enrollment.part_access.exists():
        return 0

    if not course.allow_installments or course.installments_count <= 1:
        # دورة بدون أقساط → وصول كامل (لا ننشئ خطة)
        return 0

    parts = course.parts.filter(is_active=True).order_by("order_index")
    steps = course.installments_count
    n = min(steps, parts.count())

    objs = []
    for i in range(n):
        objs.append(
            EnrollmentPartAccess(
                enrollment=enrollment,
                part=parts[i],
                unlock_step=i + 1,  # القسط 1 يفتح أول جزء… وهكذا
            )
        )
    EnrollmentPartAccess.objects.bulk_create(objs, ignore_conflicts=True)
    return len(objs)
