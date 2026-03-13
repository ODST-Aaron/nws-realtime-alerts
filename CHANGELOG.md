# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial public release
- Real-time NWS alert monitoring with Last-Modified header optimization
- Discord and Slack webhook notifications
- Auto-generated PNG alert maps via `alert_mapper.py`
- Bulk NWS zone/county lookup utility (`bulk_zone_lookup.py`)
- Tiered alert system (critical/warning/watch/advisory)
- Startup active alert awareness
- Graceful shutdown with SIGINT/SIGTERM handlers
- Polygon-based and UGC fallback site matching

### Known Issues
- Slack map delivery not yet implemented (placeholder "Map attached" footer)
- NWS alert link in Slack removed (no suitable filterable public URL since alerts.weather.gov decommissioned)

## [1.0.0] - 2025-01-XX

### Added
- First stable release

[Unreleased]: https://github.com/ODST-Aaron/nws-realtime-alerts/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ODST-Aaron/nws-realtime-alerts/releases/tag/v1.0.0
