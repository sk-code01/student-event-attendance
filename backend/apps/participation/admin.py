from django.contrib import admin

from .models import Participation


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'event', 'status', 'submitted_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'event__title')
