from datetime import timedelta

import pytest
from homeassistant.components.lock import LockState
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from myqcommunity import MyQAuthError, MyQRequestError
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.myq_community.const import DOMAIN

from .conftest import COMMUNITY_ID

GATE = "lock.maple_court_gate"
SMART_LOCK = "lock.maple_court_front_door"


async def call(hass, service, entity_id=GATE):
    await hass.services.async_call("lock", service, {ATTR_ENTITY_ID: entity_id}, blocking=True)


async def test_lock_states(hass, setup_integration):
    assert hass.states.get(GATE).state == LockState.LOCKED
    assert hass.states.get("lock.maple_court_lobby").state == STATE_UNAVAILABLE  # reported offline
    smart = hass.states.get(SMART_LOCK)
    assert smart.state == LockState.LOCKED and smart.attributes["assumed_state"] is True


async def test_unlock_opens_gate_then_relocks(hass, setup_integration, mock_client):
    await call(hass, "unlock")

    community_id, device = mock_client.unlock.await_args.args
    assert community_id == COMMUNITY_ID and device.serial_number == "GATE-1"  # Device, so it routes by family
    assert hass.states.get(GATE).state == LockState.UNLOCKED

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(GATE).state == LockState.LOCKED


async def test_unlock_refreshes_history(hass, setup_integration, mock_client):
    before = mock_client.history.await_count
    await call(hass, "unlock")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert mock_client.history.await_count > before


async def test_unlock_cooldown(hass, setup_integration, mock_client):
    await call(hass, "unlock")
    with pytest.raises(HomeAssistantError, match="just opened"):
        await call(hass, "unlock")
    assert mock_client.unlock.await_count == 1


@pytest.mark.parametrize("failure", [MyQRequestError("timeout"), False])
async def test_unlock_failure_raises(hass, setup_integration, mock_client, failure):
    if failure is False:
        mock_client.unlock.return_value = False
    else:
        mock_client.unlock.side_effect = failure
    with pytest.raises(HomeAssistantError, match="Failed to open"):
        await call(hass, "unlock")
    assert hass.states.get(GATE).state == LockState.LOCKED


async def test_unlock_auth_failure_starts_reauth(hass, setup_integration, mock_client):
    mock_client.unlock.side_effect = MyQAuthError("revoked")
    with pytest.raises(HomeAssistantError):
        await call(hass, "unlock")
    await hass.async_block_till_done()
    assert len(hass.config_entries.flow.async_progress_by_handler(DOMAIN)) == 1


async def test_gate_lock_is_noop(hass, setup_integration, mock_client):
    await call(hass, "lock")
    mock_client.lock.assert_not_awaited()


async def test_smart_lock_unlock_and_lock(hass, setup_integration, mock_client):
    await call(hass, "unlock", SMART_LOCK)
    assert hass.states.get(SMART_LOCK).state == LockState.UNLOCKED
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()
    assert hass.states.get(SMART_LOCK).state == LockState.UNLOCKED  # no auto-relock for smart locks

    await call(hass, "lock", SMART_LOCK)
    mock_client.lock.assert_awaited_once_with(COMMUNITY_ID, "LOCK-3")
    assert hass.states.get(SMART_LOCK).state == LockState.LOCKED


async def test_last_access_sensors(hass, setup_integration):
    state = hass.states.get("sensor.maple_court_last_access")
    assert state.state == "Gate - unlocked"
    assert state.attributes["device"] == "Gate"
    assert state.attributes["serial_number"] == "GATE-1"

    t = hass.states.get("sensor.maple_court_last_access_time")
    assert t.state == "2026-10-13T04:21:07+00:00"
    assert t.attributes["device_class"] == "timestamp"


async def test_sensors_update_from_coordinator(hass, setup_integration, mock_client):
    from myqcommunity import HistoryEvent

    mock_client.history.side_effect = lambda cid, limit=None: [
        HistoryEvent.from_json({"id": "h-3", "event": "unlocked", "device_name": "Lobby",
                                "serial_number": "DOOR-2", "timestamp": "2026-10-14T08:00:00Z"})
    ]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=6))
    await hass.async_block_till_done()
    assert hass.states.get("sensor.maple_court_last_access").state == "Lobby - unlocked"
    assert hass.states.get("sensor.maple_court_last_access_time").state == "2026-10-14T08:00:00+00:00"


async def test_no_history_sensors_unknown(hass, config_entry, mock_client):
    mock_client.history.side_effect = lambda cid, limit=None: []
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.maple_court_last_access").state == "unknown"
