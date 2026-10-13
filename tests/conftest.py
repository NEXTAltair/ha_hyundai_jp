"""テスト共通のフィクスチャ。実サーバーと実車には接続しない。"""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hyundai_bluelink_jp.api import BluelinkJpClient, Vehicle, parse_ccs2_status
from custom_components.hyundai_bluelink_jp.const import DOMAIN

EMAIL = "test@example.invalid"
PASSWORD = "test-password"
VEHICLE = Vehicle(vehicle_id="test-car", name="IONIQ 5", model="IONIQ 5", is_ev=True)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """custom_components の統合を読み込めるようにする。"""


@pytest.fixture
def ccs2_body() -> dict[str, Any]:
    """CCS2 の状態取得の応答を模した合成データ。"""
    return {
        "retCode": "S",
        "resCode": "0000",
        "resMsg": {
            "state": {
                "Vehicle": {
                    "Date": "20261012010000.123",
                    "DrivingReady": 0,
                    "Drivetrain": {
                        "Odometer": 10908.5,
                        "FuelSystem": {"DTE": {"Total": 601.5, "Unit": 1}},
                    },
                    "Electronics": {"Battery": {"Level": 99.5, "SensorReliability": 0}},
                    "Green": {
                        "BatteryManagement": {"BatteryRemain": {"Ratio": 73}},
                        "ChargingInformation": {
                            "ConnectorFastening": {"State": 1},
                            "Charging": {"RemainTime": 30},
                        },
                    },
                    "Cabin": {
                        "Door": {
                            "Row1": {
                                "Driver": {"Lock": 0, "Open": 0},
                                "Passenger": {"Lock": 0, "Open": 0},
                            },
                            "Row2": {
                                "Left": {"Lock": 0, "Open": 0},
                                "Right": {"Lock": 0, "Open": 0},
                            },
                        }
                    },
                    "Chassis": {"Axle": {"Tire": {"PressureLow": 0}}},
                    "Body": {"Hood": {"Open": 0}, "Trunk": {"Open": 1}},
                    "Location": {"GeoCoord": {"Latitude": 35.0, "Longitude": 139.0}},
                }
            }
        },
    }


@pytest.fixture
def mock_client(ccs2_body: dict[str, Any]) -> Iterator[SimpleNamespace]:
    """通信するメソッドだけを差し替えたクライアント。"""
    with (
        patch.object(BluelinkJpClient, "async_login", autospec=True) as login,
        patch.object(
            BluelinkJpClient, "async_get_vehicles", autospec=True, return_value=[VEHICLE]
        ) as vehicles,
        patch.object(
            BluelinkJpClient,
            "async_get_vehicle_status",
            autospec=True,
            return_value=parse_ccs2_status(ccs2_body),
        ) as status,
    ):
        yield SimpleNamespace(login=login, vehicles=vehicles, status=status)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """設定済みのアカウント。"""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Hyundai Bluelink Japan",
        data={CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD},
        unique_id=EMAIL,
    )
