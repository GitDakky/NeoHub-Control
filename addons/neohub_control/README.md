# NeoHub Control

Expose Heatmiser NeoHub thermostats, sockets, diagnostic readings, and room/zone metadata to Home Assistant using MQTT Discovery.

The add-on uses the existing NeoHub cloud login/data/control flow:

- `hm_user_login` for authentication
- `hm_cache_value` for live status
- `hm_set_temp` for target temperature commands
- `hm_set_mode` for mode/switch commands

Version `0.2.5` keeps the current Home Assistant add-on packaging and adds a HACS companion helper so users who paste the repository into HACS get install guidance instead of the add-on repository rejection. The working bridge still installs through the Home Assistant Add-on Store.

Includes premium and zero-dependency Lovelace dashboard templates in the repository `dashboards/` directory.

See `DOCS.md` for setup and topic details.
