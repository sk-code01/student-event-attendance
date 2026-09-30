from django.contrib import admin

from .models import Registration


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('student', 'event', 'status', 'registered_at', 'cancelled_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'event__title')
