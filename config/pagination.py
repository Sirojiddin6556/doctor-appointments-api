"""Пагинация с настраиваемым размером страницы через query-параметр."""

from rest_framework.pagination import PageNumberPagination


class ConfigurablePageNumberPagination(PageNumberPagination):
    """Как стандартная постраничная пагинация DRF, но клиент может задать
    размер страницы параметром `page_size` (в пределах разумного максимума).
    """

    page_size_query_param = "page_size"
    max_page_size = 100
