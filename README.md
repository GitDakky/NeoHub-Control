<p align="center">
  <img src="assets/neohub-control-hero.svg" alt="NeoHub Control animated header" width="100%" />
</p>

<p align="center">
  <a href="https://github.com/GitDakky/NeoHub-Control"><img alt="GitHub" src="https://img.shields.io/badge/GitHub-GitDakky%2FNeoHub--Control-111827?style=for-the-badge&logo=github&logoColor=white"></a>
  <img alt="Home Assistant" src="https://img.shields.io/badge/Home%20Assistant-Add--on-18BCF2?style=for-the-badge&logo=homeassistant&logoColor=white">
  <img alt="MQTT Discovery" src="https://img.shields.io/badge/MQTT-Discovery-660066?style=for-the-badge&logo=mqtt&logoColor=white">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-34D399?style=for-the-badge">
</p>

# NeoHub Control

NeoHub Control turns Heatmiser NeoHub heating into a first-class Home Assistant citizen: cloud login, live zone telemetry, MQTT Discovery, thermostat control, socket control, diagnostic attributes, and a dashboard that looks like it belongs in a mission-control room rather than a boiler cupboard.

It began as a Streamlit dashboard and Python API wrapper. It is now also a Home Assistant add-on that uses the same proven NeoHub cloud authentication flow:

- `hm_user_login` for login and device discovery
- `hm_cache_value` for live heating state
- `hm_set_temp` for temperature commands
- `hm_set_mode` for mode and socket-style commands

The result: your Heatmiser estate becomes discoverable `climate.*` and `switch.*` entities in Home Assistant, ready for dashboards, automations, voice assistants, energy workflows, and sane operational visibility.

---

## Why this exists

Heating is infrastructure. It should be observable, scriptable, automatable, and beautiful.

NeoHub Control is for people who want more than a vendor app:

- Landlords and estate operators managing many heating zones
- Smart-home builders who want Home Assistant-native climate entities
- Engineers who want MQTT topics they can inspect, replay, automate, and trust
- Anyone who wants Heatmiser visibility without staring at a phone app

---

## Highlights

### Home Assistant add-on

- Runs inside Home Assistant OS / Supervised as an add-on
- Uses MQTT Discovery to create Home Assistant entities automatically
- Supports multi-architecture builds: `aarch64`, `amd64`, `armhf`, `armv7`, `i386`
- Reads configuration from the standard add-on `/data/options.json`
- Uses the Mosquitto add-on by default at `core-mosquitto:1883`

### Climate + socket entities

- Thermostat-like zones become MQTT `climate` entities
- Socket-like zones become MQTT `switch` entities
- Stable object IDs based on hub and zone name
- Retained availability, state, and discovery topics

### Real control path

Commands from Home Assistant are routed back to the NeoHub API:

- Set target temperature from Home Assistant
- Change mode: heat, cool, fan-only/vent, off
- Toggle socket-like zones through the mode command path

### Rich telemetry

The bridge publishes:

- Current temperature
- Target temperature
- HVAC mode
- Heating action
- Humidity
- Availability
- Window-open attribute
- Low-battery attribute
- Timer status
- Modulation level

### Premium dashboard included

This repository includes two dashboard templates:

- `dashboards/neohub-control-premium-dashboard.yaml`
  - Premium Home Assistant dashboard using Mushroom, Auto Entities, and ApexCharts
  - Auto-populates `climate.neohub_*` and `switch.neohub_*` entities
  - Includes a 24-hour temperature intelligence view

- `dashboards/neohub-control-basic-dashboard.yaml`
  - Zero-dependency Lovelace dashboard using only built-in cards
  - Good for clean installs or conservative systems

---

## Architecture

```mermaid
flowchart LR
    HA[Home Assistant] -->|MQTT Discovery| MQTT[(MQTT Broker)]
    MQTT -->|command topics| ADDON[NeoHub Control Add-on]
    ADDON -->|hm_user_login| CLOUD[Heatmiser NeoHub Cloud]
    ADDON -->|hm_cache_value| CLOUD
    ADDON -->|hm_set_temp / hm_set_mode| CLOUD
    CLOUD --> HUB[NeoHub]
    HUB --> ZONES[Thermostats + Sockets]
    ADDON -->|state topics| MQTT
    MQTT -->|climate/switch entities| HA
```

The add-on is intentionally MQTT-native. MQTT Discovery is the cleanest way for an add-on to create Home Assistant climate and switch entities without writing and maintaining a separate Home Assistant custom integration.

---

## Repository layout

```text
.
├── addons/
│   └── neohub_control/              # Home Assistant add-on
│       ├── config.yaml              # Add-on manifest and options schema
│       ├── Dockerfile               # Add-on container image
│       ├── DOCS.md                  # Add-on documentation
│       ├── README.md                # Add-on store summary
│       ├── rootfs/                  # s6 service runner
│       └── app/                     # Code copied into the add-on image
├── assets/
│   └── neohub-control-hero.svg      # Animated project header
├── dashboards/
│   ├── neohub-control-premium-dashboard.yaml
│   └── neohub-control-basic-dashboard.yaml
├── ha_addon/                        # Testable add-on bridge source
├── neohub/                          # NeoHub API wrapper
├── app.py                           # Streamlit dashboard
├── cli.py                           # CLI reader
├── tests/                           # MQTT bridge tests
└── repository.yaml                  # Home Assistant add-on repository manifest
```

