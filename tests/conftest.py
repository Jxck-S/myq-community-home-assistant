"""Fixtures for myQ Community integration tests.

The myQ Community client is mocked; these tests exercise the integration's
behavior inside a real Home Assistant test instance.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myqcommunity import Community, Device, HistoryEvent, MfaChallenge
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myq_community.const import CONF_EMAIL, CONF_TOKEN, DOMAIN

EMAIL = "user@example.com"
PASSWORD = "hunter2"
TOKEN = {"access_token": "a", "refresh_token": "r", "expires_at": 9999999999.0, "token_type": "Bearer"}
COMMUNITY_ID = "comm-1"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def make_devices() -> list[Device]:
    return [
        Device.from_json({"serial_number": "GATE-1", "device_family": "access_panel",
                          "device_type": "access_panel_door", "name": "Gate", "online": True, "kind": "door"}),
        Device.from_json({"serial_number": "DOOR-2", "device_family": "access_panel",
                          "device_type": "access_panel_door", "name": "Lobby", "online": False, "kind": "door"}),
        Device.from_json({"serial_number": "LOCK-3", "device_family": "remote_lock",
                          "device_type": "rl_lock", "name": "Front Door", "online": True}),
        Device.from_json({"serial_number": "CAM-4", "device_family": "camera",
                          "device_type": "cam", "name": "Camera", "kind": "camera"}),
    ]


def make_history() -> list[HistoryEvent]:
    return [
        HistoryEvent.from_json({"id": "h-2", "event": "unlocked", "device_name": "Gate",
                                "serial_number": "GATE-1", "timestamp": "2026-10-13T04:21:07Z"}),
        HistoryEvent.from_json({"id": "h-1", "event": "unlocked", "device_name": "Lobby",
                                "serial_number": "DOOR-2", "timestamp": "2026-10-12T10:00:00Z"}),
    ]


@pytest.fixture
def mock_client():
    """Patch MyQCommunity where the integration creates it."""
    client = MagicMock()
    client.communities = AsyncMock(return_value=[Community.from_json({"id": COMMUNITY_ID, "name": "Maple Court"})])
    client.devices = AsyncMock(side_effect=lambda cid: make_devices())
    client.history = AsyncMock(side_effect=lambda cid, limit=None: make_history())
    client.unlock = AsyncMock(return_value=True)
    client.lock = AsyncMock(return_value=True)
    client.aclose = AsyncMock()

    def factory(*args, **kwargs):
        client.init_args = args
        client.init_kwargs = kwargs
        return client

    with patch("custom_components.myq_community.MyQCommunity", side_effect=factory):
        yield client


@pytest.fixture
def pending():
    p = MagicMock()
    p.challenge = MfaChallenge(method="sms", masked_phone="(XXX) XXX-3392", masked_email="u***@example.com")
    p.aclose = AsyncMock()
    return p


@pytest.fixture
def mock_auth(pending):
    """Patch AuthSession in the config flow: start_login sends a code by default."""
    from myqcommunity import Token

    auth = MagicMock()
    auth.start_login = AsyncMock(return_value=pending)
    auth.finish_login = AsyncMock(return_value=Token.from_dict(TOKEN))
    auth.pending = pending

    def factory(*args, **kwargs):
        auth.init_kwargs = kwargs
        return auth

    with patch("custom_components.myq_community.config_flow.AuthSession", side_effect=factory):
        yield auth


@pytest.fixture
def config_entry(hass) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=EMAIL,
        unique_id=EMAIL,
        data={CONF_EMAIL: EMAIL, CONF_TOKEN: TOKEN},
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_integration(hass, config_entry, mock_client):
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
