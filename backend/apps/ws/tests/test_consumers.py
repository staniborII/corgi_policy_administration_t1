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
async def test_authenticated_user_connects():
    user = await User.objects.acreate(username="staff1", role="STAFF")
    token = await Token.objects.acreate(user=user)

    app = _make_app()
    communicator = WebsocketCommunicator(app, f"/ws/events/?token={token.key}")
    connected, _ = await communicator.connect()
    assert connected
    await communicator.disconnect()


@pytest.mark.django_db(transaction=True)
@pytest.mark.asyncio
async def test_notify_message_forwarded():
    user = await User.objects.acreate(username="cust1", role="CUSTOMER")
    token = await Token.objects.acreate(user=user)

    app = _make_app()
    communicator = WebsocketCommunicator(app, f"/ws/events/?token={token.key}")
    connected, _ = await communicator.connect()
    assert connected

    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    await channel_layer.group_send(
        f"user_{user.id}",
        {"type": "notify", "payload": {"event": "policy.created", "policy_id": 42}},
    )

    response = await communicator.receive_json_from(timeout=2)
    assert response["event"] == "policy.created"
    assert response["policy_id"] == 42
    await communicator.disconnect()
