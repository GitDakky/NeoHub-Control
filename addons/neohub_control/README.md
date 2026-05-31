# NeoHub Control

Expose Heatmiser NeoHub thermostats and sockets to Home Assistant using MQTT Discovery.

The add-on uses the existing NeoHub cloud login/data/control flow from this repository:

- `hm_user_login` for authentication
- `hm_cache_value` for live status
- `hm_set_temp` for target temperature commands
- `hm_set_mode` for mode/switch commands

Includes premium and zero-dependency Lovelace dashboard templates in the repository `dashboards/` directory.

See `DOCS.md` for setup and topic details.
