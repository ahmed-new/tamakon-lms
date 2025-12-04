import base64, requests
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import Coupon, Payment
from .models import Enrollment, EnrollmentInstallment
from learning.models import Course
from .utils import ensure_part_access_plan  # الذي أنشأناه سابقًا

# ----- التسعير -----

def resolve_coupon(code: str, course: "Course|None" = None):
    """
    يرجّع الكوبون لو صالح.
    - لو تم تمرير course: يتحقق من الصلاحية لدورة بعينها (وملكية المدرّس).
    - لو لم يتم تمرير course: يتحقق بس من الصلاحية الزمنية (توافقًا مع السلوك القديم).
    """
    if not code:
        return None

    code = code.strip()
    try:
        c = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return None

    if course is not None:
        # احترام سكوب المدرّس/الدورات
        return c if c.is_valid_for(course=course) else None
    else:
        # توافق قديم
        return c if c.is_active_now() else None




def price_for_course(course: Course, mode: str, user, coupon_code: str = "", step: int | None = None):
    """
    يرجّع dict شامل: {'amount', 'discount', 'final', 'coupon'}
    - FULL: السعر = course.price بالكامل
    - INST: السعر = قيمة القسط المطلوب سداده (القسط المستحق التالي أو step المحدد)
    """
    amount = Decimal(course.price or 0)
    if mode == "installment":
        # إيجاد الاشتراك للمستخدم إن وُجد (أو None)
        enr = Enrollment.objects.filter(user=user, course=course).first()
        if not enr:
            # لو أول دفع بالقسط → سننشئ Enrollment لاحقًا وسيتم توليد الأقساط بالإشارة
            pass
        # حدّد القسط المراد دفعه
        inst_qs = None
        if enr:
            if step:
                inst_qs = enr.installments.filter(step=step)
            else:
                inst_qs = enr.installments.filter(status=EnrollmentInstallment.Status.DUE).order_by("step")
        # لو أقساط غير موجودة بعد (اشتراك جديد) نعتمد قسمة السعر على installments_count:
        if enr and inst_qs and inst_qs.exists():
            amount = inst_qs.first().amount
        else:
            cnt = course.installments_count or 1
            amount = (Decimal(course.price or 0) / Decimal(cnt)).quantize(Decimal("0.01"))
    # كوبون
    coupon = resolve_coupon(coupon_code, course=course) if coupon_code else None
    if coupon:
        final, disc = coupon.apply_for_course(amount, course=course)
    else:
        final, disc = amount, Decimal("0.00")
    return {"amount": amount, "discount": disc, "final": final, "coupon": coupon}

# ----- PayPal REST -----

def paypal_base():
    env = getattr(settings, "PAYPAL_ENV", "sandbox").lower()
    return "https://api-m.sandbox.paypal.com" if env == "sandbox" else "https://api-m.paypal.com"


def _credentials_for_course(course):
    """
    يرجّع (client_id, secret) لصاحب الدورة إن وُجد وإلا يعود لإعدادات المنصة.
    """
    instr = getattr(course, "instructor", None)
    if instr and instr.paypal_client_id and instr.paypal_secret_encrypted:
        return instr.paypal_client_id, instr.get_paypal_secret()
    return settings.PAYPAL_CLIENT_ID, settings.PAYPAL_SECRET


def paypal_client_id(course=None):
    if course is None:
        return settings.PAYPAL_CLIENT_ID
    cid, _sec = _credentials_for_course(course)
    return cid


def paypal_access_token(course=None):
    cid, sec = _credentials_for_course(course)
    b = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    resp = requests.post(
        paypal_base()+"/v1/oauth2/token",
        headers={"Authorization": f"Basic {b}"},
        data={"grant_type": "client_credentials"},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def paypal_create_order(total, currency, return_url, cancel_url, description="Course payment",*, course=None):

    token = paypal_access_token(course=course)

    payload = {
        "intent": "CAPTURE",
        "purchase_units": [
            {
                "amount": {
                    "currency_code": currency,
                    "value": f"{total:.2f}"
                },
                "description": description[:127],
            }
        ],
        "application_context": {
            "brand_name": "Tamakon",
            "return_url": return_url,
            "cancel_url": cancel_url,
            "user_action": "PAY_NOW",
            "shipping_preference": "NO_SHIPPING",
            # اختياري:
            # "landing_page": "LOGIN"
        }
    }
    r = requests.post(
        paypal_base() + "/v2/checkout/orders",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload, timeout=30
    )
    r.raise_for_status()
    data = r.json()

    # (اختياري) رجّع approve_url جاهز
    approve_url = next((lk.get("href") for lk in data.get("links", []) if lk.get("rel") == "approve"), None)
    return {"raw": data, "approve_url": approve_url}


import requests

def paypal_get_order(order_id, *, course=None):
    token = paypal_access_token(course=course)
    r = requests.get(
        paypal_base() + f"/v2/checkout/orders/{order_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30
    )
    r.raise_for_status()
    return r.json()



def paypal_safe_capture(order_id, *, course=None):
    """
    يحاول يعمل capture بأمان:
    - لو COMPLETED يرجّع الأوردر كما هو (بدون POST).
    - لو APPROVED يعمل POST /capture.
    - لو 422 وفيها ORDER_ALREADY_CAPTURED يرجّع get_order() كنجاح.
    - لو PAYER_ACTION_REQUIRED يرجّع dict فيه 'needs_approval': True + approve_url.
    - في باقي الحالات يرجّع {'error': '...'}.
    """
    token = paypal_access_token(course=course)

    # 1) افحص الحالة أولًا
    try:
        order = paypal_get_order(order_id,course=course)
    except requests.HTTPError as e:
        return {"error": f"get_order_failed: {e.response.status_code} {e.response.text}"}
    status = order.get("status")

    if status == "COMPLETED":
        return {"ok": True, "data": order, "already_completed": True}

    if status == "PAYER_ACTION_REQUIRED":
        # أعد التوجيه للموافقة من جديد
        approve_url = None
        for lk in order.get("links", []):
            if lk.get("rel") == "approve":
                approve_url = lk.get("href")
                break
        return {"needs_approval": True, "approve_url": approve_url, "data": order}

    if status != "APPROVED":
        return {"error": f"order_not_ready_for_capture: status={status}", "data": order}

    # 2) نفّذ الكابتشر
    try:
        r = requests.post(
            paypal_base() + f"/v2/checkout/orders/{order_id}/capture",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30
        )
        if not r.ok:
            # حاول نفهم التفاصيل
            try:
                err = r.json()
            except Exception:
                err = {"raw": r.text}
            # حالات شائعة:
            # ORDER_ALREADY_CAPTURED → اعتبره نجاح وجِب البيانات من get_order
            details = err.get("details") or []
            issue = details[0].get("issue") if details else None
            if issue == "ORDER_ALREADY_CAPTURED":
                order2 = paypal_get_order(order_id,course=course)
                return {"ok": True, "data": order2, "already_completed": True}
            return {"error": f"capture_http_{r.status_code}", "details": err}
        data = r.json()
        return {"ok": True, "data": data}
    except requests.RequestException as e:
        return {"error": f"capture_request_failed: {e}"}


