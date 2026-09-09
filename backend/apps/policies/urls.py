from django.urls import path

from apps.policies import views

urlpatterns = [
    path("", views.PolicyListView.as_view(), name="policy-list"),
    path("jurisdictions/", views.JurisdictionListView.as_view(), name="jurisdiction-list"),
    path("<int:pk>/", views.PolicyDetailView.as_view(), name="policy-detail"),
    path("<int:pk>/as-of/", views.PolicyAsOfView.as_view(), name="policy-as-of"),
]
