"""車両の数値と時刻のセンサー。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Vehicle, VehicleStatus
from .coordinator import BluelinkJpConfigEntry, BluelinkJpCoordinator
from .entity import BluelinkJpEntity

# コーディネーターがまとめて取得するので、エンティティごとの更新は並べない。
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BluelinkJpSensorEntityDescription(SensorEntityDescription):
    """車両状態の1項目を表すセンサーの説明。"""

    value_fn: Callable[[VehicleStatus], float | datetime | None]
    ev_only: bool = False


SENSORS: tuple[BluelinkJpSensorEntityDescription, ...] = (
    BluelinkJpSensorEntityDescription(
        key="ev_battery_level",
        translation_key="ev_battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.ev_battery_level,
        ev_only=True,
    ),
    BluelinkJpSensorEntityDescription(
        key="ev_range",
        translation_key="ev_range",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.ev_range_km,
    ),
    BluelinkJpSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda status: status.odometer_km,
    ),
    BluelinkJpSensorEntityDescription(
        key="aux_battery_level",
        translation_key="aux_battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.aux_battery_level,
    ),
    BluelinkJpSensorEntityDescription(
        key="charge_remaining_time",
        translation_key="charge_remaining_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda status: status.charge_remaining_minutes,
        ev_only=True,
    ),
    BluelinkJpSensorEntityDescription(
        key="last_synced",
        translation_key="last_synced",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda status: status.synced_at,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluelinkJpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """車両ごとのセンサーを登録する。"""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for vehicle in coordinator.vehicles.values():
        entities.extend(
            BluelinkJpSensor(coordinator, vehicle, description)
            for description in SENSORS
            if vehicle.is_ev or not description.ev_only
        )
        entities.append(BluelinkJpLastFetchedSensor(coordinator, vehicle))
    entities.append(BluelinkJpIncidentSensor(coordinator, entry.entry_id))
    async_add_entities(entities)


_REASON_LABELS = {
    "communication_error": "通信エラー",
    "invalid_auth": "認証情報が無効",
    "password_change_required": "パスワード変更の確認",
    "account_locked": "アカウントの一時ロック",
    "http_error": "サーバー応答エラー",
    "gateway_rejected": "ゲートウェイ拒否",
    "api_error": "API エラー",
    "device_registration_failed": "端末登録失敗",
    "unsupported_vehicle": "未対応の車両",
    "unsupported_response": "未対応の応答",
}


class BluelinkJpIncidentSensor(CoordinatorEntity[BluelinkJpCoordinator], SensorEntity):
    """車両取得が失敗しても直近の障害履歴を表示する。"""

    _attr_has_entity_name = True
    _attr_translation_key = "incident_history"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:history"

    def __init__(self, coordinator: BluelinkJpCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_incident_history"

    @property
    def available(self) -> bool:
        """通信失敗時にも保存した履歴を確認できる。"""
        return True

    @property
    def native_value(self) -> int:
        return len(self.coordinator.history.public_incidents())

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """画面には新しい障害から最大20件を表示する。"""
        records = self.coordinator.history.public_incidents()
        return {
            "直近の障害": [
                {
                    "対象": "車両" if item["target"] == "vehicle" else "アカウント",
                    "検出": item["started"],
                    "最後に失敗": item["last_seen"],
                    "復旧": item["ended"],
                    "最初の原因": _REASON_LABELS.get(item["reason"], "不明"),
                    "直近の原因": _REASON_LABELS.get(item["latest_reason"], "不明"),
                    "HTTP": item["latest_http_status"],
                }
                for item in reversed(records[-20:])
            ],
            "保存上限": 200,
        }


class BluelinkJpSensor(BluelinkJpEntity, SensorEntity):
    """車両状態の1項目を表すセンサー。"""

    entity_description: BluelinkJpSensorEntityDescription

    def __init__(
        self,
        coordinator: BluelinkJpCoordinator,
        vehicle: Vehicle,
        description: BluelinkJpSensorEntityDescription,
    ) -> None:
        """センサーを作る。"""
        super().__init__(coordinator, vehicle, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | datetime | None:
        """センサーの値。車が報告していない値は None（不明）にする。"""
        status = self.vehicle_status
        return None if status is None else self.entity_description.value_fn(status)


class BluelinkJpLastFetchedSensor(BluelinkJpEntity, SensorEntity):
    """HA が最後に取得に成功した時刻。車の同期時刻とは別に示す（Issue #1）。"""

    _attr_translation_key = "last_fetched"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BluelinkJpCoordinator, vehicle: Vehicle) -> None:
        """センサーを作る。"""
        super().__init__(coordinator, vehicle, "last_fetched")

    @property
    def native_value(self) -> datetime | None:
        """この車両の状態を最後に取得できた時刻。"""
        return self.coordinator.data.fetched_at.get(self.vehicle.vehicle_id)
