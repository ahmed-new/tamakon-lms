# users/middleware.py
import uuid
from django.utils.deprecation import MiddlewareMixin

DEVICE_COOKIE_NAME = "device_id"
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # سنتين
DEVICE_COOKIE_SAMESITE = "Lax"  # مناسب للكوكي العادي
# NOTE: لو بتستخدم HTTPS، يفضَّل تفعّل secure=True (هنضبطه من response.set_cookie)

class EnsureDeviceCookieMiddleware(MiddlewareMixin):
    """
    يضمن وجود device_id في الكوكي لكل زائر.
    - لو مش موجود: ينشئ UUID ويثبّته في الكوكي.
    - لا يغيّر أي شيء لو الكوكي موجود بالفعل.
    """

    def process_response(self, request, response):
        device_id = request.COOKIES.get(DEVICE_COOKIE_NAME)
        if not device_id:
            new_id = str(uuid.uuid4())
            # لو مشروعك شغّال HTTPS على الإنتاج، خليه secure=True
            response.set_cookie(
                key=DEVICE_COOKIE_NAME,
                value=new_id,
                max_age=DEVICE_COOKIE_MAX_AGE,
                httponly=True,         # يمنع JS من قراءته
                samesite=DEVICE_COOKIE_SAMESITE,
                secure=False,          # ← غيّرها True على السيرفر مع HTTPS
            )
        return response
