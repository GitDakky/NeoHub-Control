# NeoHub Control

Expose Heatmiser NeoHub thermostats, sockets, diagnostic readings, and room/zone metadata to Home Assistant using MQTT Discovery.

The add-on uses the existing NeoHub cloud login/data/control flow:

- `hm_user_login` for authentication
- `hm_cache_value` for live status
- `hm_set_temp` for target temperature commands
- `hm_set_mode` for mode/switch commands

Version `0.2.0` adds automatic Supervisor MQTT credential discovery, stable multi-hub IDs, diagnostic sensors/binary sensors, and configurable hub → property-zone plus thermostat → room mapping for properties with multiple hubs.

Includes premium and zero-dependency Lovelace dashboard templates in the repository `dashboards/` directory.

See `DOCS.md` for setup and topic details.
