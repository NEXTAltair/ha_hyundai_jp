"""CCS2 の車両状態の応答を読み取る。

項目の位置は hyundai_kia_connect_api の ApiImplType1 と同じで、日本の実応答（IONIQ 5）で確認した。
欠けている値と想定外の値は None のままにし、推測で埋めない。距離は km、割合は小数のまま持つ。
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from typing import Any

from .errors import UnsupportedResponseError

_KM_PER_MILE = 1.609344


@dataclass(frozen=True, slots=True)
class VehicleStatus:
    """車がクラウドへ同期した状態。

    Attributes:
        synced_at: 車がクラウドへ状態を同期した時刻。HA が取得した時刻ではない。
        odometer_km: 走行距離。
        ev_battery_level: 駆動用バッテリーの残量（%）。
        ev_range_km: 航続可能距離。
        aux_battery_level: 補機（12V）バッテリーの残量（%）。
        charge_remaining_minutes: 充電完了までの残り時間（分）。
        charging: 充電中か。残り時間が 0 より大きいかで判断する（上流と同じ導き方）。
        plugged_in: 充電コネクターがつながっているか。
        driving_ready: 走行可能な状態か。
        doors_locked: すべてのドアが施錠されているか。
        hood_open: ボンネットが開いているか。
        trunk_open: トランクが開いているか。
        driver_door_open: 運転席のドアが開いているか。
        passenger_door_open: 助手席のドアが開いているか。
        rear_left_door_open: 後席左のドアが開いているか。
        rear_right_door_open: 後席右のドアが開いているか。
        tire_pressure_low: タイヤ空気圧の警告が出ているか。
        latitude: 緯度。
        longitude: 経度。
    """

    synced_at: datetime | None = None
    odometer_km: float | None = None
    ev_battery_level: float | None = None
    ev_range_km: float | None = None
    aux_battery_level: float | None = None
    charge_remaining_minutes: float | None = None
    charging: bool | None = None
    plugged_in: bool | None = None
    driving_ready: bool | None = None
    doors_locked: bool | None = None
    hood_open: bool | None = None
    trunk_open: bool | None = None
    driver_door_open: bool | None = None
    passenger_door_open: bool | None = None
    rear_left_door_open: bool | None = None
    rear_right_door_open: bool | None = None
    tire_pressure_low: bool | None = None
    latitude: float | None = None
    longitude: float | None = None


def _get(data: Any, path: str) -> Any:
    for key in path.split("."):
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _flag(value: Any) -> bool | None:
    if value in (False, 0, "0", "false"):
        return False
    if value in (True, 1, "1", "true"):
        return True
    return None


def _number(value: Any) -> float | None:
    # 整数で届いた値は整数のまま返し、HA の表示に余計な ".0" を付けない。
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        number = float(value)
    except TypeError, ValueError:
        return None
    return number if isfinite(number) else None


def _percentage(value: Any) -> float | None:
    number = _number(value)
    if number is None or not 0 <= number <= 100:
        return None
    return number


def _distance_km(value: Any, unit: Any) -> float | None:
    number = _number(value)
    if number is None:
        return None
    if unit in (1, "1", "km"):
        return number
    if unit in (3, "3", "mi", "mile"):
        return number * _KM_PER_MILE
    return None


def parse_timestamp(value: Any) -> datetime | None:
    """CCS2 の時刻を UTC の datetime に変換する。

    Args:
        value: `YYYYMMDDHHMMSS`（小数秒付きも可）か ISO 8601 の文字列。時差がなければ UTC として読む。

    Returns:
        UTC の時刻。読み取れない場合は None。
    """
    if not isinstance(value, str):
        return None
    compact, separator, _fraction = value.partition(".")
    try:
        if len(compact) == 14 and compact.isdigit():
            date_format = "%Y%m%d%H%M%S.%f" if separator else "%Y%m%d%H%M%S"
            result = datetime.strptime(value, date_format)
        else:
            result = datetime.fromisoformat(value)
    except ValueError:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def _doors_locked(state: dict[str, Any]) -> bool | None:
    doors = ("Row1.Driver", "Row1.Passenger", "Row2.Left", "Row2.Right")
    # CCS2 は施錠を 0、解錠を 1 で返す。1枚でも解錠なら未施錠とし、
    # 一部のドアが欠けている応答から「すべて施錠」とは言わない。
    locks = [_flag(_get(state, f"Cabin.Door.{door}.Lock")) for door in doors]
    if any(value is True for value in locks):
        return False
    if all(value is False for value in locks):
        return True
    return None


def _aux_battery_level(state: dict[str, Any]) -> float | None:
    # SensorReliability は 1 がセンサー値を信頼できない状態を示す。
    if _get(state, "Electronics.Battery.SensorReliability") in (1, "1"):
        return None
    return _percentage(_get(state, "Electronics.Battery.Level"))


def _location(state: dict[str, Any]) -> tuple[float | None, float | None]:
    latitude = _number(_get(state, "Location.GeoCoord.Latitude"))
    longitude = _number(_get(state, "Location.GeoCoord.Longitude"))
    if (
        latitude is None
        or longitude is None
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
        or (latitude == 0 and longitude == 0)
    ):
        return None, None
    return latitude, longitude


def parse_ccs2_status(body: Any) -> VehicleStatus:
    """CCS2 の `carstatus/latest` の応答を読み取る。

    Args:
        body: 応答の JSON。

    Returns:
        読み取った車両状態。

    Raises:
        UnsupportedResponseError: `resMsg.state.Vehicle` がない場合。
    """
    state = _get(body, "resMsg.state.Vehicle")
    if not isinstance(state, dict):
        raise UnsupportedResponseError("CCS2 の車両状態が応答にありません")

    remaining_minutes = _number(_get(state, "Green.ChargingInformation.Charging.RemainTime"))
    if remaining_minutes is not None and remaining_minutes < 0:
        remaining_minutes = None
    latitude, longitude = _location(state)

    return VehicleStatus(
        # CCS2 の Date は UTC（日本時間ではない）。
        synced_at=parse_timestamp(_get(state, "Date")),
        odometer_km=_distance_km(_get(state, "Drivetrain.Odometer"), 1),
        ev_battery_level=_percentage(_get(state, "Green.BatteryManagement.BatteryRemain.Ratio")),
        ev_range_km=_distance_km(
            _get(state, "Drivetrain.FuelSystem.DTE.Total"),
            _get(state, "Drivetrain.FuelSystem.DTE.Unit"),
        ),
        aux_battery_level=_aux_battery_level(state),
        charge_remaining_minutes=remaining_minutes,
        charging=None if remaining_minutes is None else remaining_minutes > 0,
        plugged_in=_flag(_get(state, "Green.ChargingInformation.ConnectorFastening.State")),
        driving_ready=_flag(_get(state, "DrivingReady")),
        doors_locked=_doors_locked(state),
        hood_open=_flag(_get(state, "Body.Hood.Open")),
        trunk_open=_flag(_get(state, "Body.Trunk.Open")),
        driver_door_open=_flag(_get(state, "Cabin.Door.Row1.Driver.Open")),
        passenger_door_open=_flag(_get(state, "Cabin.Door.Row1.Passenger.Open")),
        rear_left_door_open=_flag(_get(state, "Cabin.Door.Row2.Left.Open")),
        rear_right_door_open=_flag(_get(state, "Cabin.Door.Row2.Right.Open")),
        tire_pressure_low=_flag(_get(state, "Chassis.Axle.Tire.PressureLow")),
        latitude=latitude,
        longitude=longitude,
    )
