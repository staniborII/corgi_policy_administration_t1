from django.urls import path

from apps.reconciliation import views

urlpatterns = [
    path("broker-statements/", views.BrokerStatementListView.as_view(), name="broker-statement-list"),
    path("broker-statements/<int:pk>/", views.BrokerStatementDetailView.as_view(), name="broker-statement-detail"),
    path("runs/", views.ReconciliationRunListView.as_view(), name="reconciliation-run-list"),
    path("runs/<int:pk>/", views.ReconciliationRunDetailView.as_view(), name="reconciliation-run-detail"),
    path("breaks/", views.ReconciliationBreakListView.as_view(), name="reconciliation-break-list"),
    path("breaks/<int:pk>/resolve/", views.ResolveBreakView.as_view(), name="reconciliation-break-resolve"),
]
