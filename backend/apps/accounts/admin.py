from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import RegistrationRequest, User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role', 'department', 'is_active', 'is_staff')
    list_filter = ('role', 'department', 'is_active', 'is_staff')
    fieldsets = UserAdmin.fieldsets + (
        ('Role', {'fields': ('role', 'department')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role', {'fields': ('role', 'email', 'department')}),
    )


@admin.register(RegistrationRequest)
class RegistrationRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'department', 'status', 'requested_at', 'reviewed_by', 'reviewed_at')
    list_filter = ('status', 'role', 'department')
    search_fields = ('user__username', 'user__email')
    readonly_fields = ('requested_at',)
