# Changelog

All notable changes to NeoHub Control are documented here.

## [0.2.4] - 2026-06-20

### Changed

- Align the add-on manifest with current Home Assistant app guidance by publishing a GHCR image reference, quoting the SemVer version, and limiting builds to supported `aarch64` and `amd64` architectures.
- Replace the local-build-only release path with Home Assistant builder actions for pull-request validation and multi-architecture publishing on `master`.
- Move the add-on image to the official pinned Home Assistant Python base image.
- Add explicit Supervisor API scope for MQTT service discovery and remove the unused `/share` write mapping.
- Add an AppArmor profile as a second line of defence.
- Harden MQTT and NeoHub client runtime behaviour with paho-mqtt 2.x disconnect callback support, explicit network timeouts, and deterministic MQTT option precedence.

## [0.2.3] - 2026-06-19

### Changed

- Existing release baseline before the Home Assistant best-practice alignment pass.
