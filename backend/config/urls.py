from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/brokers/", include("apps.brokers.urls")),
    path("api/policies/", include("apps.policies.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/endorsements/", include("apps.endorsements.urls")),
    path("api/documents/", include("apps.documents.urls")),
    path("api/integrations/", include("apps.integrations.urls")),
    path("api/claims/", include("apps.claims.urls")),
    path("api/reconciliation/", include("apps.reconciliation.urls")),
]
