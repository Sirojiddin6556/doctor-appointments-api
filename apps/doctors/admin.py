from django.contrib import admin

from .models import Doctor


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "specialization", "branch")
    list_filter = ("specialization", "branch")
    search_fields = ("user__username", "user__first_name", "user__last_name", "specialization")
