import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError, connection, transaction


class Command(BaseCommand):
    help = "Ensure a Django superuser exists using env vars."

    def handle(self, *args, **options):
        db_type = os.environ.get("DB_TYPE", "sqlite")
        db_conf = settings.DATABASES["default"]
        db_name = db_conf.get("NAME", "")
        db_host = db_conf.get("HOST", "")
        db_port = db_conf.get("PORT", "")

        if db_type == "postgres":
            self.stdout.write(f"Database: PostgreSQL ({db_name}@{db_host}:{db_port})")
        else:
            self.stdout.write(f"Database: SQLite ({db_name})")

        connection.ensure_connection()
        self.stdout.write(f"Connection verified: {connection.vendor}")

        User = get_user_model()
        username_field = User.USERNAME_FIELD

        identifier = os.environ.get("DJANGO_SUPERUSER_" + username_field.upper())
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")

        if not identifier or not password:
            self.stdout.write(
                self.style.WARNING(
                    f"DJANGO_SUPERUSER_{username_field.upper()} or DJANGO_SUPERUSER_PASSWORD not set; skipping."
                )
            )
            return

        if User.objects.filter(**{username_field: identifier}).exists():
            self.stdout.write(f"Superuser '{identifier}' already exists. Skipping.")
            return

        try:
            with transaction.atomic():
                User.objects.create_superuser(
                    **{
                        username_field: identifier,
                        "password": password,
                        "role": User.Role.STAFF,
                    }
                )
        except IntegrityError:
            self.stdout.write(f"Superuser '{identifier}' was created by another task.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{identifier}'."))
