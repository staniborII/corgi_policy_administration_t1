from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/brokers/", include("apps.brokers.urls")),
    path("api/policies/", include("apps.policies.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
]
