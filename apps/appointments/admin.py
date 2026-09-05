from django.contrib import admin

from .models import Appointment


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "slot", "status", "start_time", "end_time")
    list_filter = ("status",)
    date_hierarchy = "start_time"
    search_fields = ("patient__username",)
