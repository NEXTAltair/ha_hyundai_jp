"""CCS2 応答の読み取り。単位、精度、欠けた値の扱いを確認する。"""

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.hyundai_bluelink_jp.api import UnsupportedResponseError, parse_ccs2_status
from custom_components.hyundai_bluelink_jp.api.status import parse_timestamp


def _vehicle(body: dict[str, Any]) -> dict[str, Any]:
    return body["resMsg"]["state"]["Vehicle"]


def test_values_keep_km_and_fractions(ccs2_body: dict[str, Any]) -> None:
    original = deepcopy(ccs2_body)
    status = parse_ccs2_status(ccs2_body)
    # マイル換算や整数への切り捨てをしない（Issue #2）。
    assert status.odometer_km == 10908.5
    assert status.ev_range_km == 601.5
    assert status.aux_battery_level == 99.5
    assert status.ev_battery_level == 73
    assert isinstance(status.ev_battery_level, int)
    assert status.charge_remaining_minutes == 30
    assert status.charging is True
    assert status.plugged_in is True
    assert status.driving_ready is False
    assert status.doors_locked is True
    assert status.trunk_open is True
    assert status.hood_open is False
    assert status.driver_door_open is False
    assert status.tire_pressure_low is False
    assert (status.latitude, status.longitude) == (35.0, 139.0)
    # CCS2 の Date は UTC として読む。
    assert status.synced_at == datetime(2026, 10, 12, 1, 0, 0, 123000, tzinfo=UTC)
    assert ccs2_body == original


def test_range_in_miles_is_converted_to_km(ccs2_body: dict[str, Any]) -> None:
    _vehicle(ccs2_body)["Drivetrain"]["FuelSystem"]["DTE"] = {"Total": 100, "Unit": 3}
    assert parse_ccs2_status(ccs2_body).ev_range_km == pytest.approx(160.9344)


@pytest.mark.parametrize("unit", [None, 2, "x"])
def test_range_with_unknown_unit_is_unknown(ccs2_body: dict[str, Any], unit: Any) -> None:
    _vehicle(ccs2_body)["Drivetrain"]["FuelSystem"]["DTE"]["Unit"] = unit
    assert parse_ccs2_status(ccs2_body).ev_range_km is None


def test_missing_and_out_of_range_values_stay_unknown(ccs2_body: dict[str, Any]) -> None:
    state = _vehicle(ccs2_body)
    state["Green"] = {}
    state["Electronics"]["Battery"]["Level"] = 255
    state["Chassis"]["Axle"]["Tire"]["PressureLow"] = 255
    del state["Cabin"]["Door"]["Row2"]["Right"]["Lock"]
    del state["Date"]
    status = parse_ccs2_status(ccs2_body)
    assert status.ev_battery_level is None
    assert status.aux_battery_level is None
    assert status.charging is None
    assert status.charge_remaining_minutes is None
    assert status.plugged_in is None
    assert status.tire_pressure_low is None
    # 欠けたドアがあるときは「すべて施錠」と言わない。
    assert status.doors_locked is None
    # 同期時刻がないときに取得時刻で埋めない。
    assert status.synced_at is None


def test_one_unlocked_door_is_enough(ccs2_body: dict[str, Any]) -> None:
    state = _vehicle(ccs2_body)
    del state["Cabin"]["Door"]["Row2"]["Right"]["Lock"]
    state["Cabin"]["Door"]["Row1"]["Driver"]["Lock"] = 1
    assert parse_ccs2_status(ccs2_body).doors_locked is False


def test_no_remaining_time_means_not_charging(ccs2_body: dict[str, Any]) -> None:
    _vehicle(ccs2_body)["Green"]["ChargingInformation"]["Charging"]["RemainTime"] = 0
    status = parse_ccs2_status(ccs2_body)
    assert status.charging is False
    assert status.charge_remaining_minutes == 0


@pytest.mark.parametrize("reliability", [1, "1"])
def test_unreliable_aux_battery_is_unknown(ccs2_body: dict[str, Any], reliability: Any) -> None:
    _vehicle(ccs2_body)["Electronics"]["Battery"]["SensorReliability"] = reliability
    assert parse_ccs2_status(ccs2_body).aux_battery_level is None


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (0.0, 0.0, (None, None)),
        (0.0, 139.0, (0.0, 139.0)),
        (91.0, 139.0, (None, None)),
        ("35.5", "139.5", (35.5, 139.5)),
    ],
)
def test_location(ccs2_body: dict[str, Any], latitude: Any, longitude: Any, expected: Any) -> None:
    _vehicle(ccs2_body)["Location"]["GeoCoord"] = {"Latitude": latitude, "Longitude": longitude}
    status = parse_ccs2_status(ccs2_body)
    assert (status.latitude, status.longitude) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20261012010000", datetime(2026, 10, 12, 1, 0, tzinfo=UTC)),
        ("20261012010000.5", datetime(2026, 10, 12, 1, 0, 0, 500000, tzinfo=UTC)),
        ("2026-10-12T10:00:00+09:00", datetime(2026, 10, 12, 1, 0, tzinfo=UTC)),
        ("20261312010000", None),
        ("not a date", None),
        (20261012010000, None),
    ],
)
def test_parse_timestamp(value: Any, expected: datetime | None) -> None:
    assert parse_timestamp(value) == expected


@pytest.mark.parametrize("body", [None, [], {}, {"resMsg": {}}, {"resMsg": {"state": {"Vehicle": []}}}])
def test_unknown_envelope(body: Any) -> None:
    with pytest.raises(UnsupportedResponseError):
        parse_ccs2_status(body)
