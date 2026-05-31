from types import SimpleNamespace

import pytest

from ha_addon.service import NeoHubMQTTBridge, slugify


class FakeNeoHubClient:
    def __init__(self):
        self.temperature_calls = []
        self.mode_calls = []
        self.devices = [
            SimpleNamespace(deviceid="hub-1", devicename="Main Hub", online=True, type="neohub", version=1)
        ]
        self.zones = [
            SimpleNamespace(
                ZONE_NAME="Kitchen UFH",
                ACTUAL_TEMP="19.5",
                SET_TEMP="21.0",
                HEAT_ON=True,
                HC_MODE="HEAT",
                RELATIVE_HUMIDITY=45,
                LOW_BATTERY=False,
                WINDOW_OPEN=False,
                TIMER_ON=True,
                MODULATION_LEVEL=33,
            ),
            SimpleNamespace(
                ZONE_NAME="Garden Socket",
                ACTUAL_TEMP="255.255",
                SET_TEMP="0",
                HEAT_ON=False,
                HC_MODE=None,
                RELATIVE_HUMIDITY=0,
                LOW_BATTERY=False,
                WINDOW_OPEN=False,
                TIMER_ON=False,
                MODULATION_LEVEL=0,
            ),
        ]

    def login(self):
        return self.devices

    def get_data(self, device_id):
        assert device_id == "hub-1"
        return {"CACHE_VALUE": {"live_info": {"devices": self.zones}}}

    def set_temperature(self, device_id, zone_name, temperature):
        self.temperature_calls.append((device_id, zone_name, temperature))
        return {"STATUS": 1}

    def set_mode(self, device_id, zone_name, mode):
        self.mode_calls.append((device_id, zone_name, mode))
        return {"STATUS": 1}


class FakeMQTT:
    def __init__(self):
        self.published = []
        self.subscriptions = []

    def publish(self, topic, payload, retain=False):
        self.published.append((topic, payload, retain))

    def subscribe(self, topic):
        self.subscriptions.append(topic)


def payload_for(fake_mqtt, topic):
    matches = [payload for t, payload, _ in fake_mqtt.published if t == topic]
    assert matches, f"No payload published for {topic}; got topics {[t for t, _, _ in fake_mqtt.published]}"
    return matches[-1]


def test_slugify_creates_stable_home_assistant_ids():
    assert slugify("Main Hub Kitchen UFH") == "main_hub_kitchen_ufh"
    assert slugify("Hall / Landing (2)") == "hall_landing_2"


def test_bridge_publishes_climate_discovery_and_state_for_thermostat_zone():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt, discovery_prefix="homeassistant")

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_kitchen_ufh"
    discovery_topic = f"homeassistant/climate/{object_id}/config"
    discovery = payload_for(fake_mqtt, discovery_topic)

    assert discovery["name"] == "Kitchen UFH"
    assert discovery["unique_id"] == object_id
    assert discovery["current_temperature_topic"] == f"neohub/{object_id}/current_temperature"
    assert discovery["temperature_state_topic"] == f"neohub/{object_id}/target_temperature"
    assert discovery["temperature_command_topic"] == f"neohub/{object_id}/set_temperature"
    assert discovery["mode_command_topic"] == f"neohub/{object_id}/set_mode"
    assert discovery["modes"] == ["heat", "cool", "fan_only", "off"]

    assert payload_for(fake_mqtt, f"neohub/{object_id}/current_temperature") == 19.5
    assert payload_for(fake_mqtt, f"neohub/{object_id}/target_temperature") == 21.0
    assert payload_for(fake_mqtt, f"neohub/{object_id}/action") == "heating"
    assert payload_for(fake_mqtt, f"neohub/{object_id}/humidity") == 45
    assert payload_for(fake_mqtt, f"neohub/{object_id}/availability") == "online"

    assert f"neohub/{object_id}/set_temperature" in fake_mqtt.subscriptions
    assert f"neohub/{object_id}/set_mode" in fake_mqtt.subscriptions


def test_bridge_publishes_switch_discovery_for_socket_zone():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_garden_socket"
    discovery = payload_for(fake_mqtt, f"homeassistant/switch/{object_id}/config")

    assert discovery["name"] == "Garden Socket"
    assert discovery["unique_id"] == object_id
    assert discovery["state_topic"] == f"neohub/{object_id}/state"
    assert discovery["command_topic"] == f"neohub/{object_id}/set_mode"
    assert payload_for(fake_mqtt, f"neohub/{object_id}/state") == "OFF"


def test_bridge_routes_mqtt_commands_to_neohub_control_methods():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_kitchen_ufh"
    bridge.handle_message(f"neohub/{object_id}/set_temperature", "22.5")
    bridge.handle_message(f"neohub/{object_id}/set_mode", "cool")

    assert fake_client.temperature_calls == [("hub-1", "Kitchen UFH", 22.5)]
    assert fake_client.mode_calls == [("hub-1", "Kitchen UFH", "COOL")]


def test_invalid_temperature_command_is_rejected_without_calling_api():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_kitchen_ufh"
    with pytest.raises(ValueError):
        bridge.handle_message(f"neohub/{object_id}/set_temperature", "not-a-number")

    assert fake_client.temperature_calls == []
