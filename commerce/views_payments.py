from decimal import Decimal, ROUND_HALF_UP
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render ,redirect
from django.urls import reverse
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from learning.models import Course
from .models import Payment, Enrollment, EnrollmentInstallment , Coupon
from .utils_payments import price_for_course, paypal_create_order, paypal_safe_capture, paypal_get_order ,paypal_client_id
from .utils import ensure_part_access_plan
from django.db.models import F
from commerce.emails import send_enrollment_email




@login_required
def checkout_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    mode = request.GET.get("mode", "full")  # "full" or "installment"
    step = request.GET.get("step")
    try:
        step = int(step) if step else None
    except:
        step = None

    return render(request, "commerce/checkout.html", {
        "course": course,
        "mode": mode,
        "step": step,
        "paypal_client_id": paypal_client_id(course),  # ← مهم
        "currency": getattr(settings, "COMMERCE_CURRENCY", "USD"),
    })



@login_required
@require_POST
def paypal_quote_view(request, slug):
    """
    يرجّع معاينة التسعير بدون إنشاء Payment:
    {amount, final, discount, coupon_valid, coupon_code, currency}
    """
    course = get_object_or_404(Course, slug=slug)
    mode = request.POST.get("mode")
    step = request.POST.get("step")
    coupon_code = (request.POST.get("coupon") or "").strip()

    try:
        step = int(step) if step else None
    except Exception:
        step = None

    pr = price_for_course(course, mode, request.user, coupon_code, step)
    # نفس العملة المستخدمة في الدفع
    currency = getattr(settings, "COMMERCE_CURRENCY", "USD")

    return JsonResponse({
        "amount": f"{Decimal(pr['amount']):.2f}",
        "discount": f"{Decimal(pr['discount']):.2f}",
        "final": f"{Decimal(pr['final']):.2f}",
        "coupon_code": coupon_code or None,
        "coupon_valid": bool(pr.get("coupon")),
        "currency": currency,
    })











from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseServerError
from django.urls import reverse

@login_required
@require_POST
def paypal_create_order_view(request, slug):
    course = get_object_or_404(Course, slug=slug)
    mode = request.POST.get("mode")
    step = request.POST.get("step")
    coupon_code = (request.POST.get("coupon") or "").strip()

    try:
        step = int(step) if step else None
    except Exception:
        step = None

    # السعر النهائي
    pr = price_for_course(course, mode, request.user, coupon_code, step)
    if pr["final"] <= 0:
        return HttpResponseBadRequest("Invalid amount")

    # إنشاء Payment بحالة created
    payment = Payment.objects.create(
        user=request.user,
        course=course,
        mode=Payment.Mode.FULL if mode == "full" else Payment.Mode.INST,
        step=step,
        amount=pr["final"],
        currency=getattr(settings, "COMMERCE_CURRENCY", "USD"),
        coupon=pr["coupon"],
        discount_amount=pr["discount"],
    )

    # URLs
    ret_url = request.build_absolute_uri(
        reverse("commerce:paypal_capture") + f"?pid={payment.id}"
    )
    cancel_qs = []
    if mode:
        cancel_qs.append(f"mode={mode}")
    if step is not None:
        cancel_qs.append(f"step={step}")
    cancel_base = reverse("commerce:checkout", args=[course.slug])
    cancel_url = request.build_absolute_uri(
        cancel_base + (("?" + "&".join(cancel_qs)) if cancel_qs else "")
    )

    # إنشاء الأوردر في باي بال
    order = paypal_create_order(
        total=payment.amount,
        currency=payment.currency,
        return_url=ret_url,
        cancel_url=cancel_url,
        description=f"Tamakon: {course.title} ({mode})",
        course=course, 
    )

    # دلوقتي order = {"raw": {...}, "approve_url": "..."}
    raw = order.get("raw") or {}
    order_id = raw.get("id")
    approve_url = order.get("approve_url")

    if not order_id:
        return HttpResponseServerError("PayPal order create failed (no id).")
    if not approve_url:
        return HttpResponseServerError("PayPal approve link not found.")

    # حفظ بيانات الأوردر
    payment.paypal_order_id = order_id
    payment.raw_response = raw
    payment.save(update_fields=["paypal_order_id", "raw_response"])

    # رجع الاتنين للفرونت
    return JsonResponse({"orderID": order_id, "approve_url": approve_url})



