from __future__ import annotations

import json
import logging
import os
import re
import signal
import ssl
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable

import requests
from neohub import NeoHub

_LOGGER = logging.getLogger(__name__)
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_BASE_TOPIC = "neohub"
SUPERVISOR_MQTT_URL = "http://supervisor/services/mqtt"


def slugify(value: str) -> str:
    """Return a stable Home Assistant-safe object id fragment."""
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return re.sub(r"_+", "_", value).strip("_") or "unknown"


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number == 255.255:
        return None
    return number


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "online", "heat", "heating"}
    return bool(value)


def _explicit_false(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, (int, float)) and value == 0:
        return True
    if isinstance(value, str) and value.strip().lower() in {"0", "false", "no", "off", "offline"}:
        return True
    return False


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
    ssl_enabled: bool = False
    protocol: str | None = None
    source: str = "options"


@dataclass
class MappingSettings:
    property_name: str = "Home"
    hub_zones: tuple[dict[str, Any], ...] = ()
    room_mappings: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> "MappingSettings":
        return cls(
            property_name=str(options.get("property_name") or "Home"),
            hub_zones=tuple(options.get("hub_zones") or ()),
            room_mappings=tuple(options.get("room_mappings") or ()),
        )

    def hub_zone_for(self, device: Any) -> str | None:
        device_id = str(getattr(device, "deviceid", "") or "")
        device_name = str(getattr(device, "devicename", "") or "")
        for item in self.hub_zones:
            if _mapping_matches(item, device_id, device_name):
                return str(item.get("zone") or item.get("property_zone") or "").strip() or None
        return None

    def room_for(self, device: Any, zone_name: str) -> tuple[str | None, str | None]:
        device_id = str(getattr(device, "deviceid", "") or "")
        device_name = str(getattr(device, "devicename", "") or "")
        for item in self.room_mappings:
            thermostat = str(item.get("thermostat") or item.get("zone_name") or item.get("point") or "")
            if thermostat and slugify(thermostat) != slugify(zone_name):
                continue
            if _mapping_matches(item, device_id, device_name):
                room = str(item.get("room") or "").strip() or None
                zone = str(item.get("zone") or item.get("property_zone") or "").strip() or None
                return room, zone
        return None, None


def _mapping_matches(item: dict[str, Any], device_id: str, device_name: str) -> bool:
    wanted_id = str(item.get("hub_id") or item.get("device_id") or "").strip()
    wanted_name = str(item.get("hub_name") or item.get("device_name") or "").strip()
    id_matches = not wanted_id or wanted_id == device_id
    name_matches = not wanted_name or slugify(wanted_name) == slugify(device_name)
    return id_matches and name_matches


class PahoMQTTAdapter:
    """Small paho-mqtt adapter with explicit connect/publish verification."""

    def __init__(self, settings: MQTTSettings, message_handler: Callable[[str, str], None], *, connect_timeout: int = 20):
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - covered in container runtime
            raise RuntimeError("paho-mqtt is required for the Home Assistant add-on") from exc

        self._connected = Event()
        self._connect_error: str | None = None
        self._client = self._build_client(mqtt, settings.client_id)
        if settings.username:
            self._client.username_pw_set(settings.username, settings.password)
        if settings.ssl_enabled:
            self._client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._message_handler = message_handler

        _LOGGER.info("Connecting to MQTT broker %s:%s using %s settings", settings.host, settings.port, settings.source)
        self._client.connect(settings.host, settings.port, keepalive=60)
        self._client.loop_start()
        if not self._connected.wait(connect_timeout):
            raise RuntimeError(f"Timed out connecting to MQTT broker {settings.host}:{settings.port}")
        if self._connect_error:
            raise RuntimeError(self._connect_error)

    @staticmethod
    def _build_client(mqtt: Any, client_id: str) -> Any:
        callback_api = getattr(mqtt, "CallbackAPIVersion", None)
        if callback_api is not None:
            try:
                return mqtt.Client(callback_api.VERSION2, client_id=client_id)
            except Exception:  # pragma: no cover - compatibility fallback
                pass
        return mqtt.Client(client_id=client_id)

    def _on_connect(self, _client: Any, _userdata: Any, _flags: Any, reason_code: Any, _properties: Any = None) -> None:
        code = getattr(reason_code, "value", reason_code)
        try:
            code_int = int(code)
        except (TypeError, ValueError):
            code_int = 0 if str(reason_code).lower() == "success" else -1
        if code_int != 0:
            self._connect_error = f"MQTT connection failed: {reason_code}"
        else:
            _LOGGER.info("Connected to MQTT broker")
        self._connected.set()

    def _on_disconnect(self, _client: Any, _userdata: Any, reason_code: Any = None, _properties: Any = None) -> None:
        if reason_code not in (None, 0):
            _LOGGER.warning("Disconnected from MQTT broker: %s", reason_code)
        self._connected.clear()

    def _on_message(self, _client: Any, _userdata: Any, message: Any) -> None:
        payload = message.payload.decode("utf-8", errors="replace")
        try:
            self._message_handler(message.topic, payload)
        except Exception:  # pragma: no cover - defensive runtime logging
            _LOGGER.exception("Failed to handle MQTT command topic %s", message.topic)

    def publish(self, topic: str, payload: Any, retain: bool = False) -> None:
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, separators=(",", ":"))
        info = self._client.publish(topic, payload, qos=1, retain=retain)
        rc = getattr(info, "rc", 0)
        if rc:
            raise RuntimeError(f"MQTT publish rejected for {topic}: rc={rc}")
        wait = getattr(info, "wait_for_publish", None)
        if callable(wait):
            wait(timeout=10)
            is_published = getattr(info, "is_published", None)
            if callable(is_published) and not is_published():
                raise RuntimeError(f"MQTT publish timed out for {topic}")

    def subscribe(self, topic: str) -> None:
        result = self._client.subscribe(topic)
        rc = result[0] if isinstance(result, tuple) else getattr(result, "rc", 0)
        if rc:
            raise RuntimeError(f"MQTT subscribe rejected for {topic}: rc={rc}")

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
    property_name: str
    property_zone: str | None = None
    room: str | None = None


