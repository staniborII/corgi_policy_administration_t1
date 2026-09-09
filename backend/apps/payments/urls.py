from django.urls import path

from apps.payments import views

urlpatterns = [
    path("checkout/", views.CreateCheckoutView.as_view(), name="payment-checkout"),
    path("policy/<int:policy_id>/", views.PolicyPaymentsView.as_view(), name="policy-payments"),
    path("policy/<int:policy_id>/refunds/", views.PolicyRefundsView.as_view(), name="policy-refunds"),
    path("<int:payment_id>/simulate/", views.SimulatePaymentView.as_view(), name="payment-simulate"),
    path("refunds/<int:refund_id>/simulate/", views.SimulateRefundView.as_view(), name="refund-simulate"),
]
