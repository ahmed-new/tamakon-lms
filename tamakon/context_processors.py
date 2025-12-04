from django.urls import reverse
from commerce.models import Enrollment

def enrollment_warnings(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}

    suspended = (Enrollment.objects
                 .filter(user=user, status=Enrollment.Status.SUSPENDED)
                 .select_related("course"))
    frozen = (Enrollment.objects
              .filter(user=user, status=Enrollment.Status.FROZEN)
              .select_related("course"))

    banners = []
    if suspended.exists():
        # لكل اشتراك معلّق، هنبني لينك course_detail الخاص بيه
        items = [{
            "name": f"{e.course}",
            "url": reverse("learning:course_detail", kwargs={"slug": e.course.slug})
        } for e in suspended]

        banners.append({
            "level": "warning",
            "title": "تم تعليق اشتراكك",
            "text": "لديك اشتراك معلّق بسبب تأخر سداد قسط. لن تتمكن من الوصول للمحتوى لحين السداد.",
            "action_text": "اذهب لصفحة الكورس",
            "action_url": None,  # هنستخدم روابط العناصر نفسها (لكل كورس)
            "items": items,
        })

    if frozen.exists():
        banners.append({
            "level": "info",
            "title": "اشتراكك مجمّد مؤقتًا",
            "text": "هذا الاشتراك تم تجميده مؤقتًا.",
            "action_text": "اذهب لصفحة دوراتي",
            "action_url": reverse("learning:my_courses"),
            "items": [ {"name": f"{e.course}"} for e in frozen ],
        })

    return {"enrollment_banners": banners}
