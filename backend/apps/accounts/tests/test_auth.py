import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="staff", password="testpass", role=User.Role.STAFF, is_staff=True)


@pytest.fixture
def customer_user(db):
    return User.objects.create_user(username="customer", password="testpass", role=User.Role.CUSTOMER)


class TestLogin:
    def test_staff_login(self, api, staff_user):
        resp = api.post("/api/auth/login/", {"username": "staff", "password": "testpass"})
        assert resp.status_code == 200
        assert "token" in resp.data
        assert resp.data["user"]["role"] == "STAFF"

    def test_customer_login(self, api, customer_user):
        resp = api.post("/api/auth/login/", {"username": "customer", "password": "testpass"})
        assert resp.status_code == 200
        assert resp.data["user"]["role"] == "CUSTOMER"

    def test_invalid_credentials(self, api, staff_user):
        resp = api.post("/api/auth/login/", {"username": "staff", "password": "wrong"})
        assert resp.status_code == 400


class TestMe:
    def test_authenticated_user(self, api, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.get("/api/auth/me/")
        assert resp.status_code == 200
        assert resp.data["username"] == "staff"
        assert resp.data["role"] == "STAFF"

    def test_unauthenticated(self, api):
        resp = api.get("/api/auth/me/")
        assert resp.status_code in (401, 403)


class TestRegister:
    def test_register_customer(self, api, db):
        resp = api.post(
            "/api/auth/register/",
            {
                "username": "newcust",
                "email": "new@example.com",
                "password": "securepass123",
                "first_name": "New",
                "last_name": "Customer",
            },
        )
        assert resp.status_code == 201
        assert resp.data["user"]["role"] == "CUSTOMER"
        assert "token" in resp.data

    def test_register_duplicate(self, api, customer_user):
        resp = api.post(
            "/api/auth/register/",
            {
                "username": "customer",
                "email": "dup@example.com",
                "password": "securepass123",
            },
        )
        assert resp.status_code == 400


class TestPermissions:
    def test_staff_can_access_brokers(self, api, staff_user):
        api.force_authenticate(user=staff_user)
        resp = api.get("/api/brokers/")
        assert resp.status_code == 200

    def test_customer_cannot_access_brokers(self, api, customer_user):
        api.force_authenticate(user=customer_user)
        resp = api.get("/api/brokers/")
        assert resp.status_code == 403
