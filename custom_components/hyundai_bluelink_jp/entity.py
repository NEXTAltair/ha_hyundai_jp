"""車両ごとのエンティティの共通部分。"""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Vehicle, VehicleStatus
from .const import DOMAIN, MANUFACTURER
from .coordinator import BluelinkJpCoordinator


class BluelinkJpEntity(CoordinatorEntity[BluelinkJpCoordinator]):
    """1台の車両に属するエンティティ。"""

    _attr_has_entity_name = True

    def __init__(self, coordinator: BluelinkJpCoordinator, vehicle: Vehicle, key: str) -> None:
        """エンティティを作る。

        Args:
            coordinator: 状態を取得するコーディネーター。
            vehicle: エンティティが属する車両。
            key: 車両の中でエンティティを区別するキー。
        """
        super().__init__(coordinator)
        self.vehicle = vehicle
        self._attr_unique_id = f"{vehicle.vehicle_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, vehicle.vehicle_id)},
            name=vehicle.name,
            manufacturer=MANUFACTURER,
            model=vehicle.model or None,
        )

    @property
    def vehicle_status(self) -> VehicleStatus | None:
        """直近に取得したこの車両の状態。"""
        return self.coordinator.data.statuses.get(self.vehicle.vehicle_id)
