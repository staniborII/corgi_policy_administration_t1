from django.urls import path

from apps.claims.views import (
    ApproveClaimPaymentView,
    ClaimDetailView,
    ClaimFinancialsView,
    ClaimListView,
    ClaimPaymentListView,
    ExecutePayoutView,
    PayoutCallbackView,
    PayoutDestinationView,
    ReserveEventListView,
    VerifyPayoutDestinationView,
)

urlpatterns = [
    path("", ClaimListView.as_view(), name="claim-list"),
    path("<int:pk>/", ClaimDetailView.as_view(), name="claim-detail"),
    path("<int:pk>/financials/", ClaimFinancialsView.as_view(), name="claim-financials"),
    path("<int:claim_pk>/reserves/", ReserveEventListView.as_view(), name="reserve-event-list"),
    path("<int:claim_pk>/payments/", ClaimPaymentListView.as_view(), name="claim-payment-list"),
    path("payments/<int:pk>/approve/", ApproveClaimPaymentView.as_view(), name="claim-payment-approve"),
    path("payments/<int:pk>/execute/", ExecutePayoutView.as_view(), name="claim-payment-execute"),
    path("payout-callback/", PayoutCallbackView.as_view(), name="payout-callback"),
    path("<int:claim_pk>/payout-destination/", PayoutDestinationView.as_view(), name="payout-destination"),
    path(
        "<int:claim_pk>/payout-destination/verify/",
        VerifyPayoutDestinationView.as_view(),
        name="payout-destination-verify",
    ),
]
