"""Journal app URL configuration."""

from django.urls import path

from .views import (
    AddendumCreateView,
    AuditListView,
    EntryDetailView,
    EntryListCreateView,
    EntrySubmitView,
    PhotoFileView,
    PhotoUploadView,
)

app_name = "journal"

urlpatterns = [
    path("entries/", EntryListCreateView.as_view(), name="entry-list"),
    path("entries/<int:pk>/", EntryDetailView.as_view(), name="entry-detail"),
    path("entries/<int:pk>/submit/", EntrySubmitView.as_view(), name="entry-submit"),
    path("entries/<int:pk>/addenda/", AddendumCreateView.as_view(), name="entry-addenda"),
    path("entries/<int:pk>/photos/", PhotoUploadView.as_view(), name="entry-photos"),
    path("photos/<int:pk>/<str:variant>/", PhotoFileView.as_view(), name="photo-file"),
    path("audit/", AuditListView.as_view(), name="audit-list"),
]
