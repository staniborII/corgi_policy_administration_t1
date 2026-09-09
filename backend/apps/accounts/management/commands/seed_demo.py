from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User
from apps.brokers.models import Broker
from apps.brokers.services import create_broker, process_kyb_webhook
from apps.claims.models import ClaimPayment, ReserveEvent
from apps.claims.services import (
    approve_claim_payment,
    create_claim_payment,
    execute_payout,
    handle_payout_settled,
    set_payout_destination,
    set_reserve,
    submit_claim,
    verify_payout_destination,
)
from apps.endorsements.models import Endorsement
from apps.endorsements.services import (
    apply_endorsement,
    approve_endorsement,
    create_endorsement,
)
from apps.payments.services import create_checkout_for_policy, simulate_payment_success
from apps.policies.models import FeeRule, TaxRule
from apps.policies.services import issue_policy
from apps.reconciliation.services import generate_broker_statement, run_reconciliation


class Command(BaseCommand):
    help = "Seed believable demo data: broker, policy, endorsement, claim, reconciliation"

    def handle(self, *args, **options):
        call_command("seed_chart_of_accounts")
        self.stdout.write("")

        self._seed_users()
        self._seed_tx_tax_rules()
        self._seed_tx_fee_rules()

        if Broker.objects.filter(company_name="Acme Insurance Brokers").exists():
            self.stdout.write(self.style.WARNING("Demo scenario already seeded — skipping."))
            return

        self._seed_demo_scenario()
        self.stdout.write(self.style.SUCCESS("\nFull demo seed complete."))

    def _seed_users(self):
        self.stdout.write("Seeding users...")

        staff_users = [
            ("staff1", "staff1@corgi.dev", "Staff", "Admin", "staffpass1"),
            ("staff2", "staff2@corgi.dev", "Staff", "Reviewer", "staffpass2"),
        ]
        for username, email, first, last, password in staff_users:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "role": User.Role.STAFF,
                    "is_staff": True,
                },
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"  Created STAFF: {username} / {password}")
            else:
                self.stdout.write(f"  Exists: {username}")

        customer_users = [
            ("customer1", "customer1@example.com", "Jane", "Doe", "custpass1"),
        ]
        for username, email, first, last, password in customer_users:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "role": User.Role.CUSTOMER,
                },
            )
            if created:
                user.set_password(password)
                user.save()
                self.stdout.write(f"  Created CUSTOMER: {username} / {password}")
            else:
                self.stdout.write(f"  Exists: {username}")

    def _seed_tx_tax_rules(self):
        self.stdout.write("Seeding Texas surplus-lines tax rules...")
        _, created = TaxRule.objects.get_or_create(
            jurisdiction="TX",
            name="TX Surplus Lines Premium Tax",
            effective_from=date(2024, 1, 1),
            defaults={
                "component_type": TaxRule.ComponentType.TAX,
                "rate_bps": 485,
                "is_refundable": True,
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: TX Surplus Lines Premium Tax (4.85%)")

    def _seed_tx_fee_rules(self):
        self.stdout.write("Seeding Texas surplus-lines fee rules...")
        _, created = FeeRule.objects.get_or_create(
            jurisdiction="TX",
            name="TX SLTX Stamping Fee",
            effective_from=date(2024, 1, 1),
            defaults={
                "fee_type": FeeRule.FeeType.RATE,
                "rate_bps": 4,
                "is_refundable": True,
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: TX SLTX Stamping Fee (0.04%)")

    @transaction.atomic
    def _seed_demo_scenario(self):
        staff1 = User.objects.get(username="staff1")
        staff2 = User.objects.get(username="staff2")
        customer = User.objects.get(username="customer1")

        # 1. Broker with KYB approval
        self.stdout.write("\n--- Creating broker ---")
        broker = create_broker(
            company_name="Acme Insurance Brokers",
            commission_rate_bps=1500,
            contact_email="broker@acme.dev",
            contact_first_name="Bob",
            contact_last_name="Broker",
        )
        broker = process_kyb_webhook(
            broker_id=broker.id,
            inquiry_id="SEED-KYB-001",
            persona_status="completed",
        )
        self.stdout.write(f"  Broker #{broker.id} — {broker.company_name} — {broker.status}")

        # 2. Issue policy (DRAFT)
        self.stdout.write("\n--- Issuing policy ---")
        policy, charges = issue_policy(
            customer=customer,
            broker_id=broker.id,
            effective_date=date(2026, 1, 1),
            premium_amount_cents=120_000_00,
            coverage_territory="TX",
            created_by=staff1,
        )
        self.stdout.write(f"  Policy {policy.policy_number} — premium ${charges['premium_cents'] / 100:,.2f}")
        self.stdout.write(
            f"  Tax: ${charges['total_tax_cents'] / 100:,.2f}  Fees: ${charges['total_fees_cents'] / 100:,.2f}"
        )
        self.stdout.write(f"  Total: ${charges['total_cents'] / 100:,.2f}")

        # 3. Pay and activate (DRAFT -> PENDING_PAYMENT -> ACTIVE)
        self.stdout.write("\n--- Activating policy via simulated payment ---")
        checkout = create_checkout_for_policy(policy_id=policy.id, requested_by=staff1)
        simulate_payment_success(payment_id=checkout["payment_id"])
        policy.refresh_from_db()
        self.stdout.write(f"  Policy status: {policy.status}")

        # 4. Endorsement — coverage limit increase ($10,000/yr)
        self.stdout.write("\n--- Creating endorsement (coverage limit increase) ---")
        endorsement, end_charges = create_endorsement(
            policy_id=policy.id,
            endorsement_type=Endorsement.EndorsementType.COVERAGE_LIMIT_CHANGE,
            effective_date=date(2026, 7, 1),
            annual_premium_delta_cents=10_000_00,
            description="Increase general aggregate from $1M to $2M",
            created_by=staff1,
        )
        self.stdout.write(f"  Endorsement {endorsement.endorsement_number} — status: {endorsement.status}")
        self.stdout.write(f"  Pro-rated charge: ${end_charges['total_cents'] / 100:,.2f}")

        if endorsement.status == Endorsement.Status.PENDING_CUSTOMER_APPROVAL:
            approve_endorsement(endorsement_id=endorsement.id, approved_by=customer)
            endorsement.refresh_from_db()
            self.stdout.write(f"  Customer approved — status: {endorsement.status}")

        apply_endorsement(endorsement_id=endorsement.id)
        endorsement.refresh_from_db()
        policy.refresh_from_db()
        self.stdout.write(f"  Applied — policy premium now ${policy.premium_amount_cents / 100:,.2f}")

        # 5. Second endorsement — address correction (no premium change)
        self.stdout.write("\n--- Creating endorsement (address correction) ---")
        addr_end, _ = create_endorsement(
            policy_id=policy.id,
            endorsement_type=Endorsement.EndorsementType.ADDRESS_CORRECTION,
            effective_date=date(2026, 3, 15),
            annual_premium_delta_cents=0,
            description="Correct insured address to 456 Oak Ave, Austin TX 78701",
            created_by=staff2,
        )
        apply_endorsement(endorsement_id=addr_end.id)
        self.stdout.write(f"  Endorsement {addr_end.endorsement_number} — applied")

        # 6. Claim with reserve and partial payout
        self.stdout.write("\n--- Submitting claim ---")
        claim = submit_claim(
            policy_id=policy.id,
            date_of_loss=date(2026, 8, 15),
            description="Water damage to insured commercial property — burst pipe in main office",
            estimated_amount_cents=250_000_00,
            user=customer,
        )
        self.stdout.write(f"  Claim #{claim.id} — status: {claim.status}")

        set_reserve(
            claim_id=claim.id,
            amount_cents=200_000_00,
            reserve_type=ReserveEvent.ReserveType.INITIAL,
            memo="Initial reserve based on adjuster estimate",
            user=staff1,
        )
        claim.refresh_from_db()
        self.stdout.write(f"  Initial reserve $200,000 — claim status: {claim.status}")

        set_payout_destination(
            claim_id=claim.id,
            payee_name="Jane Doe",
            account_last_four="4567",
        )
        verify_payout_destination(claim_id=claim.id, outcome="VERIFIED")
        self.stdout.write("  Payout destination set and verified")

        cp = create_claim_payment(
            claim_id=claim.id,
            amount_cents=75_000_00,
            payee="Jane Doe",
            user=staff1,
        )
        self.stdout.write(f"  Claim payment #{cp.id} for $75,000 — status: {cp.status}")

        if cp.status == ClaimPayment.Status.PENDING_APPROVAL:
            approve_claim_payment(payment_id=cp.id, user=staff2)
            cp.refresh_from_db()
            self.stdout.write(f"  Approved by staff2 — status: {cp.status}")

        cp = execute_payout(payment_id=cp.id, user=staff1)
        cp.refresh_from_db()
        self.stdout.write(f"  Payout executed — reference: {cp.payout_reference}")

        handle_payout_settled(
            payout_reference=cp.payout_reference,
            amount_cents=cp.amount_cents,
        )
        self.stdout.write("  Payout settled — ledger entries posted")

        # 7. Reconciliation run (will produce a break for SIMULATED payments)
        self.stdout.write("\n--- Running reconciliation ---")
        recon_run = run_reconciliation()
        self.stdout.write(f"  Run #{recon_run.id} — status: {recon_run.status}")
        break_count = recon_run.breaks.count()
        self.stdout.write(f"  Breaks found: {break_count}")

        # 8. Broker statement
        self.stdout.write("\n--- Generating broker statement ---")
        statement = generate_broker_statement(
            broker=broker,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
        )
        self.stdout.write(f"  Statement #{statement.id} — {statement.period_start} to {statement.period_end}")

        self.stdout.write("\n--- Demo scenario summary ---")
        self.stdout.write(f"  Broker: {broker.company_name} (KYB {broker.status})")
        self.stdout.write(f"  Policy: {policy.policy_number} ({policy.status})")
        self.stdout.write("  Endorsements: 2 (coverage change + address correction)")
        self.stdout.write(f"  Claim: #{claim.id} with $75,000 settled payout")
        self.stdout.write(f"  Reconciliation: {break_count} break(s)")
        self.stdout.write(f"  Broker statement: #{statement.id}")
