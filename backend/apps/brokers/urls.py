from django.urls import path

from apps.brokers import views

urlpatterns = [
    path("", views.BrokerListView.as_view(), name="broker-list"),
    path("<int:pk>/", views.BrokerDetailView.as_view(), name="broker-detail"),
    path("<int:pk>/kyb/", views.BrokerKYBInitiateView.as_view(), name="broker-kyb-initiate"),
]
