# NeoHub Control Home Assistant Add-on

NeoHub Control logs in to the Heatmiser NeoHub cloud using the same `hm_user_login` authentication method used by the Python dashboard, polls live device data with `hm_cache_value`, and exposes thermostats/sockets to Home Assistant over MQTT Discovery.

## What it creates

- Thermostat zones become MQTT `climate` entities.
- Socket-like zones become MQTT `switch` entities.
- Per-zone attributes include window-open, low-battery, timer, and modulation information.
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
mqtt:
  host: core-mosquitto
  port: 1883
  username: ""
  password: ""
```

If Mosquitto is configured with Home Assistant service discovery, `core-mosquitto:1883` is normally correct. If your broker requires credentials, set `mqtt.username` and `mqtt.password`.

## Dashboard included

This repository ships with two Lovelace dashboards:

- `dashboards/neohub-control-premium-dashboard.yaml` — auto-populating, visually polished dashboard using Mushroom, Auto Entities, ApexCharts, and optional Card Mod.
- `dashboards/neohub-control-basic-dashboard.yaml` — built-in Home Assistant cards only.

The premium dashboard looks for:

```text
climate.neohub_*
switch.neohub_*
```

## MQTT topics

For a hub called `Main Hub` and a zone called `Kitchen UFH`, topics look like:

```text
homeassistant/climate/neohub_main_hub_kitchen_ufh/config
neohub/neohub_main_hub_kitchen_ufh/current_temperature
neohub/neohub_main_hub_kitchen_ufh/target_temperature
neohub/neohub_main_hub_kitchen_ufh/set_temperature
neohub/neohub_main_hub_kitchen_ufh/set_mode
```

## Notes

This add-on is designed for NeoHub-backed devices. Neostat WiFi devices that can read data but redirect control endpoints to HTML may need a separate control implementation.
