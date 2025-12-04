from django.utils import timezone
from django.utils.deprecation import MiddlewareMixin

class LastSeenMiddleware(MiddlewareMixin):
    def process_request(self, request):
        u = getattr(request, "user", None)
        if not u or not u.is_authenticated:
            return
        # تحديث كل 15 دقيقة فقط لتقليل الكتابة على DB
        act = getattr(u, "activity", None)
        if not act:
            return
        now = timezone.now()
        if (now - act.last_seen).total_seconds() > 15 * 60:
            act.last_seen = now
            act.save(update_fields=["last_seen"])
