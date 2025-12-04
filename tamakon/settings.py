

from pathlib import Path
import os
from decouple import config



# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-c=@1x)d%pjo^_g6qu-f#*as3(l%y5%@i9(ry-&3n-%pe+d9*!b'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "tamakon.online",
    "www.tamakon.online",
]



# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    "users.apps.UsersConfig",
    "learning",
    "commerce.apps.CommerceConfig",
    "django_celery_beat",
    "marketing",
    "ckeditor",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'tamakon.middleware.LastSeenMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    "users.middleware.EnsureDeviceCookieMiddleware",
]


BUNNY_LIBRARY_ID = config("BUNNY_LIBRARY_ID")
BUNNY_API_KEY = config("BUNNY_API_KEY")



# CSRF_COOKIE_SECURE = True
# SESSION_COOKIE_SECURE = True



AUTH_USER_MODEL = "users.User"

ROOT_URLCONF = 'tamakon.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR,"templates")],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                 "tamakon.context_processors.enrollment_warnings",
            ],
        },
    },
]

WSGI_APPLICATION = 'tamakon.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': BASE_DIR / 'db.sqlite3',
#     }
# }

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

# اللغة والتوقيت
LANGUAGE_CODE = "ar"

TIME_ZONE = "Africa/Cairo"

USE_I18N = True
USE_TZ = True

# celery settings

CELERY_BROKER_URL = "redis://127.0.0.1:6379/0"
CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/1"
CELERY_TIMEZONE = "Africa/Cairo"
CELERY_ENABLE_UTC = False



from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "salary-day-reminders-daily-09:00": {
        "task": "commerce.tasks.send_salary_day_reminders",
        # هنشغّلها يوميًا 09:00 بتوقيت القاهرة — والدالة هي اللي بتشيّك: 26 أو force
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "emails", "expires": 60*60},  # اختياري
    },
        "absence-14-days-daily": {
            "task": "notifications.tasks.send_two_weeks_absence_alerts",
            "schedule": crontab(hour=9, minute=30),  # يوميًا 09:00 صباحًا بتوقيت السيرفر
        },
         "mark-overdue-installments-daily": {
        "task": "commerce.tasks.mark_overdue_installments",
        "schedule": crontab(hour=8, minute=0),
        "options": {"expires": 60*60},
    },
    "suspend-overdue-60d-daily": {
        "task": "commerce.tasks.suspend_enrollments_with_overdue_60d",
        "schedule": crontab(hour=8, minute=10),
        "options": {"expires": 60*60},
    },
    "reactivate-when-no-overdue60-daily": {
        "task": "commerce.tasks.reactivate_when_no_overdue_60d",
        "schedule": crontab(hour=8, minute=20),
        "options": {"expires": 60*60},
    },
    
    "auto-unfreeze-enrollments-daily": {
        "task": "commerce.tasks.auto_unfreeze_enrollments",
        "schedule": crontab(hour=8, minute=25),
        "options": {"expires": 60*60},
    },
}


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

BASE_DIR = Path(__file__).resolve().parent.parent

# مسار URL اللي هيتعرض فيه الملفات
STATIC_URL = "/static/"

# أماكن البحث عن الملفات أثناء التطوير
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# مسار تخزين الملفات المجمّعة لما نعمل collectstatic (وقت الإنتاج)
STATIC_ROOT = BASE_DIR / "staticfiles"

STATIC_URL = 'static/'

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'




# العملة الافتراضية
COMMERCE_CURRENCY = "USD"   # أو "SAR" لو شغّال في السعودية

# PayPal
PAYPAL_ENV = "live"      # أو "live" عند الإطلاق
PAYPAL_CLIENT_ID = config("PAYPAL_CLIENT_ID")
PAYPAL_SECRET= config("PAYPAL_SECRET")


# Email sending
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = "customer-care@tamakon.online"
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = "تمكن <customer-care@tamakon.online"

PAYPAL_SECRET_ENC_KEY= config("PAYPAL_SECRET_ENC_KEY")





SITE_URL = "https://tamakon.online"

