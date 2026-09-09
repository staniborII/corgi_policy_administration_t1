from django.urls import path

from apps.reconciliation import views

urlpatterns = [
    path("broker-statements/", views.BrokerStatementListView.as_view(), name="broker-statement-list"),
    path("broker-statements/<int:pk>/", views.BrokerStatementDetailView.as_view(), name="broker-statement-detail"),
]
