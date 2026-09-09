from django.urls import path

from apps.endorsements import views

urlpatterns = [
    path("", views.EndorsementListView.as_view(), name="endorsement-list"),
    path("<int:pk>/", views.EndorsementDetailView.as_view(), name="endorsement-detail"),
    path("<int:pk>/approve/", views.ApproveEndorsementView.as_view(), name="endorsement-approve"),
    path("<int:pk>/apply/", views.ApplyEndorsementView.as_view(), name="endorsement-apply"),
    path("<int:pk>/correct/", views.CorrectEndorsementView.as_view(), name="endorsement-correct"),
]
