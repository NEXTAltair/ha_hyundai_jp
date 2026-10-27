"""障害履歴の永続化と回復の判定。"""

import json
from datetime import timedelta
from types import SimpleNamespace

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hyundai_bluelink_jp import history as history_module
from custom_components.hyundai_bluelink_jp.api import BluelinkError, RequestFailedError
from custom_components.hyundai_bluelink_jp.const import DOMAIN
from custom_components.hyundai_bluelink_jp.diagnostics import async_get_config_entry_diagnostics
from custom_components.hyundai_bluelink_jp.history import IncidentHistory, vehicle_scope


async def test_history_groups_failures_persists_and_closes_only_on_recovery(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    history = IncidentHistory(hass, "history-test")
    await history.async_load()
    scope = vehicle_scope("private-vehicle-id")
    await history.async_failure(scope, RequestFailedError("private-token", http_status=503))
    freezer.tick(timedelta(minutes=10))
    await history.async_failure(scope, BluelinkError("private-email"))
    other = IncidentHistory(hass, "history-test")
    await other.async_load()
    records = other.public_incidents()
    assert len(records) == 1
    assert records[0]["reason"] == "http_error"
    assert records[0]["latest_reason"] == "communication_error"
    assert records[0]["started"] != records[0]["last_seen"]
    assert records[0]["ended"] is None
    assert all(
        secret not in json.dumps(records)
        for secret in ("private-vehicle-id", "private-token", "private-email")
    )
    await other.async_recovery(scope)
    await other.async_recovery(scope)
    assert other.public_incidents()[0]["ended"] is not None
    await other.async_remove()
    again = IncidentHistory(hass, "history-test")
    await again.async_load()
    assert again.public_incidents() == []


async def test_setup_failure_recorded_and_diagnostics_available(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_client.login.side_effect = BluelinkError("private-password")
    await hass.config_entries.async_setup(config_entry.entry_id)
    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diagnostics["incidents"][0]["ended"] is None
    assert diagnostics["incidents"][0]["reason"] == "communication_error"
    assert "private-password" not in json.dumps(diagnostics)

    mock_client.login.side_effect = None
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    records = config_entry.runtime_data.history.public_incidents()
    assert len(records) == 1
    assert records[0]["ended"] is not None


async def test_history_limits_completed_records(hass: HomeAssistant, monkeypatch) -> None:
    monkeypatch.setattr(history_module, "MAX_INCIDENTS", 2)
    history = IncidentHistory(hass, "limit-test")
    await history.async_load()
    for _ in range(3):
        await history.async_failure("account", BluelinkError("offline"))
        await history.async_recovery("account")
    assert len(history.public_incidents()) == 2


async def test_initial_vehicle_failure_persists_until_success(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_client.status.side_effect = RequestFailedError("offline", http_status=503)
    await hass.config_entries.async_setup(config_entry.entry_id)
    data = await async_get_config_entry_diagnostics(hass, config_entry)
    assert data["incidents"][0]["target"] == "vehicle"
    assert data["incidents"][0]["ended"] is None
    mock_client.status.side_effect = None
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.runtime_data.history.public_incidents()[0]["ended"] is not None


async def test_vehicle_failure_and_recovery_visible_in_sensor(
    hass: HomeAssistant,
    mock_client: SimpleNamespace,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    mock_client.status.side_effect = RequestFailedError("private message", http_status=503)
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "sensor", DOMAIN, f"{config_entry.entry_id}_incident_history"
    )
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None and state.state == "1"
    assert state.attributes["直近の障害"][0]["復旧"] is None
    first_failure_time = state.attributes["直近の障害"][0]["最後に失敗"]
    freezer.tick(timedelta(minutes=10))
    mock_client.status.side_effect = BluelinkError("another private message")
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None and state.state == "1"
    assert state.attributes["直近の障害"][0]["最後に失敗"] != first_failure_time
    assert state.attributes["直近の障害"][0]["直近の原因"] == "通信エラー"
    mock_client.status.side_effect = None
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state is not None and state.attributes["直近の障害"][0]["復旧"] is not None
