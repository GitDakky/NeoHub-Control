from __future__ import annotations

import json
import logging
import os
import re
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests
from neohub import NeoHub

_LOGGER = logging.getLogger(__name__)
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_BASE_TOPIC = "neohub"


def slugify(value: str) -> str:
    """Return a stable Home Assistant-safe object id fragment."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_")


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _read_addon_options(path: str = "/data/options.json") -> dict[str, Any]:
    options_path = Path(path)
    if not options_path.exists():
        return {}
    return json.loads(options_path.read_text(encoding="utf-8"))


@dataclass
class MQTTSettings:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "neohub-control-addon"


class PahoMQTTAdapter:
    """Small paho-mqtt adapter matching the bridge's tiny publish/subscribe API."""

    def __init__(self, settings: MQTTSettings, message_handler: Callable[[str, str], None]):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - covered in container runtime
            raise RuntimeError("paho-mqtt is required for the Home Assistant add-on") from exc

        self._client = mqtt.Client(client_id=settings.client_id)
        if settings.username:
            self._client.username_pw_set(settings.username, settings.password)
        self._client.on_message = self._on_message
        self._message_handler = message_handler
        self._client.connect(settings.host, settings.port, keepalive=60)
        self._client.loop_start()

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        self._message_handler(message.topic, payload)

    def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, separators=(",", ":"))
        self._client.publish(topic, payload, retain=retain)

    def subscribe(self, topic: str) -> None:
        self._client.subscribe(topic)

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


@dataclass
class ZoneBinding:
    object_id: str
    device_id: str
    device_name: str
    zone_name: str
    kind: str


