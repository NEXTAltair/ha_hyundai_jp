"""車がクラウドへ同期した位置。"""

from homeassistant.components.device_tracker.const import SourceType
from homeassistant.components.device_tracker.entity import TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Vehicle
from .coordinator import BluelinkJpConfigEntry, BluelinkJpCoordinator
from .entity import BluelinkJpEntity

# コーディネーターがまとめて取得するので、エンティティごとの更新は並べない。
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BluelinkJpConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """車両ごとの位置を登録する。"""
    coordinator = entry.runtime_data
    async_add_entities(BluelinkJpTracker(coordinator, vehicle) for vehicle in coordinator.vehicles.values())


class BluelinkJpTracker(BluelinkJpEntity, TrackerEntity):
    """車がクラウドへ同期した位置。"""

    _attr_translation_key = "location"
    _attr_source_type = SourceType.GPS

    def __init__(self, coordinator: BluelinkJpCoordinator, vehicle: Vehicle) -> None:
        """位置のエンティティを作る。"""
        super().__init__(coordinator, vehicle, "location")

    @property
    def latitude(self) -> float | None:
        """緯度。"""
        status = self.vehicle_status
        return None if status is None else status.latitude

    @property
    def longitude(self) -> float | None:
        """経度。"""
        status = self.vehicle_status
        return None if status is None else status.longitude
