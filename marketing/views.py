# marketing/views.py
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.core.mail import EmailMultiAlternatives, get_connection
from django.contrib import messages
from django.conf import settings

from .forms import ComposeEmailForm
from .models import VisitorEmailCampaign, VisitorEmailLog
from commerce.models import Visitor  # عدّل المسار لو موديل الزائر في مكان آخر
from .utils import build_unsubscribe_url, render_personalized, verify_unsubscribe_token

BATCH_SIZE = 100  # حجم الدفعة الواحدة للإرسال بدون Celery


@staff_member_required
def bulk_email_compose(request):
    """
    شاشة واحدة:
      - جدول الزوّار مع checkbox name="selected" لكل صف.
      - فورم تأليف الرسالة: ComposeEmailForm (subject + body_html [+ body_text]).
      - زرين: 'preview' لمعاينة الرسالة على أحد المختارين، و 'start' لبدء الإرسال.
    """
    visitors = Visitor.objects.all().order_by("-created_at")
    form = ComposeEmailForm(request.POST or None)

    if request.method == "POST":
        selected_ids = request.POST.getlist("selected")

        if not selected_ids:
            messages.error(request, "من فضلك اختر واحدًا على الأقل من الجدول.")
            return render(
                request,
                "marketing/bulk_email_compose.html",
                {"visitors": visitors, "form": form},
            )

        if not form.is_valid():
            messages.error(request, "برجاء استكمال العنوان والمحتوى بشكل صحيح.")
            return render(
                request,
                "marketing/bulk_email_compose.html",
                {"visitors": visitors, "form": form},
            )

        subject = (form.cleaned_data["subject"] or "").strip()
        body_html = (form.cleaned_data["body_html"] or "").strip()
        body_text = (form.cleaned_data.get("body_text") or "").strip()

        # معاينة
        if "preview" in request.POST:
            v = Visitor.objects.filter(pk__in=selected_ids).first()
            if not v:
                messages.error(request, "تعذّر العثور على مستهدف للمعاينة.")
                return render(
                    request,
                    "marketing/bulk_email_compose.html",
                    {"visitors": visitors, "form": form},
                )

            ctx = {
                "name": v.name or "صديقنا",
                "email": v.email,
                "site_name": getattr(settings, "SITE_NAME", "منصتك"),
                "unsubscribe_url": build_unsubscribe_url(v.email),
            }
            html_preview, text_preview = render_personalized(body_html, body_text, ctx)

            return render(
                request,
                "marketing/bulk_email_preview.html",
                {
                    "form": form,
                    "visitors": visitors,
                    "sample_to": v.email,
                    "subject": subject,
                    "html_preview": html_preview,
                    "text_preview": text_preview or "(سيتم توليد نصّي تلقائيًا عند الإرسال)",
                    "selected_ids": selected_ids,  # لو هتعمل hidden inputs في صفحة المعاينة
                },
            )

        # بدء الإرسال
        if "start" in request.POST:
            total = Visitor.objects.filter(pk__in=selected_ids).count()
            if total == 0:
                messages.error(request, "القائمة المختارة فارغة.")
                return render(
                    request,
                    "marketing/bulk_email_compose.html",
                    {"visitors": visitors, "form": form},
                )

            camp = VisitorEmailCampaign.objects.create(
                subject=subject,
                body_html=body_html,
                body_text=body_text or "",
                total_targets=total,
                status=VisitorEmailCampaign.Status.SENDING,
                created_by=request.user,
            )

            # خزّن قائمة الـ IDs في الـ session لتجزئة الإرسال على دفعات
            request.session[f"campaign_{camp.id}_ids"] = list(map(int, selected_ids))

            messages.info(request, f"بدأت الحملة #{camp.id}. الإجمالي: {total}")
            return redirect("marketing:bulk_email_send", campaign_id=camp.id)

    # GET
    return render(request, "marketing/bulk_email_compose.html", {"visitors": visitors, "form": form})


@staff_member_required
def bulk_email_send(request, campaign_id: int):
    """
    يرسل الدفعة التالية من القائمة المختارة المخزّنة في الـ session.
    القالب 'marketing/bulk_email_send.html' يحتوي زر POST لإرسال الدفعة التالية.
    """
    camp = VisitorEmailCampaign.objects.get(pk=campaign_id)
    key = f"campaign_{camp.id}_ids"
    id_list = request.session.get(key, [])

    # إن لم يتبقّ IDs، أنهِ الحملة
    if not id_list:
        if camp.status != VisitorEmailCampaign.Status.DONE:
            camp.status = VisitorEmailCampaign.Status.DONE
            camp.save(update_fields=["status"])
        messages.success(request, f"اكتمل الإرسال: {camp.sent_count}/{camp.total_targets}")
        return redirect("marketing:bulk_email_compose")

    # جهّز دفعة IDs
    batch_ids = id_list[:BATCH_SIZE]
    remaining_ids = id_list[BATCH_SIZE:]
    request.session[key] = remaining_ids

    qs = Visitor.objects.filter(pk__in=batch_ids).order_by("id")
    now = timezone.now()

    connection = get_connection()
    connection.open()
    sent_now = 0

    for v in qs:
        # استبعاد غير الموافقين بهدوء وتسجيلهم كفشل بسبب consent
        if not v.consent:
            VisitorEmailLog.objects.create(
                campaign=camp, visitor=v, to_email=v.email,
                status="failed", error="consent=False", sent_at=now
            )
            continue

        try:
            ctx = {
                "name": v.name or "صديقنا",
                "email": v.email,
                "site_name": getattr(settings, "SITE_NAME", "منصتك"),
                "unsubscribe_url": build_unsubscribe_url(v.email),
            }
            html_body, text_body = render_personalized(camp.body_html, camp.body_text, ctx)
            if not text_body:
                from django.utils.html import strip_tags
                text_body = strip_tags(html_body)

            msg = EmailMultiAlternatives(
                subject=camp.subject,
                body=text_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
                to=[v.email],
                connection=connection,
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send(fail_silently=False)

            VisitorEmailLog.objects.create(
                campaign=camp, visitor=v, to_email=v.email,
                status="sent", sent_at=now
            )
            sent_now += 1

        except Exception as e:
            VisitorEmailLog.objects.create(
                campaign=camp, visitor=v, to_email=v.email,
                status="failed", error=str(e), sent_at=now
            )

    connection.close()

    # تحديث تقدّم الحملة
    camp.sent_count = camp.sent_count + sent_now

    if not remaining_ids:
        camp.status = VisitorEmailCampaign.Status.DONE
        camp.save(update_fields=["sent_count", "status"])
        messages.success(request, f"اكتمل الإرسال: {camp.sent_count}/{camp.total_targets}")
        return redirect("marketing:bulk_email_compose")

    camp.save(update_fields=["sent_count"])
    messages.info(request, f"تم إرسال دفعة: {sent_now}. الإجمالي: {camp.sent_count}/{camp.total_targets}")
    return render(request, "marketing/bulk_email_send.html", {"camp": camp, "batch_size": BATCH_SIZE})


def visitor_unsubscribe(request):
    """
    يضبط consent=False للزائر بناءً على توكن آمن في الرابط المرسل داخل البريد.
    """
    token = request.GET.get("t")
    email = verify_unsubscribe_token(token) if token else None
    changed = False

    if email:
        try:
            v = Visitor.objects.get(email=email)
            if v.consent:
                v.consent = False
                v.save(update_fields=["consent"])
                changed = True
        except Visitor.DoesNotExist:
            pass

    return render(request, "marketing/unsubscribe_done.html", {"changed": changed, "email": email})
