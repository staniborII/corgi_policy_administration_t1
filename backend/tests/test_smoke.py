from django.core.management import call_command


def test_django_check():
    """Verify Django project configuration loads without errors."""
    call_command("check", verbosity=0)
