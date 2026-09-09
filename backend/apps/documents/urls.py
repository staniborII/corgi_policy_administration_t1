from django.urls import path

from apps.documents import views

urlpatterns = [
    path("policy/<int:policy_id>/declarations/", views.DeclarationsDownloadView.as_view(), name="declarations-pdf"),
    path(
        "policy/<int:policy_id>/endorsement-schedule/",
        views.EndorsementScheduleDownloadView.as_view(),
        name="endorsement-schedule-pdf",
    ),
]
