from django.core.management.base import BaseCommand

from apps.ledger.models import LedgerAccount

CHART_OF_ACCOUNTS = [
    # Assets (normal balance: DEBIT)
    ("1000", "Cash", "ASSET", "DEBIT"),
    ("1010", "Stripe Clearing", "ASSET", "DEBIT"),
    ("1100", "Premium Receivable", "ASSET", "DEBIT"),
    # Liabilities (normal balance: CREDIT)
    ("2000", "Unearned Premium", "LIABILITY", "CREDIT"),
    ("2100", "State Premium Tax Payable", "LIABILITY", "CREDIT"),
    ("2200", "Broker Commission Payable", "LIABILITY", "CREDIT"),
    ("2300", "Claim Reserve", "LIABILITY", "CREDIT"),
    ("2400", "Refund Payable", "LIABILITY", "CREDIT"),
    # Revenue (normal balance: CREDIT)
    ("4000", "Earned Premium", "REVENUE", "CREDIT"),
    ("4100", "Fee Revenue", "REVENUE", "CREDIT"),
    ("4200", "Commission Clawback", "REVENUE", "CREDIT"),
    # Expenses (normal balance: DEBIT)
    ("5000", "Claims Expense", "EXPENSE", "DEBIT"),
    ("5100", "Commission Expense", "EXPENSE", "DEBIT"),
]


class Command(BaseCommand):
    help = "Seed the chart of accounts for the double-entry ledger"

    def handle(self, *args, **options):
        created_count = 0
        for code, name, account_type, normal_balance in CHART_OF_ACCOUNTS:
            _, created = LedgerAccount.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "account_type": account_type,
                    "normal_balance": normal_balance,
                },
            )
            if created:
                created_count += 1
                self.stdout.write(f"  Created {code} — {name}")
            else:
                self.stdout.write(f"  Exists  {code} — {name}")

        self.stdout.write(self.style.SUCCESS(f"Done. {created_count} new accounts created."))
