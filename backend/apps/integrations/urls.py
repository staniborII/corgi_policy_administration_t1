from django.urls import path

from apps.integrations import views

urlpatterns = [
    path("webhooks/persona/", views.PersonaWebhookView.as_view(), name="persona-webhook"),
]
