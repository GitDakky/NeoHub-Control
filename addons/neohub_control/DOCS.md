# NeoHub Control Home Assistant Add-on

NeoHub Control logs in to the Heatmiser NeoHub cloud using `hm_user_login`, polls live hub/thermostat point data with `hm_cache_value`, and exposes a modern, multi-hub model to Home Assistant over MQTT Discovery.

## What it creates

- Thermostat points become MQTT `climate` entities.
- Socket-like points become MQTT `switch` entities.
- Diagnostic entities are published for useful telemetry such as floor temperature, modulation level, window-open, low-battery, heat-on, and cool-on.
- Each hub and thermostat point gets stable IDs that include the hub ID, preventing collisions when five hubs share room names like Kitchen, Hallway, Ensuite, etc.
- Per-point attributes include `property_name`, `property_zone`, `room`, `hub_name`, and `hub_id` so dashboards and automations can group by your real building model.
- Temperature and mode commands are routed back to the NeoHub API with `hm_set_temp` and `hm_set_mode`.

## Requirements

- Home Assistant OS or Supervised install with add-on support.
- MQTT broker add-on, normally Mosquitto.
- MQTT integration enabled in Home Assistant.
- Heatmiser NeoHub account credentials.

## Configuration

```yaml
username: your-neohub-email@example.com
password: your-neohub-password
url: https://neohub.co.uk/
poll_interval: 60
discovery_prefix: homeassistant
base_topic: neohub
property_name: Longueville Hall

# Assign physical NeoHub hardware to broad building zones.
# Use hub_id when known; hub_name is accepted for readability.
hub_zones:
  - hub_id: D8:80:39:AE:5E:4C
    zone: Gate House
  - hub_name: 2nd Floor
    zone: Upper Floor

# Assign individual thermostat points to rooms.
# zone can override/inherit the hub zone for that thermostat.
room_mappings:
  - hub_name: Gate House
    thermostat: Kitchen
    room: Kitchen
    zone: Gate House
  - hub_name: 2nd Floor
    thermostat: G Ensuite
    room: Green Ensuite
    zone: Upper Floor

# Normally leave mqtt fields blank: the add-on now reads Supervisor's
# MQTT service credentials automatically. Fill these only for an external broker.
mqtt:
  host: ""
  port: 1883
  username: ""
  password: ""
  ssl: false
```

### MQTT authentication

Version `0.2.4` declares minimal Supervisor API access for the MQTT service (`mqtt:need`) and uses the generated add-on credentials from Mosquitto automatically. This avoids the common failure where `core-mosquitto` rejects anonymous/blank MQTT logins and no discovery entities appear.

## Home Assistant packaging and security

- The add-on uses the official pinned Home Assistant Python base image.
- `config.yaml` points to the pre-built `ghcr.io/gitdakky/neohub-control` image; Home Assistant no longer needs to build the container locally.
- CI uses the current Home Assistant builder actions to validate pull requests and publish `aarch64`/`amd64` images from `master`.
- The add-on keeps protection mode compatible defaults: no host networking, no privileged mode, no device mounts, and no `/share` write mapping.
- An `apparmor.txt` profile is included as a second line of defence for the Python bridge.

## Dashboard included

This standalone add-on repository ships with two Lovelace dashboards:

- `dashboards/neohub-control-premium-dashboard.yaml` — auto-populating, visually polished dashboard using Mushroom, Auto Entities, ApexCharts, and optional Card Mod.
- `dashboards/neohub-control-basic-dashboard.yaml` — built-in Home Assistant cards only.

The premium dashboard looks for:

```text
climate.neohub_*
switch.neohub_*
sensor.neohub_*
binary_sensor.neohub_*
```

## MQTT topics

For a hub called `Main Hub`, hub ID `hub-1`, and thermostat `Kitchen UFH`, topics look like:

```text
homeassistant/climate/neohub_main_hub_kitchen_ufh_hub_1/config
neohub/neohub_main_hub_kitchen_ufh_hub_1/current_temperature
neohub/neohub_main_hub_kitchen_ufh_hub_1/target_temperature
neohub/neohub_main_hub_kitchen_ufh_hub_1/set_temperature
neohub/neohub_main_hub_kitchen_ufh_hub_1/set_mode
```

## Notes

This add-on is designed for NeoHub-backed devices. Neostat WiFi devices that can read data but redirect control endpoints to HTML may need a separate control implementation.
