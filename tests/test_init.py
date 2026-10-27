"""HA での読み込み、エンティティ、取得失敗の見え方。"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hyundai_bluelink_jp.api import (
    AccountLockedError,
    AuthenticationError,
    BluelinkError,
    BluelinkJpClient,
    PasswordChangeRequiredError,
    RequestFailedError,
    UnsupportedVehicleError,
    Vehicle,
    VehicleStatus,
)
from custom_components.hyundai_bluelink_jp.const import DOMAIN


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _state(hass: HomeAssistant, platform: str, key: str, vehicle_id: str = "test-car") -> str | None:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{vehicle_id}_{key}")
    if entity_id is None:
        return None
    state = hass.states.get(entity_id)
    return None if state is None else state.state


async def test_setup_creates_vehicle_entities(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "test-car"), config_entry.entry_id)
    assert device is not None
    assert (device.name, device.model, device.manufacturer) == ("IONIQ 5", "IONIQ 5", "Hyundai")

    # 距離は km、割合は小数のまま（Issue #2）。
    assert _state(hass, "sensor", "ev_battery_level") == "73"
    assert _state(hass, "sensor", "aux_battery_level") == "99.5"
    assert _state(hass, "sensor", "odometer") == "10908.5"
    assert _state(hass, "sensor", "ev_range") == "601.5"
    assert _state(hass, "sensor", "charge_remaining_time") == "30"

    # 車の同期時刻と HA の取得時刻は別のセンサー（Issue #1）。
    synced = dt_util.parse_datetime(_state(hass, "sensor", "last_synced") or "")
    assert synced == datetime(2026, 10, 12, 1, 0, 0, tzinfo=UTC)
    fetched = dt_util.parse_datetime(_state(hass, "sensor", "last_fetched") or "")
    assert fetched is not None
    assert fetched > synced

    assert _state(hass, "binary_sensor", "door_lock") == STATE_OFF
    assert _state(hass, "binary_sensor", "trunk") == STATE_ON
    assert _state(hass, "binary_sensor", "hood") == STATE_OFF
    assert _state(hass, "binary_sensor", "driving_ready") == STATE_OFF
    assert _state(hass, "binary_sensor", "charging") == STATE_ON
    assert _state(hass, "binary_sensor", "plugged_in") == STATE_ON

    tracker_id = er.async_get(hass).async_get_entity_id("device_tracker", DOMAIN, "test-car_location")
    assert tracker_id is not None
    tracker = hass.states.get(tracker_id)
    assert tracker is not None
    assert (tracker.attributes["latitude"], tracker.attributes["longitude"]) == (35.0, 139.0)

    # 遠隔操作のエンティティは作らない（Issue #4）。
    entities = er.async_entries_for_config_entry(er.async_get(hass), config_entry.entry_id)
    assert {entity.domain for entity in entities} == {"sensor", "binary_sensor", "device_tracker"}

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_non_ev_has_no_ev_entities(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    mock_client.vehicles.return_value = [Vehicle(vehicle_id="test-car", name="Car", model="", is_ev=False)]
    await _setup(hass, config_entry)
    for platform, key in (
        ("sensor", "ev_battery_level"),
        ("sensor", "charge_remaining_time"),
        ("binary_sensor", "charging"),
        ("binary_sensor", "plugged_in"),
    ):
        assert _state(hass, platform, key) is None
    assert _state(hass, "sensor", "odometer") == "10908.5"


async def test_fetch_failure_makes_entities_unavailable(
    hass: HomeAssistant,
    mock_client: SimpleNamespace,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    fetched_before = _state(hass, "sensor", "last_fetched")

    mock_client.status.side_effect = RequestFailedError("HTTP 500", http_status=500)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    # 取得に失敗したら古い値のまま見せない（Issue #1）。
    assert _state(hass, "sensor", "ev_battery_level") == STATE_UNAVAILABLE
    assert _state(hass, "sensor", "last_fetched") == STATE_UNAVAILABLE

    mock_client.status.side_effect = None
    freezer.tick(timedelta(minutes=10))
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", "ev_battery_level") == "73"
    assert _state(hass, "sensor", "last_fetched") != fetched_before


async def test_auth_failure_during_update_starts_reauth(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    await _setup(hass, config_entry)
    mock_client.status.side_effect = AuthenticationError("wrong password")
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (AuthenticationError("wrong password"), ConfigEntryState.SETUP_ERROR),
        (AccountLockedError("locked"), ConfigEntryState.SETUP_RETRY),
        (BluelinkError("timeout"), ConfigEntryState.SETUP_RETRY),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_client: SimpleNamespace,
    config_entry: MockConfigEntry,
    error: Exception,
    state: ConfigEntryState,
) -> None:
    mock_client.login.side_effect = error
    await _setup(hass, config_entry)
    assert config_entry.state is state


async def test_password_change_prompt_starts_reauth(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    mock_client.login.side_effect = PasswordChangeRequiredError("password change")
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == [SOURCE_REAUTH]


async def test_first_fetch_failure_retries_setup(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    mock_client.status.side_effect = RequestFailedError("HTTP 500", http_status=500)
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_one_failing_vehicle_does_not_hide_others(
    hass: HomeAssistant,
    mock_client: SimpleNamespace,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    status = mock_client.status.return_value
    mock_client.vehicles.return_value = [
        Vehicle(vehicle_id="test-car", name="IONIQ 5", model="IONIQ 5", is_ev=True),
        Vehicle(vehicle_id="old-car", name="Old car", model="", is_ev=True),
    ]
    failing = {"old-car"}

    async def fetch(client: BluelinkJpClient, vehicle_id: str) -> VehicleStatus:
        if vehicle_id in failing:
            raise UnsupportedVehicleError("HTTP 404", http_status=404)
        return status

    mock_client.status.side_effect = fetch
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert _state(hass, "sensor", "ev_battery_level") == "73"
    assert _state(hass, "sensor", "ev_battery_level", "old-car") == STATE_UNAVAILABLE
    assert _state(hass, "sensor", "last_fetched", "old-car") == STATE_UNAVAILABLE
    assert caplog.text.count("Old car の状態を取得できませんでした") == 1
    incidents = config_entry.runtime_data.history.public_incidents()
    assert len(incidents) == 1 and incidents[0]["ended"] is None

    # 失敗し続けても、警告は繰り返さない。
    await config_entry.runtime_data.async_refresh()
    assert caplog.text.count("Old car の状態を取得できませんでした") == 1

    failing.clear()
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor", "ev_battery_level", "old-car") == "73"
    assert "Old car の状態を再び取得できました" in caplog.text
    assert config_entry.runtime_data.history.public_incidents()[0]["ended"] is not None
