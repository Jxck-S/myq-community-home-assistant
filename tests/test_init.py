from datetime import timedelta

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.util import dt as dt_util
from myqcommunity import MyQAuthError, MyQRequestError, Token
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.myq_community.const import CONF_TOKEN, DOMAIN

from .conftest import COMMUNITY_ID, TOKEN


async def test_setup_creates_entities(hass, setup_integration, mock_client):
    assert setup_integration.state is ConfigEntryState.LOADED
    ids = set(hass.states.async_entity_ids())
    assert {
        "lock.maple_court_gate",
        "lock.maple_court_lobby",
        "lock.maple_court_front_door",
        "sensor.maple_court_last_access",
        "sensor.maple_court_last_access_time",
    } <= ids
    assert not any("camera" in i for i in ids)  # not unlockable
    # One devices + one history request per community, not one per entity
    assert mock_client.devices.await_count == 1
    mock_client.history.assert_awaited_once_with(COMMUNITY_ID, limit=10)


async def test_client_gets_shared_http_and_saved_token(hass, setup_integration, mock_client):
    (token,) = mock_client.init_args
    assert token == Token.from_dict(TOKEN)
    assert mock_client.init_kwargs["http"] is not None
    assert callable(mock_client.init_kwargs["on_token_refresh"])


async def test_rotated_token_saved_to_entry(hass, setup_integration, mock_client):
    new = Token(access_token="new", refresh_token="new-r", expires_at=123.0)
    mock_client.init_kwargs["on_token_refresh"](new)
    assert setup_integration.data[CONF_TOKEN] == new.to_dict()


async def test_auth_error_starts_reauth(hass, config_entry, mock_client):
    mock_client.communities.side_effect = MyQAuthError("revoked")
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_connection_error_retries_setup(hass, config_entry, mock_client):
    mock_client.communities.side_effect = MyQRequestError("offline", status=503)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_update_failure_marks_entities_unavailable(hass, setup_integration, mock_client):
    mock_client.devices.side_effect = MyQRequestError("offline")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.maple_court_last_access").state == STATE_UNAVAILABLE
    assert hass.states.get("lock.maple_court_gate").state == STATE_UNAVAILABLE


async def test_auth_failure_during_update_starts_reauth(hass, setup_integration, mock_client):
    mock_client.history.side_effect = MyQAuthError("revoked")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == [SOURCE_REAUTH]


async def test_unload_closes_client(hass, setup_integration, mock_client):
    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    assert setup_integration.state is ConfigEntryState.NOT_LOADED
    mock_client.aclose.assert_awaited_once()
