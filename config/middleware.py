import logging


logger = logging.getLogger("apps.http")


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
