from django.urls import path

from apps.policies import views

urlpatterns = [
    path("", views.PolicyListView.as_view(), name="policy-list"),
    path("<int:pk>/", views.PolicyDetailView.as_view(), name="policy-detail"),
]
