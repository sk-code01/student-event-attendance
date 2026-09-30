from django.contrib import admin

from .models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ['id', 'participation', 'status', 'current_version', 'created_at']
    list_filter = ['status']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(EvidenceVersion)
class EvidenceVersionAdmin(admin.ModelAdmin):
    list_display = ['id', 'evidence', 'version_number', 'submitted_by', 'submitted_at']
    readonly_fields = ['created_at']


@admin.register(EvidenceCapture)
class EvidenceCaptureAdmin(admin.ModelAdmin):
    list_display = ['id', 'evidence_version', 'capture_role', 'validation_status', 'created_at']
    list_filter = ['capture_role', 'validation_status']
    readonly_fields = ['created_at']


@admin.register(EvidenceVerification)
class EvidenceVerificationAdmin(admin.ModelAdmin):
    list_display = ['id', 'evidence_version', 'reviewer', 'decision', 'is_event_coordinator_override', 'created_at']
    list_filter = ['decision', 'is_event_coordinator_override']
    readonly_fields = ['created_at', 'updated_at']