class NeoHubMQTTBridge:
    """Publish NeoHub devices into Home Assistant via MQTT discovery."""

    def __init__(
        self,
        neohub_client: Any,
        mqtt_client: Any,
        *,
        discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX,
        base_topic: str = DEFAULT_BASE_TOPIC,
        mapping: MappingSettings | None = None,
    ):
        self.neohub_client = neohub_client
        self.mqtt = mqtt_client
        self.discovery_prefix = discovery_prefix.strip("/")
        self.base_topic = base_topic.strip("/")
        self.mapping = mapping or MappingSettings()
        self.devices: list[Any] = []
        self.bindings_by_object_id: dict[str, ZoneBinding] = {}
        self.bindings_by_command_topic: dict[str, ZoneBinding] = {}

    def startup(self) -> None:
        self.devices = list(self.neohub_client.login())
        _LOGGER.info("Logged into NeoHub and found %s hub(s)", len(self.devices))

    def publish_all(self) -> None:
        published = 0
        for device in self.devices:
            if not self._device_is_online(device):
                _LOGGER.warning("NeoHub %s is offline; skipping point polling", getattr(device, "devicename", device))
                self._publish_hub_status(device, "offline")
                continue
            try:
                data = self.neohub_client.get_data(device.deviceid)
            except Exception:
                _LOGGER.exception("Failed to fetch NeoHub cache for hub %s", getattr(device, "devicename", device))
                self._publish_hub_status(device, "offline")
                continue
            zones = data.get("CACHE_VALUE", {}).get("live_info", {}).get("devices", [])
            if not zones:
                _LOGGER.warning("NeoHub %s returned no live_info.devices points", getattr(device, "devicename", device))
            for zone in zones:
                self._publish_zone(device, zone)
                published += 1
            self._publish_hub_status(device, "online")
        _LOGGER.info("Published %s NeoHub point(s) across %s hub(s)", published, len(self.devices))

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
            _LOGGER.info("Set %s/%s to %.1f°C", binding.device_name, binding.zone_name, temperature)
            return

        if topic.endswith("/set_mode"):
            mode = self._normalise_mode(payload)
            self.neohub_client.set_mode(binding.device_id, binding.zone_name, mode)
            _LOGGER.info("Set %s/%s mode to %s", binding.device_name, binding.zone_name, mode)
            return

        _LOGGER.debug("No command handler for MQTT topic %s", topic)

    def _publish_zone(self, device: Any, zone: Any) -> None:
        kind = self._zone_kind(zone)
        zone_name = str(_zone_get(zone, "ZONE_NAME", "point"))
        device_name = str(getattr(device, "devicename", "NeoHub"))
        object_id = self._object_id(device, zone_name)
        room, room_zone = self.mapping.room_for(device, zone_name)
        property_zone = room_zone or self.mapping.hub_zone_for(device)
        binding = ZoneBinding(
            object_id=object_id,
            device_id=str(getattr(device, "deviceid", "")),
            device_name=device_name,
            zone_name=zone_name,
            kind=kind,
            property_name=self.mapping.property_name,
            property_zone=property_zone,
            room=room,
        )
        self.bindings_by_object_id[object_id] = binding

        if kind == "socket":
            self._publish_switch_discovery(binding, device, zone)
            self._publish_switch_state(binding, zone)
        else:
            self._publish_climate_discovery(binding, device, zone)
            self._publish_climate_state(binding, zone)
            self._publish_diagnostic_entities(binding, device, zone)

    def _publish_climate_discovery(self, binding: ZoneBinding, device: Any, zone: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        discovery = {
            "name": self._friendly_entity_name(binding),
            "unique_id": binding.object_id,
            "object_id": binding.object_id,
            "device": self._zone_device_info(binding, device, zone),
            "availability_topic": f"{topic_prefix}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
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

    def _publish_switch_discovery(self, binding: ZoneBinding, device: Any, zone: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        discovery = {
            "name": self._friendly_entity_name(binding),
            "unique_id": binding.object_id,
            "object_id": binding.object_id,
            "device": self._zone_device_info(binding, device, zone),
            "availability_topic": f"{topic_prefix}/availability",
            "payload_available": "online",
            "payload_not_available": "offline",
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
        actual_temp = _float_or_none(_zone_get(zone, "ACTUAL_TEMP"))
        target_temp = _float_or_none(_zone_get(zone, "SET_TEMP"))
        mode = self._ha_mode(_zone_get(zone, "HC_MODE"), _zone_get(zone, "HEAT_MODE", False), _zone_get(zone, "STANDBY", False))
        action = "heating" if _bool(_zone_get(zone, "HEAT_ON", False)) else "idle"
        if _bool(_zone_get(zone, "COOL_ON", False)):
            action = "cooling"

        self.mqtt.publish(f"{topic_prefix}/availability", "offline" if _bool(_zone_get(zone, "OFFLINE", False)) else "online", retain=True)
        if actual_temp is not None:
            self.mqtt.publish(f"{topic_prefix}/current_temperature", actual_temp, retain=True)
        if target_temp is not None:
            self.mqtt.publish(f"{topic_prefix}/target_temperature", target_temp, retain=True)
        self.mqtt.publish(f"{topic_prefix}/mode", mode, retain=True)
        self.mqtt.publish(f"{topic_prefix}/action", action, retain=True)
        self.mqtt.publish(f"{topic_prefix}/humidity", _zone_get(zone, "RELATIVE_HUMIDITY", 0), retain=True)
        self._publish_json(f"{topic_prefix}/attributes", self._zone_attributes(binding, zone), retain=True)

    def _publish_switch_state(self, binding: ZoneBinding, zone: Any) -> None:
        topic_prefix = self._topic(binding.object_id)
        state = "ON" if _bool(_zone_get(zone, "HEAT_ON", False)) else "OFF"
        self.mqtt.publish(f"{topic_prefix}/availability", "offline" if _bool(_zone_get(zone, "OFFLINE", False)) else "online", retain=True)
        self.mqtt.publish(f"{topic_prefix}/state", state, retain=True)
        self._publish_json(f"{topic_prefix}/attributes", self._zone_attributes(binding, zone), retain=True)

    def _publish_diagnostic_entities(self, binding: ZoneBinding, device: Any, zone: Any) -> None:
        self._publish_sensor(binding, device, zone, "floor_temperature", "CURRENT_FLOOR_TEMPERATURE", "°C", "temperature")
        self._publish_sensor(binding, device, zone, "modulation_level", "MODULATION_LEVEL", "%", None)
        self._publish_binary_sensor(binding, device, zone, "window_open", "WINDOW_OPEN", "window")
        self._publish_binary_sensor(binding, device, zone, "low_battery", "LOW_BATTERY", "battery")
        self._publish_binary_sensor(binding, device, zone, "heat_on", "HEAT_ON", "heat")
        self._publish_binary_sensor(binding, device, zone, "cool_on", "COOL_ON", "cold")

    def _publish_sensor(self, binding: ZoneBinding, device: Any, zone: Any, key: str, field: str, unit: str | None, device_class: str | None) -> None:
        value = _float_or_none(_zone_get(zone, field))
        if value is None:
            return
        object_id = f"{binding.object_id}_{key}"
        topic = f"{self._topic(binding.object_id)}/{key}"
        payload: dict[str, Any] = {
            "name": f"{self._friendly_entity_name(binding)} {key.replace('_', ' ').title()}",
            "unique_id": object_id,
            "object_id": object_id,
            "device": self._zone_device_info(binding, device, zone),
            "availability_topic": f"{self._topic(binding.object_id)}/availability",
            "state_topic": topic,
            "entity_category": "diagnostic",
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        self._publish_json(f"{self.discovery_prefix}/sensor/{object_id}/config", payload, retain=True)
        self.mqtt.publish(topic, value, retain=True)

    def _publish_binary_sensor(self, binding: ZoneBinding, device: Any, zone: Any, key: str, field: str, device_class: str | None) -> None:
        object_id = f"{binding.object_id}_{key}"
        topic = f"{self._topic(binding.object_id)}/{key}"
        payload: dict[str, Any] = {
            "name": f"{self._friendly_entity_name(binding)} {key.replace('_', ' ').title()}",
            "unique_id": object_id,
            "object_id": object_id,
            "device": self._zone_device_info(binding, device, zone),
            "availability_topic": f"{self._topic(binding.object_id)}/availability",
            "state_topic": topic,
            "payload_on": "ON",
            "payload_off": "OFF",
            "entity_category": "diagnostic",
        }
        if device_class:
            payload["device_class"] = device_class
        self._publish_json(f"{self.discovery_prefix}/binary_sensor/{object_id}/config", payload, retain=True)
        self.mqtt.publish(topic, "ON" if _bool(_zone_get(zone, field, False)) else "OFF", retain=True)

    def _publish_hub_status(self, device: Any, availability: str) -> None:
        device_name = slugify(str(getattr(device, "devicename", "device")))
        device_id = slugify(str(getattr(device, "deviceid", device_name)))
        self.mqtt.publish(f"{self.base_topic}/hub_{device_name}_{device_id}/availability", availability, retain=True)

    def _publish_json(self, topic: str, payload: dict[str, Any], retain: bool = False) -> None:
        self.mqtt.publish(topic, payload, retain=retain)

    def _subscribe_command(self, binding: ZoneBinding, topic: str) -> None:
        self.bindings_by_command_topic[topic] = binding
        self.mqtt.subscribe(topic)

    def _topic(self, object_id: str) -> str:
        return f"{self.base_topic}/{object_id}"

    def _object_id(self, device: Any, zone_name: str) -> str:
        device_name = slugify(str(getattr(device, "devicename", "hub")))
        device_id = slugify(str(getattr(device, "deviceid", device_name)))
        return f"neohub_{device_name}_{zone_name and slugify(zone_name)}_{device_id[-8:]}"

    def _hub_device_info(self, device: Any) -> dict[str, Any]:
        device_id = str(getattr(device, "deviceid", slugify(str(getattr(device, "devicename", "device")))))
        hub_zone = self.mapping.hub_zone_for(device)
        info: dict[str, Any] = {
            "identifiers": [f"neohub_hub_{device_id}"],
            "name": getattr(device, "devicename", "NeoHub"),
            "manufacturer": "Heatmiser",
            "model": getattr(device, "type", "NeoHub"),
            "sw_version": str(getattr(device, "version", "")),
        }
        if hub_zone:
            info["suggested_area"] = hub_zone
        return info

    def _zone_device_info(self, binding: ZoneBinding, device: Any, zone: Any) -> dict[str, Any]:
        zone_identifier = _zone_get(zone, "DEVICE_ID") or binding.zone_name
        info: dict[str, Any] = {
            "identifiers": [f"neohub_point_{binding.device_id}_{slugify(str(zone_identifier))}"],
            "name": self._friendly_entity_name(binding),
            "manufacturer": "Heatmiser",
            "model": self._zone_model(zone),
            "via_device": f"neohub_hub_{binding.device_id}",
        }
        if binding.room:
            info["suggested_area"] = binding.room
        elif binding.property_zone:
            info["suggested_area"] = binding.property_zone
        return info

    def _friendly_entity_name(self, binding: ZoneBinding) -> str:
        if binding.room and slugify(binding.room) != slugify(binding.zone_name):
            return f"{binding.room} ({binding.zone_name})"
        return binding.zone_name

    def _zone_attributes(self, binding: ZoneBinding, zone: Any) -> dict[str, Any]:
        return {
            "property_name": binding.property_name,
            "property_zone": binding.property_zone,
            "room": binding.room,
            "hub_name": binding.device_name,
            "hub_id": binding.device_id,
            "zone_name": binding.zone_name,
            "window_open": _bool(_zone_get(zone, "WINDOW_OPEN", False)),
            "low_battery": _bool(_zone_get(zone, "LOW_BATTERY", False)),
            "timer_on": _bool(_zone_get(zone, "TIMER_ON", False)),
            "hold_on": _bool(_zone_get(zone, "HOLD_ON", False)),
            "standby": _bool(_zone_get(zone, "STANDBY", False)),
            "away": _bool(_zone_get(zone, "AWAY", False)),
            "holiday": _bool(_zone_get(zone, "HOLIDAY", False)),
            "modulation_level": _zone_get(zone, "MODULATION_LEVEL", 0),
            "device_id": _zone_get(zone, "DEVICE_ID"),
            "available_modes": _zone_get(zone, "AVAILABLE_MODES", []),
        }

    def _device_is_online(self, device: Any) -> bool:
        online = getattr(device, "online", None)
        if online is None:
            return True
        return not _explicit_false(online)

    def _zone_kind(self, zone: Any) -> str:
        zone_name = str(_zone_get(zone, "ZONE_NAME", ""))
        actual_temp = str(_zone_get(zone, "ACTUAL_TEMP", ""))
        thermostat = _zone_get(zone, "THERMOSTAT")
        device_type = str(_zone_get(zone, "DEVICE_TYPE", ""))
        if device_type == "6" or actual_temp == "255.255" or "socket" in zone_name.lower():
            return "socket"
        if isinstance(thermostat, dict) or thermostat is True:
            return "climate"
        return "climate"

    def _zone_model(self, zone: Any) -> str:
        if self._zone_kind(zone) == "socket":
            return "NeoPlug / socket"
        if _bool(_zone_get(zone, "TIMECLOCK", False)):
            return "NeoStat timeclock"
        return "NeoStat thermostat"

    def _ha_mode(self, api_mode: Any, heat_mode: Any, standby: Any = False) -> str:
        if _bool(standby):
            return "off"
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


def _zone_get(zone: Any, key: str, default: Any = None) -> Any:
    if isinstance(zone, dict):
        return zone.get(key, default)
    return getattr(zone, key, default)


def _supervisor_mqtt_settings() -> MQTTSettings | None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        response = requests.get(SUPERVISOR_MQTT_URL, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        _LOGGER.warning("Unable to read Supervisor MQTT service details: %s", exc)
        return None
    return MQTTSettings(
        host=payload["host"],
        port=int(payload.get("port") or 1883),
        username=payload.get("username"),
        password=payload.get("password"),
        ssl_enabled=_bool(payload.get("ssl", False)),
        protocol=payload.get("protocol"),
        source="supervisor-service",
    )


def _mqtt_settings_from_options(options: dict[str, Any]) -> MQTTSettings:
    mqtt_options = options.get("mqtt") or {}
    has_explicit_auth = bool(mqtt_options.get("username") or os.environ.get("MQTT_USERNAME"))
    has_explicit_host = bool(mqtt_options.get("host") or os.environ.get("MQTT_HOST"))
    if not has_explicit_auth:
        supervisor_settings = _supervisor_mqtt_settings()
        if supervisor_settings:
            supervisor_settings.client_id = mqtt_options.get("client_id") or "neohub-control-addon"
            return supervisor_settings
    return MQTTSettings(
        host=mqtt_options.get("host") or os.environ.get("MQTT_HOST") or "core-mosquitto",
        port=int(mqtt_options.get("port") or os.environ.get("MQTT_PORT") or 1883),
        username=mqtt_options.get("username") or os.environ.get("MQTT_USERNAME"),
        password=mqtt_options.get("password") or os.environ.get("MQTT_PASSWORD"),
        client_id=mqtt_options.get("client_id") or "neohub-control-addon",
        ssl_enabled=_bool(mqtt_options.get("ssl") or os.environ.get("MQTT_SSL") or False),
        protocol=mqtt_options.get("protocol") or os.environ.get("MQTT_PROTOCOL"),
        source="explicit-options" if has_explicit_host or has_explicit_auth else "defaults",
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
        mapping=MappingSettings.from_options(options),
    )
    bridge_holder["bridge"] = bridge
    return bridge, mqtt


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    options = _read_addon_options()
    poll_interval = int(options.get("poll_interval", os.environ.get("POLL_INTERVAL", 60)))
    mqtt: PahoMQTTAdapter | None = None
    running = True

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    while running:
        try:
            bridge, mqtt = build_bridge_from_options(options)
            bridge.startup()
            while running:
                bridge.publish_all()
                time.sleep(poll_interval)
        except Exception as exc:
            _LOGGER.exception("NeoHub Control loop failed; retrying in 30 seconds: %s", exc)
            if mqtt is not None:
                try:
                    mqtt.stop()
                except Exception:
                    _LOGGER.debug("Failed to stop MQTT cleanly", exc_info=True)
                mqtt = None
            time.sleep(min(30, poll_interval))
    if mqtt is not None:
        mqtt.stop()


if __name__ == "__main__":
    main()