---

## Installing as a Home Assistant add-on

### 1. Add this repository to Home Assistant

In Home Assistant:

1. Go to Settings → Add-ons → Add-on Store
2. Open the three-dot menu
3. Choose Repositories
4. Add:

```text
https://github.com/GitDakky/NeoHub-Control
```

5. Refresh the add-on store
6. Install `NeoHub Control`

### 2. Enable MQTT

Install and start the official Mosquitto broker add-on, then make sure the MQTT integration is enabled in Home Assistant.

Default broker settings expected by this add-on:

```yaml
mqtt:
  host: core-mosquitto
  port: 1883
  username: ""
  password: ""
```

If your broker requires credentials, set them in the add-on options.

### 3. Configure NeoHub credentials

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

Start the add-on. Within one poll cycle, Home Assistant should discover entities like:

```text
climate.neohub_main_hub_kitchen_ufh
climate.neohub_main_hub_lounge
switch.neohub_main_hub_garden_socket
```

---

## Dashboard setup

### Premium dashboard

Use this if you want the full visual experience:

```text
dashboards/neohub-control-premium-dashboard.yaml
```

Recommended HACS cards:

- Mushroom Cards
- Auto Entities
- ApexCharts Card
- Optional: Card Mod for the glassmorphism hero card styling

The premium dashboard auto-discovers entities matching:

```text
climate.neohub_*
switch.neohub_*
```

### Basic dashboard

Use this if you want no custom frontend dependencies:

```text
dashboards/neohub-control-basic-dashboard.yaml
```

Edit the example entity IDs to match your actual discovered entities.

---

## MQTT topic model

For a hub called `Main Hub` and a zone called `Kitchen UFH`, the bridge creates an object ID like:

```text
neohub_main_hub_kitchen_ufh
```

Discovery:

```text
homeassistant/climate/neohub_main_hub_kitchen_ufh/config
```

State:

```text
neohub/neohub_main_hub_kitchen_ufh/availability
neohub/neohub_main_hub_kitchen_ufh/current_temperature
neohub/neohub_main_hub_kitchen_ufh/target_temperature
neohub/neohub_main_hub_kitchen_ufh/mode
neohub/neohub_main_hub_kitchen_ufh/action
neohub/neohub_main_hub_kitchen_ufh/humidity
neohub/neohub_main_hub_kitchen_ufh/attributes
```

Commands:

```text
neohub/neohub_main_hub_kitchen_ufh/set_temperature
neohub/neohub_main_hub_kitchen_ufh/set_mode
```

---

## Running the original Streamlit dashboard

The original dashboard is still available for local desktop/browser use.

```bash
git clone https://github.com/GitDakky/NeoHub-Control.git
cd NeoHub-Control
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

---

## CLI usage

```bash
python cli.py your-neohub-email@example.com your-password
python cli.py your-neohub-email@example.com your-password "Main Hub"
```

---

## Development

This project is deliberately small and inspectable.

Run tests:

```bash
PYTHONPATH=. pytest -q
```

Run the add-on bridge tests against the packaged add-on copy:

```bash
PYTHONPATH=addons/neohub_control/app pytest tests/test_ha_mqtt.py -q
```

Run lint:

```bash
ruff check .
```

Build the add-on image locally:

```bash
docker build -t neohub-control-addon-test addons/neohub_control
```

---

## Current status

Working and tested locally:

- MQTT discovery payload generation
- Climate state publishing
- Socket state publishing
- Command topic routing
- Temperature command validation
- Python compile checks
- Ruff lint checks
- YAML parsing checks

Needs real-world validation:

- Live NeoHub account/device test
- Home Assistant add-on store install flow
- Docker build on a running Docker daemon
- Long-running MQTT reconnect behavior under broker/cloud outages

---

## Neostat WiFi note

This project is designed for NeoHub-backed devices. A reported Neostat WiFi case can read data but receives an HTML redirect when attempting control endpoints such as `hm_set_temp`. That likely needs a separate Neostat WiFi control strategy rather than the NeoHub control path.

---

## Security and privacy

- Credentials are read from Home Assistant add-on options.
- Credentials are not published to MQTT.
- MQTT discovery/state topics contain hub and zone names; choose zone names accordingly if topic visibility matters in your network.
- Use a trusted MQTT broker and avoid exposing it directly to the internet.

---

## Contributing

Pull requests are welcome.

Good first contributions:

- Confirm live device compatibility
- Add reconnect/backoff hardening
- Improve socket-specific control semantics
- Add optional sensors for diagnostics
- Add Home Assistant screenshots
- Package releases and SLSA provenance for real build artifacts

Please include tests for behavior changes where practical.

---

## License

MIT. See `LICENSE`.

---

## Acknowledgments

Built for the Home Assistant and Heatmiser communities, with respect for people who believe their heating system should be as observable and automatable as the rest of their infrastructure.