@login_required
def paypal_capture_view(request):
    pid = request.GET.get("pid")
    token_order_id = request.GET.get("token")  # PayPal يرسلها في redirect
    if not pid:
        return HttpResponseBadRequest("Missing pid")

    payment = get_object_or_404(Payment, id=pid, user=request.user)

    # نستخدم token إن وُجد، وإلا fallback للـ id المخزّن
    order_id = token_order_id or payment.paypal_order_id
    if not order_id:
        return HttpResponseBadRequest("Missing order id")

    # محاولة capture بأمان
    result = paypal_safe_capture(order_id, course=payment.course)
    if result.get("error"):
        payment.raw_response = result
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["raw_response", "status"])
        return render(
            request,
            "commerce/checkout_result.html",
            {"ok": False, "payment": payment, "msg": result["error"]},
        )

    # لو محتاج موافقة تاني
    if result.get("needs_approval"):
        approve_url = result.get("approve_url")
        return redirect(approve_url) if approve_url else HttpResponseServerError(
            "Payer action required but no approve URL."
        )

    data = result.get("data") or {}
    payment.raw_response = data

    # --- استخراج الحالة والمبلغ ---
    status = data.get("status")  # APPROVED / COMPLETED / ...
    pu = (data.get("purchase_units") or [{}])[0]

    captures = pu.get("payments", {}).get("captures", [])
    capture_id = None
    cap_amount = cap_currency = None
    if captures:
        cap0 = captures[0]
        capture_id = cap0.get("id")
        amt = cap0.get("amount") or {}
        cap_amount = amt.get("value")
        cap_currency = amt.get("currency_code")

    pu_amount = pu.get("amount") or {}
    pu_value = pu_amount.get("value")
    pu_currency = pu_amount.get("currency_code")

    value = cap_amount or pu_value
    currency = cap_currency or pu_currency

    if value is None or currency is None:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["raw_response", "status"])
        return render(
            request,
            "commerce/checkout_result.html",
            {"ok": False, "payment": payment, "msg": f"missing amount (status={status})"},
        )

    try:
        pay_val = payment.amount.quantize(Decimal("0.01"))
        got_val = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if got_val != pay_val:
            raise ValueError(f"amount_mismatch got={got_val} expected={pay_val}")
        if (currency or "").upper() != (payment.currency or "").upper():
            raise ValueError(f"currency_mismatch got={currency} expected={payment.currency}")
    except Exception as e:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["raw_response", "status"])
        return render(
            request,
            "commerce/checkout_result.html",
            {"ok": False, "payment": payment, "msg": str(e)},
        )

    # ✅ الدفع ناجح
    if status == "COMPLETED" or capture_id:
        from django.db import transaction
        from django.db.models import F
        from .models import Coupon

        with transaction.atomic():
            # اقفل الصف وتأكد ما نزودش الكوبون أو نعيد الـ CAPTURE مرتين
            payment = Payment.objects.select_for_update().get(pk=payment.pk)

            first_time_captured = (payment.status != Payment.Status.CAPTURED)

            payment.status = Payment.Status.CAPTURED
            if capture_id:
                payment.paypal_capture_id = capture_id

            # إصلاح الغلطة الإملائية هنا:
            payment.raw_response = data

            if capture_id:
                payment.save(update_fields=["raw_response", "status", "paypal_capture_id"])
            else:
                payment.save(update_fields=["raw_response", "status"])

            # زوّد عداد الكوبون مرة واحدة فقط
            if first_time_captured and payment.coupon_id:
                Coupon.objects.filter(pk=payment.coupon_id).update(used_count=F("used_count") + 1)
    else:
        payment.status = Payment.Status.FAILED
        payment.save(update_fields=["raw_response", "status"])
        return render(request, "commerce/checkout_result.html", {
            "ok": False, "payment": payment, "msg": f"unexpected_status {status}"
        })

    # ---- تطبيق الأثر على الاشتراك/الأقساط ----
    course = payment.course
    if payment.mode == Payment.Mode.FULL:
        enr, _ = Enrollment.objects.get_or_create(
            user=payment.user, course=course,
            defaults={"status": Enrollment.Status.ACTIVE},
        )
        payment.enrollment = enr
        payment.save(update_fields=["enrollment"])

        ensure_part_access_plan(enr, overwrite=False)

        for inst in enr.installments.all():
            if inst.status != EnrollmentInstallment.Status.PAID:
                inst.status = EnrollmentInstallment.Status.PAID
                inst.paid_at = timezone.now()
                inst.save(update_fields=["status", "paid_at"])
    else:
        enr, _ = Enrollment.objects.get_or_create(
            user=payment.user, course=course,
            defaults={"status": Enrollment.Status.ACTIVE},
        )
        ensure_part_access_plan(enr, overwrite=False)

        inst = None
        if payment.step:
            inst = enr.installments.filter(step=payment.step).first()
        if not inst:
            inst = enr.installments.filter(status=EnrollmentInstallment.Status.DUE).order_by("step").first()

        if inst:
            inst.status = EnrollmentInstallment.Status.PAID
            inst.paid_at = timezone.now()
            inst.save(update_fields=["status", "paid_at"])
            payment.installment = inst
            payment.enrollment = enr
            payment.save(update_fields=["installment", "enrollment"])

    # ✅ بعد ما `enr` بقى موجود ومظبوط — ابعت الإيميل هنا
    from commerce.emails import send_enrollment_email
    try:
        site_url = request.build_absolute_uri("/").rstrip("/")
        send_enrollment_email(payment.user, enr, payment, site_url=site_url)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("Failed to send enrollment email: %s", e)

    # صفحة النتيجة
    return render(request, "commerce/checkout_result.html", {
        "ok": True, "payment": payment,
        "redirect_url": reverse("learning:course_detail", args=[payment.course.slug])
    })
