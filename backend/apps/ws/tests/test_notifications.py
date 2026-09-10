from unittest.mock import MagicMock, patch

from apps.ws.notifications import notify_staff, notify_user


@patch("apps.ws.notifications.get_channel_layer")
def test_notify_user_sends_to_correct_group(mock_get_layer):
    mock_layer = MagicMock()
    mock_get_layer.return_value = mock_layer

    notify_user(42, "policy.created", {"policy_id": 1})

    mock_layer.group_send.assert_called_once()
    call_args = mock_layer.group_send.call_args
    assert call_args[0][0] == "user_42"
    payload = call_args[0][1]["payload"]
    assert payload["event"] == "policy.created"
    assert payload["policy_id"] == 1


@patch("apps.ws.notifications.get_channel_layer")
def test_notify_staff_sends_to_role_group(mock_get_layer):
    mock_layer = MagicMock()
    mock_get_layer.return_value = mock_layer

    notify_staff("reconciliation.completed", {"run_id": 5})

    mock_layer.group_send.assert_called_once()
    call_args = mock_layer.group_send.call_args
    assert call_args[0][0] == "role_STAFF"
    payload = call_args[0][1]["payload"]
    assert payload["event"] == "reconciliation.completed"


@patch("apps.ws.notifications.get_channel_layer")
def test_notification_gracefully_handles_no_layer(mock_get_layer):
    mock_get_layer.return_value = None
    notify_user(1, "test.event")


@patch("apps.ws.notifications.get_channel_layer")
def test_notification_gracefully_handles_exception(mock_get_layer):
    mock_layer = MagicMock()
    mock_layer.group_send.side_effect = ConnectionError("Redis down")
    mock_get_layer.return_value = mock_layer

    notify_user(1, "test.event")
