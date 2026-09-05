import django_filters

from .models import Doctor


class DoctorFilter(django_filters.FilterSet):
    specialization = django_filters.CharFilter(field_name="specialization", lookup_expr="iexact")
    branch = django_filters.CharFilter(field_name="branch", lookup_expr="iexact")

    class Meta:
        model = Doctor
        fields = ["specialization", "branch"]
