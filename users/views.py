# users/views.py
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login ,authenticate ,logout 
from .forms import RegisterForm
from django.shortcuts import resolve_url

def register(request):
    if request.user.is_authenticated:
        messages.info(request, "أنت مسجّل دخول بالفعل.")
        return redirect("/")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, "تم إنشاء الحساب بنجاح. مرحبًا بك في تمكن!")
            login(request, user)  # دخوله مباشرة بعد التسجيل
            return redirect("learning:home")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {"form": form})






def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")  # اسم المسار بتاع الصفحة الرئيسية

    next_url = request.GET.get("next") or request.POST.get("next") or resolve_url("learning:home")

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = (request.POST.get("password") or "").strip()

        user = authenticate(request, username=username, password=password)
        if not user:
            messages.error(request, "بيانات الدخول غير صحيحة.")
            return render(request, "registration/login.html", {"username": username})

        login(request, user)  # لا ترجع قيمة

        if request.user.is_authenticated:
            return redirect(next_url)
        else:
            # السيجنال بتاع الأجهزة غالبًا حط رسالة؛ نحط احتياطيًا
            # messages.error(request, "تم رفض تسجيل الدخول بسبب حد الأجهزة (جهازان فقط).")
            return render(request, "registration/login.html", {"username": username})

    return render(request, "registration/login.html")



def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
    return redirect("/")