class NeoHubMQTTBridge:
    """Publish NeoHub devices into Home Assistant via MQTT discovery."""

    def __init__(
        self,
        neohub_client: Any,
        mqtt_client: Any,
        *,
        discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
        base_topic: str = DEFAULT_BASE_TOPIC,
    ):
        self.neohub_client = neohub_client
        self.mqtt = mqtt_client
        self.discovery_prefix = discovery_prefix.strip("/")
        self.base_topic = base_topic.strip("/")
        self.devices: list[Any] = []
        self.bindings_by_object_id: dict[str, ZoneBinding] = {}
        self.bindings_by_command_topic: dict[str, ZoneBinding] = {}

    def startup(self) -> None:
        self.devices = list(self.neohub_client.login())
        _LOGGER.info("Logged into NeoHub and found %s devices", len(self.devices))

    def publish_all(self) -> None:
        for device in self.devices:
            if not getattr(device, "online", False):
                self._publish_device_availability(device, "offline")
                continue
            data = self.neohub_client.get_data(device.deviceid)
            zones = data.get("CACHE_VALUE", {}).get("live_info", {}).get("devices", [])
            for zone in zones:
                self._publish_zone(device, zone)

    def handle_message(self, topic: str, payload: str) -> None:
        binding = self.bindings_by_command_topic.get(topic)
        if binding is None:
            _LOGGER.debug("Ignoring unregistered MQTT topic %s", topic)
            return

        if topic.endswith("/set_temperature"):
            temperature = _float_or_none(payload)
            if temperature is None:
                raise ValueError(f"Invalid temperature command for {binding.zone_name}: {payload!r}")
            self.neohub_client.set_temperature(binding.device_id, binding.zone_name, temperature)
            _LOGGER.info("Set %s to %.1f°C", binding.zone_name, temperature)
            return

        if topic.endswith("/set_mode"):
            mode = self._normalise_mode(payload)
            self.neohub_client.set_mode(binding.device_id, binding.zone_name, mode)
            _LOGGER.info("Set %s mode to %s", binding.zone_name, mode)
            return

        _LOGGER.debug("No command handler for MQTT topic %s", topic)

    def _publish_zone(self, device: Any, zone: Any) -> None:
        kind = self._zone_kind(zone)
        object_id = f"neohub_{slugify(getattr(device, 'devicename', 'device'))}_{slugify(getattr(zone, 'ZONE_NAME', 'zone'))}"
        binding = ZoneBinding(
            object_id=object_id,
            device_id=device.deviceid,
            device_name=getattr(device, "devicename", "NeoHub"),
            zone_name=getattr(zone, "ZONE_NAME", object_id),
            kind=kind,
        )
        self.bindings_by_object_id[object_id] = binding

        if kind == "socket":
            self._publish_switch_discovery(binding, device)
            self._publish_switch_state(binding, zone)
        else:
            self._publish_climate_discovery(binding, device)
            self._publish_climate_state(binding, zone)

    def _publish_climate_discovery(self, binding: ZoneBinding, device: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        discovery = {
            "name": binding.zone_name,
            "unique_id": binding.object_id,
            "object_id": binding.object_id,
            "device": self._device_info(device),
            "availability_topic": f"{topic_prefix}/availability",
            "current_temperature_topic": f"{topic_prefix}/current_temperature",
            "temperature_state_topic": f"{topic_prefix}/target_temperature",
            "temperature_command_topic": f"{topic_prefix}/set_temperature",
            "temperature_unit": "C",
            "min_temp": 5,
            "max_temp": 30,
            "temp_step": 0.5,
            "mode_state_topic": f"{topic_prefix}/mode",
            "mode_command_topic": f"{topic_prefix}/set_mode",
            "modes": ["heat", "cool", "fan_only", "off"],
            "action_topic": f"{topic_prefix}/action",
            "humidity_state_topic": f"{topic_prefix}/humidity",
            "json_attributes_topic": f"{topic_prefix}/attributes",
        }
        self._publish_json(f"{self.discovery_prefix}/climate/{binding.object_id}/config", discovery, retain=True)
        self._subscribe_command(binding, f"{topic_prefix}/set_temperature")
        self._subscribe_command(binding, f"{topic_prefix}/set_mode")

    def _publish_switch_discovery(self, binding: ZoneBinding, device: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        discovery = {
            "name": binding.zone_name,
            "unique_id": binding.object_id,
            "object_id": binding.object_id,
            "device": self._device_info(device),
            "availability_topic": f"{topic_prefix}/availability",
            "state_topic": f"{topic_prefix}/state",
            "command_topic": f"{topic_prefix}/set_mode",
            "payload_on": "ON",
            "payload_off": "OFF",
            "json_attributes_topic": f"{topic_prefix}/attributes",
        }
        self._publish_json(f"{self.discovery_prefix}/switch/{binding.object_id}/config", discovery, retain=True)
        self._subscribe_command(binding, f"{topic_prefix}/set_mode")

    def _publish_climate_state(self, binding: ZoneBinding, zone: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        actual_temp = _float_or_none(getattr(zone, "ACTUAL_TEMP", None))
        target_temp = _float_or_none(getattr(zone, "SET_TEMP", None))
        mode = self._ha_mode(getattr(zone, "HC_MODE", None), getattr(zone, "HEAT_MODE", False))
        action = "heating" if _bool(getattr(zone, "HEAT_ON", False)) else "idle"

        self.mqtt.publish(f"{topic_prefix}/availability", "online", retain=True)
        if actual_temp is not None:
            self.mqtt.publish(f"{topic_prefix}/current_temperature", actual_temp, retain=True)
        if target_temp is not None:
            self.mqtt.publish(f"{topic_prefix}/target_temperature", target_temp, retain=True)
        self.mqtt.publish(f"{topic_prefix}/mode", mode, retain=True)
        self.mqtt.publish(f"{topic_prefix}/action", action, retain=True)
        self.mqtt.publish(f"{topic_prefix}/humidity", getattr(zone, "RELATIVE_HUMIDITY", 0), retain=True)
        self._publish_json(f"{topic_prefix}/attributes", self._zone_attributes(zone), retain=True)

    def _publish_switch_state(self, binding: ZoneBinding, zone: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        state = "ON" if _bool(getattr(zone, "HEAT_ON", False)) else "OFF"
        self.mqtt.publish(f"{topic_prefix}/availability", "online", retain=True)
        self.mqtt.publish(f"{topic_prefix}/state", state, retain=True)
        self._publish_json(f"{topic_prefix}/attributes", self._zone_attributes(zone), retain=True)

    def _publish_device_availability(self, device: Any, availability: str) -> None:
        device_name = slugify(getattr(device, "devicename", "device"))
        self.mqtt.publish(f"{self.base_topic}/neohub_{device_name}/availability", availability, retain=True)

    def _publish_json(self, topic: str, payload: dict[str, Any], retain: bool = False) -> None:
        self.mqtt.publish(topic, payload, retain=retain)

    def _subscribe_command(self, binding: ZoneBinding, topic: str) -> None:
        self.bindings_by_command_topic[topic] = binding
        self.mqtt.subscribe(topic)

    def _topic(self, object_id: str) -> str:
        return f"{self.base_topic}/{object_id}"

    def _device_info(self, device: Any) -> dict[str, Any]:
        return {
            "identifiers": [f"neohub_{getattr(device, 'deviceid', slugify(getattr(device, 'devicename', 'device')))}"],
            "name": getattr(device, "devicename", "NeoHub"),
            "manufacturer": "Heatmiser",
            "model": getattr(device, "type", "NeoHub"),
            "sw_version": str(getattr(device, "version", "")),
        }

    def _zone_attributes(self, zone: Any) -> dict[str, Any]:
        return {
            "zone_name": getattr(zone, "ZONE_NAME", None),
            "window_open": _bool(getattr(zone, "WINDOW_OPEN", False)),
            "low_battery": _bool(getattr(zone, "LOW_BATTERY", False)),
            "timer_on": _bool(getattr(zone, "TIMER_ON", False)),
            "modulation_level": getattr(zone, "MODULATION_LEVEL", 0),
        }

    def _zone_kind(self, zone: Any) -> str:
        zone_name = str(getattr(zone, "ZONE_NAME", ""))
        actual_temp = str(getattr(zone, "ACTUAL_TEMP", ""))
        if actual_temp == "255.255" or "socket" in zone_name.lower():
            return "socket"
        return "climate"

    def _ha_mode(self, api_mode: Any, heat_mode: Any) -> str:
        if isinstance(api_mode, str):
            mode = api_mode.strip().upper()
            if mode == "HEAT":
                return "heat"
            if mode == "COOL":
                return "cool"
            if mode == "VENT":
                return "fan_only"
            if mode == "OFF":
                return "off"
        return "heat" if _bool(heat_mode) else "off"

    def _normalise_mode(self, payload: str) -> str:
        requested = payload.strip().upper()
        mapping = {
            "HEAT": "HEAT",
            "COOL": "COOL",
            "VENT": "VENT",
            "FAN_ONLY": "VENT",
            "FAN ONLY": "VENT",
            "ON": "HEAT",
            "OFF": "OFF",
        }
        if requested not in mapping:
            raise ValueError(f"Unsupported mode command: {payload!r}")
        return mapping[requested]


def _mqtt_settings_from_options(options: dict[str, Any]) -> MQTTSettings:
    mqtt_options = options.get("mqtt") or {}
    return MQTTSettings(
        host=mqtt_options.get("host") or os.environ.get("MQTT_HOST") or "core-mosquitto",
        port=int(mqtt_options.get("port") or os.environ.get("MQTT_PORT") or 1883),
        username=mqtt_options.get("username") or os.environ.get("MQTT_USERNAME"),
        password=mqtt_options.get("password") or os.environ.get("MQTT_PASSWORD"),
        client_id=mqtt_options.get("client_id") or "neohub-control-addon",
    )


def build_bridge_from_options(options: dict[str, Any]) -> tuple[NeoHubMQTTBridge, PahoMQTTAdapter]:
    username = options.get("username") or os.environ.get("NEOHUB_USERNAME")
    password = options.get("password") or os.environ.get("NEOHUB_PASSWORD")
    if not username or not password:
        raise RuntimeError("NeoHub username and password must be configured")

    neohub_url = options.get("url") or os.environ.get("NEOHUB_URL")
    client = NeoHub(username=username, password=password, url=neohub_url)
    bridge_holder: dict[str, NeoHubMQTTBridge] = {}

    def on_message(topic: str, payload: str) -> None:
        bridge_holder["bridge"].handle_message(topic, payload)

    mqtt = PahoMQTTAdapter(_mqtt_settings_from_options(options), on_message)
    bridge = NeoHubMQTTBridge(
        client,
        mqtt,
        discovery_prefix=options.get("discovery_prefix", DEFAULT_DISCOVERY_PREFIX),
        base_topic=options.get("base_topic", DEFAULT_BASE_TOPIC),
    )
    bridge_holder["bridge"] = bridge
    return bridge, mqtt


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    options = _read_addon_options()
    poll_interval = int(options.get("poll_interval", os.environ.get("POLL_INTERVAL", 60)))
    bridge, mqtt = build_bridge_from_options(options)
    running = True

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    bridge.startup()
    while running:
        try:
            bridge.publish_all()
        except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
            _LOGGER.exception("Failed to publish NeoHub state: %s", exc)
        time.sleep(poll_interval)
    mqtt.stop()


if __name__ == "__main__":
    main()
