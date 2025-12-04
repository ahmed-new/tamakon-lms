from django.urls import path
from . import views
from . import bunny_api

app_name = "learning"

urlpatterns = [
    path("", views.home, name="home"),
     path("faq/", views.faq_page, name="faq"),
    path("contact/", views.contact, name="contact"),
    path("courses/", views.course_list, name="course_list"),
    path("my-courses/", views.my_courses, name="my_courses"),
    path("about-us/", views.about_us, name="about_us"),

    path("courses/<slug:slug>/", views.course_detail, name="course_detail"),

    path("lesson/<int:pk>/", views.lesson_detail, name="lesson_detail"),
    path("lesson/<int:pk>/complete/", views.complete_lesson, name="complete_lesson"),

    path("gate/lesson/<int:pk>/", views.preview_gate, name="preview_gate"),

    path("chapters/<int:pk>/quiz/", views.chapter_quiz, name="chapter_quiz"),
    path("chapters/<int:pk>/quiz/submit/", views.chapter_quiz_submit, name="chapter_quiz_submit"),


    path("uploader/", bunny_api.bunny_upload_page, name="bunny_uploader"),  # ← صفحة الرفع
    path("api/bunny/start", bunny_api.start_bunny_upload, name="bunny_start"),
    path("api/bunny/status/<uuid:video_id>", bunny_api.video_status, name="bunny_status"),

]
