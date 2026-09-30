from django.contrib import admin

from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'event_date', 'conducting_college', 'department', 'created_by')
    list_filter = ('status', 'category', 'conducting_college')
    search_fields = ('title', 'venue')
