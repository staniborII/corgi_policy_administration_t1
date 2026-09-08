from datetime import date

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.policies.models import FeeRule, TaxRule


class Command(BaseCommand):
    help = "Seed demo users and California tax/fee rules"

    def handle(self, *args, **options):
        call_command("seed_chart_of_accounts")
        self.stdout.write("")

        self._seed_users()
        self._seed_tax_rules()
        self._seed_fee_rules()

        self.stdout.write(self.style.SUCCESS("\nDemo seed complete."))

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

    def _seed_tax_rules(self):
        self.stdout.write("Seeding California tax rules...")
        _, created = TaxRule.objects.get_or_create(
            jurisdiction="CA",
            name="CA Premium Tax",
            effective_from=date(2020, 1, 1),
            defaults={
                "component_type": TaxRule.ComponentType.TAX,
                "rate_bps": 235,
                "is_refundable": True,
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: CA Premium Tax (2.35%)")

        _, created = TaxRule.objects.get_or_create(
            jurisdiction="CA",
            name="CA FAIR Plan Surcharge",
            effective_from=date(2020, 1, 1),
            defaults={
                "component_type": TaxRule.ComponentType.SURCHARGE,
                "rate_bps": 10,
                "is_refundable": False,
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: CA FAIR Plan Surcharge (0.10%)")

    def _seed_fee_rules(self):
        self.stdout.write("Seeding California fee rules...")
        _, created = FeeRule.objects.get_or_create(
            jurisdiction="CA",
            name="CA Stamping Fee",
            effective_from=date(2020, 1, 1),
            defaults={
                "fee_type": FeeRule.FeeType.FLAT,
                "amount_cents": 2500,
                "is_refundable": False,
            },
        )
        self.stdout.write(f"  {'Created' if created else 'Exists'}: CA Stamping Fee ($25.00)")
