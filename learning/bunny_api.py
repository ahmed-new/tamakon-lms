# learning/bunny_api.py
import time, hashlib, requests
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseServerError
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.shortcuts import render
from .models import VideoAsset
from django.urls import reverse




BUNNY_API = "https://video.bunnycdn.com"

def staff_only(user):  # اسمح للأدمن/الستاف/المدرّب
    return bool(
        user.is_staff
        or getattr(user, "role", "") in ("admin", "trainer")
    )

@login_required
@user_passes_test(staff_only)
def bunny_upload_page(request):
    return render(request, "learning/bunny_upload.html")





@login_required
@user_passes_test(staff_only)
@require_POST
def start_bunny_upload(request):
    title = (request.POST.get("title") or "").strip()
    if not title:
        return HttpResponseBadRequest("title is required")

    lib = getattr(settings, "BUNNY_LIBRARY_ID", None)
    api_key = getattr(settings, "BUNNY_API_KEY", None)
    if not lib:
        return HttpResponseServerError("Missing BUNNY_LIBRARY_ID")
    if not api_key:
        return HttpResponseServerError("Missing BUNNY_API_KEY")

    # 1) إنشاء الفيديو على Bunny
    try:
        r = requests.post(
            f"{BUNNY_API}/library/{lib}/videos",
            headers={"AccessKey": api_key, "Content-Type": "application/json"},
            json={"title": title},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        return HttpResponseServerError(f"Bunny create failed: {getattr(e.response,'text',str(e))}")

    video_id = (data or {}).get("guid")
    if not video_id:
        return HttpResponseServerError("Create Video failed: missing guid")

    # 2) خزّن/حدّث VideoAsset فورًا (علشان ما نضيعش الـ video_id)
    asset, created = VideoAsset.objects.get_or_create(
        owner=request.user,
        provider=VideoAsset.Provider.VIMEO,   # نعرضه كـ Vimeo زي ما اتفقنا
        video_id=str(video_id),
        defaults={"title": title, "encode_progress": 0, "meta": data},
    )
    if not created:
        upd = []
        if title and asset.title != title:
            asset.title = title
            upd.append("title")
        asset.meta = data
        upd.append("meta")
        if upd:
            asset.save(update_fields=upd + ["updated_at"])

    # 3) اصنع توقيع TUS **دائمًا** خارج أي شرط
    expire = int(time.time()) + 15 * 60  # صلاحية 15 دقيقة
    payload = f"{lib}{api_key}{expire}{video_id}".encode("utf-8")
    signature = hashlib.sha256(payload).hexdigest()

      # 4) حضّر رابط الأدمن لفتح السجل مباشرة
    admin_url = reverse("admin:learning_videoasset_change", args=[asset.pk])
    
    # 4) رجّع الإعدادات
    return JsonResponse({
        "uploadEndpoint": "https://video.bunnycdn.com/tusupload",
        "libraryId": lib,
        "videoId": video_id,
        "signature": signature,
        "expire": expire,
        "embedUrl": f"https://iframe.mediadelivery.net/embed/{lib}/{video_id}",
        "adminUrl": admin_url, 
    })




# learning/bunny_api.py (اختياري)
@login_required
@user_passes_test(staff_only)
def video_status(request, video_id):
    lib = settings.BUNNY_LIBRARY_ID
    r = requests.get(
        f"{BUNNY_API}/library/{lib}/videos/{video_id}",
        headers={"AccessKey": settings.BUNNY_API_KEY},
        timeout=30,
    )
    return JsonResponse(r.json(), status=r.status_code)
