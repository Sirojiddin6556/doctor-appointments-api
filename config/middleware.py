import logging


logger = logging.getLogger("apps.http")

# Строгий CSP для SPA: скрипты и стили только свои, шрифты — Google Fonts,
# запросы (fetch) — только на свой origin. Убирает возможность вынести
# украденный через XSS токен на чужой домен.
_SPA_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
# Пути, где живёт сторонний UI (Swagger, Django admin) с инлайновыми
# скриптами/стилями — на них строгий CSP не накладываем.
_CSP_EXEMPT_PREFIXES = ("/api/docs", "/api/schema", "/admin", "/static")


class SecurityHeadersMiddleware:
    """Добавляет Content-Security-Policy к страницам приложения."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith(_CSP_EXEMPT_PREFIXES):
            response.setdefault("Content-Security-Policy", _SPA_CSP)
        return response


class RequestLoggingMiddleware:
    """Логирует начало и результат каждого HTTP-запроса."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        пользователь = getattr(request, "user", None)
        имя = getattr(пользователь, "username", "аноним") or "аноним"
        logger.info("Начат запрос %s %s, пользователь: %s", request.method, request.path, имя)

        response = self.get_response(request)

        logger.info(
            "Завершен запрос %s %s со статусом %s",
            request.method,
            request.path,
            response.status_code,
        )
        return response