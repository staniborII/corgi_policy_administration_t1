import pytest
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from apps.ws.consumers import EventConsumer
from apps.ws.middleware import TokenAuthMiddleware

User = get_user_model()


def _make_app():
    from channels.routing import URLRouter
    from django.urls import path

    return TokenAuthMiddleware(URLRouter([path("ws/events/", EventConsumer.as_asgi())]))


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_valid_token_resolves_user():
    user = await User.objects.acreate(username="wsuser", role="CUSTOMER")
    token = await Token.objects.acreate(user=user)

    app = _make_app()
    communicator = WebsocketCommunicator(app, f"/ws/events/?token={token.key}")
    connected, code = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_invalid_token_rejected():
    app = _make_app()
    communicator = WebsocketCommunicator(app, "/ws/events/?token=bad-token")
    connected, code = await communicator.connect()
    assert not connected
    assert code == 4001


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_no_token_rejected():
    app = _make_app()
    communicator = WebsocketCommunicator(app, "/ws/events/")
    connected, code = await communicator.connect()
    assert not connected
    assert code == 4001
