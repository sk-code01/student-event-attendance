"""Mounted three times from config/api_urls.py so each capability has its own
top-level namespace (`/recommendations/`, `/anomalies/`, `/engagement/`), as
the SRS API layout specifies, while sharing one app."""

from django.urls import path

from .views import AnomaliesView, EngagementView, RecommendationsView

recommendation_urls = [path('', RecommendationsView.as_view(), name='ai-recommendations')]
anomaly_urls = [path('', AnomaliesView.as_view(), name='ai-anomalies')]
engagement_urls = [path('', EngagementView.as_view(), name='ai-engagement')]
