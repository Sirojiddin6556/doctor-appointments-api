from django.contrib import admin

from .models import Slot


@admin.register(Slot)
class SlotAdmin(admin.ModelAdmin):
    list_display = ("id", "doctor", "start_time", "end_time", "is_free")
    list_filter = ("doctor",)
    date_hierarchy = "start_time"
