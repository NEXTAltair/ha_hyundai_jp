"""ドア、充電などの状態を表すバイナリーセンサー。"""

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Vehicle, VehicleStatus
from .coordinator import BluelinkJpConfigEntry, BluelinkJpCoordinator
from .entity import BluelinkJpEntity

# コーディネーターがまとめて取得するので、エンティティごとの更新は並べない。
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class BluelinkJpBinarySensorEntityDescription(BinarySensorEntityDescription):
    """車両状態の1項目を表すバイナリーセンサーの説明。"""

    is_on_fn: Callable[[VehicleStatus], bool | None]
    ev_only: bool = False


def _unlocked(status: VehicleStatus) -> bool | None:
    # lock クラスのバイナリーセンサーは on が「解錠」を表す。
    return None if status.doors_locked is None else not status.doors_locked


BINARY_SENSORS: tuple[BluelinkJpBinarySensorEntityDescription, ...] = (
    BluelinkJpBinarySensorEntityDescription(
        key="door_lock",
        translation_key="door_lock",
        device_class=BinarySensorDeviceClass.LOCK,
        is_on_fn=_unlocked,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="hood",
        translation_key="hood",
        device_class=BinarySensorDeviceClass.OPENING,
        is_on_fn=lambda status: status.hood_open,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="trunk",
        translation_key="trunk",
        device_class=BinarySensorDeviceClass.OPENING,
        is_on_fn=lambda status: status.trunk_open,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="driver_door",
        translation_key="driver_door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda status: status.driver_door_open,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="passenger_door",
        translation_key="passenger_door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda status: status.passenger_door_open,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="rear_left_door",
        translation_key="rear_left_door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda status: status.rear_left_door_open,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="rear_right_door",
        translation_key="rear_right_door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on_fn=lambda status: status.rear_right_door_open,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="driving_ready",
        translation_key="driving_ready",
        device_class=BinarySensorDeviceClass.POWER,
        is_on_fn=lambda status: status.driving_ready,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="tire_pressure",
        translation_key="tire_pressure",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda status: status.tire_pressure_low,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="charging",
        translation_key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        is_on_fn=lambda status: status.charging,
        ev_only=True,
    ),
    BluelinkJpBinarySensorEntityDescription(
        key="plugged_in",
        translation_key="plugged_in",
        device_class=BinarySensorDeviceClass.PLUG,
        is_on_fn=lambda status: status.plugged_in,
        ev_only=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluelinkJpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """車両ごとのバイナリーセンサーを登録する。"""
    coordinator = entry.runtime_data
    async_add_entities(
        BluelinkJpBinarySensor(coordinator, vehicle, description)
        for vehicle in coordinator.vehicles.values()
        for description in BINARY_SENSORS
        if vehicle.is_ev or not description.ev_only
    )


class BluelinkJpBinarySensor(BluelinkJpEntity, BinarySensorEntity):
    """車両状態の1項目を表すバイナリーセンサー。"""

    entity_description: BluelinkJpBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: BluelinkJpCoordinator,
        vehicle: Vehicle,
        description: BluelinkJpBinarySensorEntityDescription,
    ) -> None:
        """バイナリーセンサーを作る。"""
        super().__init__(coordinator, vehicle, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """センサーの状態。車が報告していない値は None（不明）にする。"""
        status = self.vehicle_status
        return None if status is None else self.entity_description.is_on_fn(status)
