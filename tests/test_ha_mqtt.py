from types import SimpleNamespace

import pytest

from ha_addon.service import MappingSettings, NeoHubMQTTBridge, PahoMQTTAdapter, _mqtt_settings_from_options, slugify
from neohub.neohub import NeoHub


class FakeNeoHubClient:
    def __init__(self):
        self.temperature_calls = []
        self.mode_calls = []
        self.get_data_calls = []
        self.devices = [
            SimpleNamespace(deviceid="hub-1", devicename="Main Hub", online=True, type="neohub", version=1)
        ]
        self.zones = [
            SimpleNamespace(
                ZONE_NAME="Kitchen UFH",
                DEVICE_ID=101,
                ACTUAL_TEMP="19.5",
                SET_TEMP="21.0",
                HEAT_ON=True,
                HC_MODE="HEAT",
                RELATIVE_HUMIDITY=45,
                CURRENT_FLOOR_TEMPERATURE="18.2",
                LOW_BATTERY=False,
                WINDOW_OPEN=False,
                TIMER_ON=True,
                MODULATION_LEVEL=33,
            ),
            SimpleNamespace(
                ZONE_NAME="Garden Socket",
                DEVICE_ID=102,
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
        self.get_data_calls.append(device_id)
        assert device_id in {"hub-1", "hub-2"}
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

    object_id = "neohub_main_hub_kitchen_ufh_hub_1"
    discovery_topic = f"homeassistant/climate/{object_id}/config"
    discovery = payload_for(fake_mqtt, discovery_topic)

    assert discovery["name"] is None
    assert discovery["device"]["name"] == "NeoHub Kitchen UFH"
    assert discovery["unique_id"] == f"neohub_mqtt_v2_{object_id}"
    assert discovery["device"]["via_device"] == "neohub_mqtt_v2_hub_hub-1"
    assert discovery["current_temperature_topic"] == f"neohub/{object_id}/current_temperature"
    assert discovery["temperature_state_topic"] == f"neohub/{object_id}/target_temperature"
    assert discovery["temperature_command_topic"] == f"neohub/{object_id}/set_temperature"
    assert discovery["mode_command_topic"] == f"neohub/{object_id}/set_mode"
    assert discovery["modes"] == ["heat", "cool", "fan_only", "off"]

    assert payload_for(fake_mqtt, "homeassistant/binary_sensor/neohub_hub_main_hub_hub_1_online/config")["device_class"] == "connectivity"
    assert payload_for(fake_mqtt, "neohub/neohub_hub_main_hub_hub_1/availability") == "online"

    assert payload_for(fake_mqtt, f"neohub/{object_id}/current_temperature") == 19.5
    assert payload_for(fake_mqtt, f"neohub/{object_id}/target_temperature") == 21.0
    assert payload_for(fake_mqtt, f"neohub/{object_id}/action") == "heating"
    assert payload_for(fake_mqtt, f"neohub/{object_id}/humidity") == 45
    assert payload_for(fake_mqtt, f"neohub/{object_id}/availability") == "online"
    assert payload_for(fake_mqtt, f"neohub/{object_id}/floor_temperature") == 18.2
    assert payload_for(fake_mqtt, f"neohub/{object_id}/modulation_level") == 33
    assert payload_for(fake_mqtt, f"neohub/{object_id}/window_open") == "OFF"
    assert payload_for(fake_mqtt, f"neohub/{object_id}/heat_on") == "ON"

    assert f"neohub/{object_id}/set_temperature" in fake_mqtt.subscriptions
    assert f"neohub/{object_id}/set_mode" in fake_mqtt.subscriptions


def test_bridge_publishes_switch_discovery_for_socket_zone():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_garden_socket_hub_1"
    discovery = payload_for(fake_mqtt, f"homeassistant/switch/{object_id}/config")

    assert discovery["name"] is None
    assert discovery["device"]["name"] == "NeoHub Garden Socket"
    assert discovery["unique_id"] == f"neohub_mqtt_v2_{object_id}"
    assert discovery["state_topic"] == f"neohub/{object_id}/state"
    assert discovery["command_topic"] == f"neohub/{object_id}/set_mode"
    assert payload_for(fake_mqtt, f"neohub/{object_id}/state") == "OFF"


def test_bridge_routes_mqtt_commands_to_neohub_control_methods():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_kitchen_ufh_hub_1"
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

    object_id = "neohub_main_hub_kitchen_ufh_hub_1"
    with pytest.raises(ValueError):
        bridge.handle_message(f"neohub/{object_id}/set_temperature", "not-a-number")

    assert fake_client.temperature_calls == []


def test_publish_all_fetches_data_when_online_field_is_missing():
    fake_client = FakeNeoHubClient()
    delattr(fake_client.devices[0], "online")
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    assert fake_client.get_data_calls == ["hub-1"]
    assert payload_for(fake_mqtt, "homeassistant/climate/neohub_main_hub_kitchen_ufh_hub_1/config")


def test_multi_hub_duplicate_names_do_not_collide_and_route_commands_to_correct_hub():
    fake_client = FakeNeoHubClient()
    fake_client.devices = [
        SimpleNamespace(deviceid="hub-1", devicename="Shared Hub", online=True, type="neohub", version=1),
        SimpleNamespace(deviceid="hub-2", devicename="Shared Hub", online=True, type="neohub", version=1),
    ]
    fake_client.zones = [SimpleNamespace(ZONE_NAME="Kitchen", DEVICE_ID=1, ACTUAL_TEMP="20", SET_TEMP="21", HEAT_ON=False)]
    fake_mqtt = FakeMQTT()
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt)

    bridge.startup()
    bridge.publish_all()

    first = "neohub_shared_hub_kitchen_hub_1"
    second = "neohub_shared_hub_kitchen_hub_2"
    assert payload_for(fake_mqtt, f"homeassistant/climate/{first}/config")["unique_id"] == f"neohub_mqtt_v2_{first}"
    assert payload_for(fake_mqtt, f"homeassistant/climate/{second}/config")["unique_id"] == f"neohub_mqtt_v2_{second}"

    bridge.handle_message(f"neohub/{first}/set_temperature", "20.5")
    bridge.handle_message(f"neohub/{second}/set_temperature", "22")

    assert fake_client.temperature_calls == [("hub-1", "Kitchen", 20.5), ("hub-2", "Kitchen", 22.0)]


def test_zone_and_room_mapping_are_published_as_device_metadata_and_attributes():
    fake_client = FakeNeoHubClient()
    fake_mqtt = FakeMQTT()
    mapping = MappingSettings(
        property_name="Example House",
        hub_zones=({"hub_id": "hub-1", "zone": "East Wing"},),
        room_mappings=({"hub_id": "hub-1", "thermostat": "Kitchen UFH", "room": "Kitchen", "zone": "Family Zone"},),
    )
    bridge = NeoHubMQTTBridge(fake_client, fake_mqtt, mapping=mapping)

    bridge.startup()
    bridge.publish_all()

    object_id = "neohub_main_hub_kitchen_ufh_hub_1"
    discovery = payload_for(fake_mqtt, f"homeassistant/climate/{object_id}/config")
    attrs = payload_for(fake_mqtt, f"neohub/{object_id}/attributes")

    assert discovery["name"] is None
    assert discovery["device"]["name"] == "NeoHub Kitchen (Kitchen UFH)"
    assert discovery["device"]["suggested_area"] == "Kitchen"
    assert attrs["property_name"] == "Example House"
    assert attrs["property_zone"] == "Family Zone"
    assert attrs["room"] == "Kitchen"
    assert attrs["hub_name"] == "Main Hub"


def test_mqtt_settings_prefer_supervisor_service_credentials(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "host": "core-mosquitto",
                "port": 1883,
                "username": "addons",
                "password": "secret",
                "ssl": False,
                "protocol": "3.1.1",
            }

    monkeypatch.setenv("SUPERVISOR_TOKEN", "token")
    monkeypatch.setattr("ha_addon.service.requests.get", lambda *args, **kwargs: Response())

    settings = _mqtt_settings_from_options({"mqtt": {"host": "", "username": "", "password": ""}})

    assert settings.host == "core-mosquitto"
    assert settings.username == "addons"
    assert settings.password == "secret"
    assert settings.source == "supervisor-service"


def test_neohub_url_without_trailing_slash_is_normalised():
    client = NeoHub("user", "pass", "https://neohub.co.uk")

    assert client.url == "https://neohub.co.uk/"


def test_mqtt_ssl_false_option_overrides_environment(monkeypatch):
    monkeypatch.setenv("MQTT_SSL", "true")

    settings = _mqtt_settings_from_options({"mqtt": {"host": "broker.local", "ssl": False}})

    assert settings.host == "broker.local"
    assert settings.ssl_enabled is False
    assert settings.source == "explicit-options"


def test_paho_disconnect_callback_accepts_v1_and_v2_signatures():
    class Connected:
        def __init__(self):
            self.clear_calls = 0

        def clear(self):
            self.clear_calls += 1

    adapter = object.__new__(PahoMQTTAdapter)
    adapter._connected = Connected()

    adapter._on_disconnect(None, None, 0)
    adapter._on_disconnect(None, None, object(), 0, object())

    assert adapter._connected.clear_calls == 2


def test_neohub_api_requests_use_configured_timeout():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"STATUS": 1, "TOKEN": "token", "devices": []}

    class Session:
        def __init__(self):
            self.calls = []

        def post(self, url, data, timeout):
            self.calls.append({"url": url, "data": data, "timeout": timeout})
            return Response()

    client = NeoHub("user", "pass", "https://neohub.co.uk", request_timeout=7)
    client.session = Session()

    client.login()

    assert client.session.calls[0]["url"] == "https://neohub.co.uk/hm_user_login"
    assert client.session.calls[0]["timeout"] == 7
