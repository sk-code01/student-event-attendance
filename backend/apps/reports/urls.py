from django.urls import path

from .views import ReportExportView, ReportPreviewView, ReportTypeListView

urlpatterns = [
    path('', ReportTypeListView.as_view(), name='report-types'),
    # The <str:report_type> segment is matched against a closed allowlist in
    # the view; it never reaches the filesystem or an import.
    path('<str:report_type>/', ReportPreviewView.as_view(), name='report-preview'),
    path('<str:report_type>/export/', ReportExportView.as_view(), name='report-export'),
]
