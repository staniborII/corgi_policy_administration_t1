import pytest


@pytest.fixture(autouse=True)
def _channel_layer_settings(settings):
    settings.CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        },
    }
