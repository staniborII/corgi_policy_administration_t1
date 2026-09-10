from django.urls import path

from apps.policies import views

urlpatterns = [
    path("", views.PolicyListView.as_view(), name="policy-list"),
    path("jurisdictions/", views.JurisdictionListView.as_view(), name="jurisdiction-list"),
    path("<int:pk>/", views.PolicyDetailView.as_view(), name="policy-detail"),
    path("<int:pk>/as-of/", views.PolicyAsOfView.as_view(), name="policy-as-of"),
    path("<int:pk>/cancel/", views.CancelPolicyView.as_view(), name="policy-cancel"),
    path("<int:pk>/decline/", views.DeclinePolicyView.as_view(), name="policy-decline"),
    path("<int:pk>/update-effective-date/", views.UpdateEffectiveDateView.as_view(), name="policy-update-effective-date"),
]
