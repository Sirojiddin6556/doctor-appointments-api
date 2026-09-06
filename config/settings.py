"""Настройки Django для API записи пациентов в клинику.

Все значения, зависящие от окружения, берутся из переменных окружения, поэтому
один и тот же образ можно запускать локально, в Docker и в CI.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# --- Основные настройки ------------------------------------------------------

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# --- Приложения --------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # Сторонние приложения.
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    # Приложения проекта.
    "apps.users",
    "apps.doctors",
    "apps.slots",
    "apps.appointments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Отдаёт собранную статику из STATIC_ROOT без DEBUG и без отдельного nginx.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "config.middleware.RequestLoggingMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- База данных -------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "clinic_db"),
        "USER": os.environ.get("POSTGRES_USER", "clinic_user"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "clinic_dev_pass"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "users.User"

# --- Проверка паролей ---------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Язык и время -------------------------------------------------------------

LANGUAGE_CODE = "ru-ru"
# Правило 8: все даты хранятся и возвращаются в UTC.
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Статические файлы --------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ----------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "config.pagination.ConfigurablePageNumberPagination",
    "PAGE_SIZE": int(os.environ.get("DRF_PAGE_SIZE", "20")),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Правило 8: принимаем и возвращаем даты ISO 8601 с часовым поясом.
    "DATETIME_FORMAT": "iso-8601",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.ScopedRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # Ограничение частоты входа защищает endpoint от перебора паролей.
        "login": os.environ.get("LOGIN_THROTTLE_RATE", "5/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_LIFETIME_MINUTES", "15"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=int(os.environ.get("JWT_REFRESH_LIFETIME_DAYS", "7"))
    ),
    "ROTATE_REFRESH_TOKENS": True,
    # Старый refresh кладётся в blacklist после ротации и при logout,
    # поэтому украденный/использованный токен нельзя применить повторно.
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# --- Безопасность в production (DEBUG=False) --------------------------------
# Локально и в CI DEBUG=True, поэтому эти жёсткие настройки не мешают
# разработке, но включаются автоматически на боевом профиле.
if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

SPECTACULAR_SETTINGS = {
    "TITLE": "API записи в клинику",
    "DESCRIPTION": "REST API для записи пациентов к врачам.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "русский": {
            "format": "{asctime} | {levelname} | {name} | {message}",
            "style": "{",
        },
    },
    "handlers": {
        "консоль": {
            "class": "logging.StreamHandler",
            "formatter": "русский",
        },
    },
    "loggers": {
        "apps": {
            "handlers": ["консоль"],
            "level": os.environ.get("LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "django": {
            "handlers": ["консоль"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
