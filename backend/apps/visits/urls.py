"""Visits app URL configuration."""

from django.urls import path

from .views import VisitCancelView, VisitDetailView, VisitListCreateView

app_name = "visits"

urlpatterns = [
    path("", VisitListCreateView.as_view(), name="visit-list"),
    path("<int:pk>/", VisitDetailView.as_view(), name="visit-detail"),
    path("<int:pk>/cancel/", VisitCancelView.as_view(), name="visit-cancel"),
]
